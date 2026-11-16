use crate::pdf::Pdf;
use anyhow::{anyhow, bail, Context as _, Result};
use rquickjs::{Context, Ctx, Exception, Function, Runtime as Engine};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::{HashSet, VecDeque},
    path::PathBuf,
    rc::Rc,
    sync::{Arc, LazyLock, Mutex},
};
mod document_context;
mod documents;
struct DocumentServices {
    dialogs: Arc<Mutex<VecDeque<Value>>>,
    alerts: Arc<Mutex<VecDeque<Value>>>,
    interactive: bool,
    print_output_dir: Option<PathBuf>,
    attachment_output_dir: Option<PathBuf>,
    trace_dir: Option<PathBuf>,
    dialog_count: Arc<Mutex<usize>>,
    alert_count: Arc<Mutex<usize>>,
    // Original scripts can catch a rejected test reply. Keep control failures
    // outside their JavaScript state so a probe cannot silently pass afterward.
    control_errors: Arc<Mutex<Vec<Value>>>,
}
pub struct Runtime {
    pub js: Context,
    _engine: Engine,
    pub loaded: usize,
    documents: Rc<documents::Documents>,
}
// Reader's span metrics use one decimal with ties-to-even, applied to the
// actual binary value (8.05 rounds up; 7.25 rounds down). Multiplication by ten
// first would erase the distinction at some half-way values.
fn round_rich_metric(value: f64) -> f64 {
    format!("{value:.1}").parse().unwrap_or(value)
}
// Reader folds spaces and ligatures when a string fits PDFDocEncoding;
// a value requiring Unicode retains them. Rich inputs convert each span.
fn normalize_pdf_text(value: String) -> String {
    static PDF_DOC_CHARACTERS: LazyLock<HashSet<char>> = LazyLock::new(|| {
        let bytes = lopdf::Object::String((0..=255).collect(), lopdf::StringFormat::Literal);
        lopdf::decode_text_string(&bytes)
            .expect("The PDFDocEncoding byte map is valid")
            .chars()
            .collect()
    });
    if value
        .chars()
        .all(|c| c == '\u{a0}' || PDF_DOC_CHARACTERS.contains(&c))
    {
        value
            .replace('\u{a0}', " ")
            .replace('ﬁ', "fi")
            .replace('ﬂ', "fl")
    } else {
        value
    }
}
fn decode_xfdf_rich(ctx: Ctx, request: String) -> rquickjs::Result<String> {
    (|| -> Result<String> {
        let request: Value = serde_json::from_str(&request)?;
        Ok(crate::pdf::xfdf::rich_import(
            request["xml"]
                .as_str()
                .context("Missing rich XFDF markup")?,
            &request["defaults"],
        )?
        .to_string())
    })()
    .map_err(|e| Exception::throw_message(&ctx, &format!("{e:#}")))
}
// Scripted probes select only options actually offered by the original dialog.
// Preserve option magnitudes because Acrobat uses them as item identities.
fn select_dialog_options(request: &Value, reply: &mut Value) -> Result<()> {
    let Some(selections) = reply["select"].as_object().cloned() else {
        return Ok(());
    };
    fn select(
        options: &mut Value,
        labels: &[String],
        qualified: bool,
        parents: &[String],
        matches: &mut usize,
    ) {
        if let Some(options) = options.as_object_mut() {
            for (name, value) in options {
                let mut path = parents.to_vec();
                path.push(name.clone());
                if let Some(n) = value.as_i64() {
                    let magnitude = n.saturating_abs().max(1);
                    let selected = if qualified {
                        path == labels
                    } else {
                        name == &labels[0]
                    };
                    *value = json!(if selected {
                        *matches += 1;
                        magnitude
                    } else {
                        -magnitude
                    });
                } else {
                    select(value, labels, qualified, &path, matches);
                }
            }
        }
    }
    for (id, selection) in selections {
        let qualified = selection.is_array();
        let labels = if let Some(label) = selection.as_str() {
            vec![label.to_owned()]
        } else {
            selection
                .as_array()
                .context("dialog selection must be a label or label path")?
                .iter()
                .map(|v| {
                    v.as_str()
                        .map(str::to_owned)
                        .context("dialog path labels must be strings")
                })
                .collect::<Result<Vec<_>>>()?
        };
        if labels.is_empty() {
            bail!("dialog selection path must not be empty")
        }
        if request["enabled"][&id] == false || request["visible"][&id] == false {
            bail!("dialog control {id} is unavailable")
        }
        let mut options = request["values"][&id].clone();
        let mut matches = 0;
        select(&mut options, &labels, qualified, &[], &mut matches);
        if matches != 1 {
            bail!("dialog control {id} offers {matches} matches for {selection}")
        }
        if !reply["values"].is_object() {
            reply["values"] = json!({});
        }
        reply["values"][&id] = options;
    }
    Ok(())
}
fn scripted_alert_response(request: &Value, reply: &Value) -> Result<Value> {
    if let Some(title) = reply.get("title") {
        if title.as_str() != request["cTitle"].as_str() {
            bail!("scripted alert title does not match the actual request")
        }
    }
    let button = reply
        .as_i64()
        .or_else(|| reply["button"].as_i64())
        .context("scripted alert requires a button code")?;
    let kind = request["nType"].as_i64().unwrap_or(0);
    let allowed: &[i64] = match kind {
        0 => &[1],
        1 => &[1, 2],
        2 => &[3, 4],
        3 => &[2, 3, 4],
        _ => bail!("unsupported alert type {kind}"),
    };
    if !allowed.contains(&button) {
        bail!(
            "alert type {kind} does not offer button code {button}: {}",
            request["cTitle"]
        )
    }
    let checked = reply
        .get("checked")
        .and_then(Value::as_bool)
        .unwrap_or_else(|| {
            request["oCheckbox"]["bInitialValue"]
                .as_bool()
                .unwrap_or(false)
        });
    Ok(json!({"button":button,"checked":checked}))
}
// Probe button paths use the labels shown by the original dialog, including
// parent menus. Resolve to a real enabled control; never manufacture a choice.
fn select_dialog_button(request: &Value, reply: &mut Value) -> Result<()> {
    let Some(path) = reply.get("button_path") else {
        return Ok(());
    };
    let path: Vec<&str> = path
        .as_array()
        .context("button_path must be an array")?
        .iter()
        .map(|v| v.as_str().context("button path labels must be strings"))
        .collect::<Result<_>>()?;
    if path.is_empty() {
        bail!("button_path cannot be empty")
    }
    fn matches(name: &str, wanted: &str) -> bool {
        let name = name.trim_start_matches("✓ ");
        name.trim() == wanted || name.split('\t').next().unwrap_or(name).trim() == wanted
    }
    fn walk(
        request: &Value,
        element: &Value,
        path: &[&str],
        available: bool,
        found: &mut Vec<String>,
    ) {
        let id = element["item_id"].as_str().unwrap_or("");
        let available =
            available && request["enabled"][id] != false && request["visible"][id] != false;
        let name = element["name"].as_str().unwrap_or("");
        if !name.is_empty() && (path.is_empty() || !matches(name, path[0])) {
            return;
        }
        let remaining = if name.is_empty() { path } else { &path[1..] };
        if element["type"] == "button" && remaining.is_empty() && available && !id.is_empty() {
            found.push(id.to_owned());
        }
        if let Some(children) = element["elements"].as_array() {
            for child in children {
                walk(request, child, remaining, available, found);
            }
        }
    }
    let mut found = Vec::new();
    if let Some(elements) = request["description"]["elements"].as_array() {
        for element in elements {
            walk(request, element, &path, true, &mut found);
        }
    }
    if found.len() != 1 {
        bail!(
            "dialog offers {} available matches for button path {path:?}",
            found.len()
        )
    }
    reply["event"] = json!(found[0]);
    reply.as_object_mut().unwrap().remove("result");
    Ok(())
}
impl Runtime {
    pub fn new(
        pdf: &Arc<Pdf>,
        dialogs: Vec<Value>,
        alerts: Vec<Value>,
        interactive: bool,
        print_output_dir: Option<std::path::PathBuf>,
        attachment_output_dir: Option<std::path::PathBuf>,
    ) -> Result<Self> {
        let engine = Engine::new()?;
        engine.set_memory_limit(512 * 1024 * 1024);
        engine.set_max_stack_size(2 * 1024 * 1024);
        let js = Context::full(&engine)?;
        let services = DocumentServices {
            dialogs: Arc::new(Mutex::new(VecDeque::from(dialogs))),
            alerts: Arc::new(Mutex::new(VecDeque::from(alerts))),
            interactive,
            print_output_dir,
            attachment_output_dir,
            trace_dir: std::env::var_os("MPMB_DIALOG_TRACE_DIR").map(PathBuf::from),
            dialog_count: Arc::new(Mutex::new(0)),
            alert_count: Arc::new(Mutex::new(0)),
            control_errors: Arc::new(Mutex::new(Vec::new())),
        };
        let documents = documents::Documents::new(js.clone(), Arc::clone(pdf), services)?;
        let loaded = js.with(|ctx| Self::initialize_document(ctx, pdf, &documents))?;
        Ok(Self {
            js,
            _engine: engine,
            loaded,
            documents,
        })
    }
    // Initialization can run inside an already-held QuickJS runtime guard.
    // Source documents must get their own context and original host/scripts;
    // reentering Context::with while a document callback holds that guard fails.
    fn initialize_document<'js>(
        ctx: Ctx<'js>,
        pdf: &Arc<Pdf>,
        documents: &Rc<documents::Documents>,
    ) -> Result<usize> {
        documents.install(ctx.clone(), pdf)?;
        ctx.globals().set(
            "__xfdfExport",
            Function::new(
                ctx.clone(),
                |ctx: Ctx, input: String| -> rquickjs::Result<String> {
                    serde_json::from_str(&input)
                        .map_err(anyhow::Error::from)
                        .and_then(|request| crate::pdf::xfdf::export(&request))
                        .map_err(|e| Exception::throw_message(&ctx, &format!("{e:#}")))
                },
            )?,
        )?;
        let services = &documents.services;
        let interactive = services.interactive;
        let print_output_dir = services.print_output_dir.clone();
        let attachment_output_dir = services.attachment_output_dir.clone();
        let xfdf_base = pdf
            .path
            .parent()
            .unwrap_or(std::path::Path::new("."))
            .to_owned();
        ctx.globals().set("__xfdfRead", Function::new(ctx.clone(), move |ctx: Ctx, path: String| -> rquickjs::Result<String> {
            (|| -> Result<String> {
                let selected = if path.is_empty() {
                    if !interactive { bail!("XFDF file picker requires interactive mode or an explicit local path") }
                    let output = std::process::Command::new("zenity").args(["--file-selection", "--title=Import XFDF form data", "--file-filter=XFDF | *.xfdf *.xml"]).arg(format!("--filename={}/", xfdf_base.display())).output()?;
                    if !output.status.success() {
                        if output.status.code() == Some(1) { return Ok(json!({"cancelled":true}).to_string()) }
                        bail!("Native XFDF file picker failed")
                    }
                    String::from_utf8(output.stdout)?.trim_end_matches(['\r', '\n']).to_owned()
                } else { path };
                if selected.contains("://") { bail!("XFDF import requires a local filesystem path") }
                let path = std::path::Path::new(&selected);
                let path = if path.is_absolute() { path.to_owned() } else { xfdf_base.join(path) };
                let bytes = std::fs::read(&path)?;
                if bytes.len() > 64 * 1024 * 1024 { bail!("XFDF import exceeds 64 MiB") }
                let fields = crate::pdf::xfdf::parse::read(std::str::from_utf8(&bytes).context("XFDF import requires UTF-8")?)?;
                let sha256 = Sha256::digest(&bytes).iter().map(|b| format!("{b:02x}")).collect::<String>();
                Ok(json!({"path":path,"sha256":sha256,"fields":fields}).to_string())
            })().map_err(|e| Exception::throw_message(&ctx, &format!("{e:#}")))
        })?)?;
        ctx.globals()
            .set("__xfdfRich", Function::new(ctx.clone(), decode_xfdf_rich)?)?;
        let repair_allowed = std::env::var_os("MPMB_STRICT_ORIGINAL_SCRIPTS").is_none()
            && pdf.scripts.iter().any(|(name, source)| {
                name == "Functions2"
                    && Sha256::digest(source.as_bytes())
                        .iter()
                        .map(|b| format!("{b:02x}"))
                        .collect::<String>()
                        == "ce4624265af7fad2456badd108fa6003e5dbb939263ee7269a4cbbf9e3055857"
            });
        let icon_base = pdf
            .path
            .parent()
            .unwrap_or(std::path::Path::new("."))
            .to_owned();
        ctx.globals().set("__iconImport", Function::new(ctx.clone(), move |ctx: Ctx, input: String| -> rquickjs::Result<String> {
            (|| -> Result<String> {
                let request: Value = serde_json::from_str(&input)?;
                let result = crate::icon_import::request(&request, interactive, &icon_base)?;
                if interactive && result["code"].as_i64().is_some_and(|v| v < 0) {
                    crate::ui::alert(&json!({"cTitle":"Import image or PDF icon", "cMsg":result["reason"].as_str().unwrap_or("The selected page is invalid"), "nType":0, "nIcon":0}))?;
                }
                Ok(result.to_string())
            })().map_err(|e| Exception::throw_message(&ctx, &format!("{e:#}")))
        })?)?;
        let attachments = crate::attachments::read(&pdf.doc)?;
        let attachment_metadata: Vec<_> = attachments.values().cloned().collect();
        let exporter = std::cell::RefCell::new(crate::attachments::Exporter::default());
        ctx.globals().set(
            "__attachment",
            Function::new(
                ctx.clone(),
                move |ctx: Ctx, request: String| -> rquickjs::Result<String> {
                    exporter
                        .borrow_mut()
                        .export(
                            &attachments,
                            &request,
                            interactive,
                            attachment_output_dir.as_deref(),
                        )
                        .map(|v| v.to_string())
                        .map_err(|e| Exception::throw_message(&ctx, &format!("{e:#}")))
                },
            )?,
        )?;
        let print_pdf = Arc::clone(pdf);
        ctx.globals().set(
            "__print",
            Function::new(
                ctx.clone(),
                move |ctx: Ctx, request: String| -> rquickjs::Result<String> {
                    crate::printing::execute(
                        &print_pdf,
                        &request,
                        interactive,
                        print_output_dir.as_deref(),
                    )
                    .map(|v| v.to_string())
                    .map_err(|e| Exception::throw_message(&ctx, &format!("{e:#}")))
                },
            )?,
        )?;
        ctx.globals().set(
            "__log",
            Function::new(ctx.clone(), |s: String| {
                eprintln!("JS: {s}");
                true
            })?,
        )?;
        let queue = Arc::clone(&services.dialogs);
        let trace_dir = services.trace_dir.clone();
        let trace_count = Arc::clone(&services.dialog_count);
        let control_errors = Arc::clone(&services.control_errors);
        let dialog_document = pdf.path.clone();
        ctx.globals().set(
            "__dialog",
            Function::new(
                ctx.clone(),
                move |ctx: Ctx, s: String| -> rquickjs::Result<String> {
                    let mut scripted = false;
                    (|| -> std::result::Result<String, String> {
                        let request: Value = serde_json::from_str(&s).map_err(|e| e.to_string())?;
                        if let Some(dir) = &trace_dir {
                            std::fs::create_dir_all(dir).map_err(|e| e.to_string())?;
                            let mut count = trace_count.lock().unwrap();
                            *count += 1;
                            std::fs::write(dir.join(format!("dialog-{:03}.json", *count)), &s)
                                .map_err(|e| e.to_string())?;
                        }
                        if let Some(mut reply) = queue.lock().unwrap().pop_front() {
                            scripted = true;
                            if let Some(title) = reply["title"].as_str() {
                                if request["description"]["name"].as_str() != Some(title) {
                                    return Err(format!(
                                        "Expected dialog {title}, received {}",
                                        request["description"]["name"]
                                    ));
                                }
                            }
                            if let Some(header) = reply["header"].as_str() {
                                fn find_header(node: &Value) -> Option<&str> {
                                    if node["item_id"] == "head" {
                                        return node["name"].as_str();
                                    }
                                    node["elements"]
                                        .as_array()
                                        .and_then(|v| v.iter().find_map(find_header))
                                }
                                if find_header(&request["description"]) != Some(header) {
                                    return Err(format!("Expected dialog header {header}"));
                                }
                            }
                            select_dialog_options(&request, &mut reply)
                                .map_err(|e| e.to_string())?;
                            select_dialog_button(&request, &mut reply)
                                .map_err(|e| e.to_string())?;
                            eprintln!(
                                "Dialog: {} [scripted response]",
                                request["description"]["name"]
                            );
                            return Ok(reply.to_string());
                        }
                        if !interactive {
                            return Err(format!(
                                "Unanswered dialog: {}",
                                request["description"]["name"]
                            ));
                        }
                        crate::ui::modal(&request)
                            .map(|v| v.to_string())
                            .map_err(|e| e.to_string())
                    })()
                    .map_err(|e| {
                        if scripted || !interactive {
                            control_errors.lock().unwrap().push(json!({
                                "kind": "dialog_control",
                                "error": e,
                                "source_document": dialog_document,
                            }));
                        }
                        Exception::throw_message(&ctx, &e)
                    })
                },
            )?,
        )?;
        let aq = Arc::clone(&services.alerts);
        let alert_trace_dir = services.trace_dir.clone();
        let alert_count = Arc::clone(&services.alert_count);
        let alert_control_errors = Arc::clone(&services.control_errors);
        let alert_document = pdf.path.clone();
        ctx.globals().set(
            "__alert",
            Function::new(
                ctx.clone(),
                move |ctx: Ctx, s: String| -> rquickjs::Result<String> {
                    let mut scripted = false;
                    (|| -> std::result::Result<String, String> {
                        let v: Value = serde_json::from_str(&s).map_err(|e| e.to_string())?;
                        if let Some(dir) = &alert_trace_dir {
                            std::fs::create_dir_all(dir).map_err(|e| e.to_string())?;
                            let mut count = alert_count.lock().unwrap();
                            *count += 1;
                            std::fs::write(dir.join(format!("alert-{:03}.json", *count)), &s)
                                .map_err(|e| e.to_string())?;
                        }
                        if let Some(reply) = aq.lock().unwrap().pop_front() {
                            scripted = true;
                            eprintln!("Alert [scripted response]: {}", v["cTitle"]);
                            return scripted_alert_response(&v, &reply)
                                .map(|v| v.to_string())
                                .map_err(|e| e.to_string());
                        }
                        if !interactive {
                            return Err(format!("Unanswered alert: {}", v["cTitle"]));
                        }
                        crate::ui::alert(&v)
                            .map(|v| v.to_string())
                            .map_err(|e| e.to_string())
                    })()
                    .map_err(|e| {
                        if scripted || !interactive {
                            alert_control_errors.lock().unwrap().push(json!({
                                "kind": "alert_control",
                                "error": e,
                                "source_document": alert_document,
                            }));
                        }
                        Exception::throw_message(&ctx, &e)
                    })
                },
            )?,
        )?;
        ctx.globals().set(
            "__file",
            Function::new(
                ctx.clone(),
                move |ctx: Ctx, path: String| -> rquickjs::Result<String> {
                    (|| -> Result<String> {
                        let selected = if path.is_empty() {
                            if !interactive {
                                bail!(
                                    "file picker requires interactive mode or explicit local path"
                                )
                            }
                            let out = std::process::Command::new("zenity")
                                .args([
                                    "--file-selection",
                                    "--title=Import MPMB JavaScript",
                                    "--file-filter=JavaScript | *.js",
                                ])
                                .output()?;
                            if !out.status.success() {
                                return Ok("null".into());
                            }
                            String::from_utf8(out.stdout)?
                                .trim_end_matches('\n')
                                .to_owned()
                        } else {
                            path
                        };
                        if selected.starts_with("http:") || selected.starts_with("https:") {
                            bail!("URL imports are unsupported")
                        }
                        let bytes = std::fs::read(selected)?;
                        if bytes.len() > 16 * 1024 * 1024 {
                            bail!("import exceeds 16 MiB")
                        }
                        Ok(json!({"data":String::from_utf8(bytes)?}).to_string())
                    })()
                    .map_err(|e| Exception::throw_message(&ctx, &format!("{e:#}")))
                },
            )?,
        )?;
        let initial = json!({"attachments":attachment_metadata,"repair_allowed":repair_allowed,"templates":pdf.templates,"trace":std::env::var("MPMB_TRACE_FIELDS").unwrap_or_default().split(',').collect::<Vec<_>>(),"bookmarks":pdf.bookmarks,"fields":pdf.fields,"order":pdf.order,"info":pdf.info,"file":pdf.path.file_name().unwrap().to_string_lossy(),"path":pdf.path,"pages":pdf.doc.get_pages().len()});
        ctx.globals().set(
            "__roundRichMetric",
            Function::new(ctx.clone(), round_rich_metric)?,
        )?;
        ctx.globals().set(
            "__normalizePdfText",
            Function::new(ctx.clone(), normalize_pdf_text)?,
        )?;
        ctx.globals().set("__initial", initial.to_string())?;
        ctx.eval::<(), _>(concat!(include_str!("acrobat.js"), "\nvoid 0;"))
            .map_err(|e| anyhow!("Acrobat host: {e}: {:?}", ctx.catch()))?;
        for (name, code) in &pdf.scripts {
            Self::eval_in(&ctx, code)
                .with_context(|| format!("original document script {name}"))?;
        }
        Self::eval_in(&ctx, "__host.applyQualifiedRepairs()")?;
        let diagnostics: Value =
            serde_json::from_str(&Self::raw_in(&ctx, "__host.diagnostics()")?)?;
        if diagnostics["errors"]
            .as_array()
            .is_some_and(|e| !e.is_empty())
        {
            bail!(
                "original initialization reported errors: {}",
                diagnostics["errors"]
            )
        }
        Ok(pdf.scripts.len())
    }
    pub fn eval(&self, s: &str) -> Result<Value> {
        self.js.with(|ctx| Self::eval_in(&ctx, s))
    }
    fn eval_in(ctx: &Ctx<'_>, s: &str) -> Result<Value> {
        // Preserve stack traces, including exceptions caught by original sheet code in diagnostics.
        let quoted = serde_json::to_string(s)?;
        let wrapped=format!("(function(){{try{{let v=(0,eval)({quoted});return JSON.stringify({{ok:true,value:v===undefined?null:v}})}}catch(e){{return JSON.stringify({{ok:false,error:String(e),stack:e.stack}})}}}})()");
        let reply: String = Self::raw_in(ctx, &wrapped)?;
        let v: Value = serde_json::from_str(&reply)?;
        if v["ok"] != true {
            return Err(anyhow!("{}\n{}", v["error"], v["stack"]));
        }
        Ok(v["value"].clone())
    }
    fn raw(&self, code: &str) -> Result<String> {
        self.js.with(|ctx| Self::raw_in(&ctx, code))
    }
    fn raw_in(ctx: &Ctx<'_>, code: &str) -> Result<String> {
        ctx.eval::<String, _>(code)
            .map_err(|e| anyhow!("JavaScript engine: {e}: {:?}", ctx.catch()))
    }
    pub fn command(&self, code: &str) -> Result<()> {
        self.eval(&format!("__host.command({})", serde_json::to_string(code)?))?;
        Ok(())
    }
    pub fn ready(&self) -> Result<()> {
        self.eval("__host.ready()")?;
        Ok(())
    }
    pub fn snapshot(&self) -> Result<Value> {
        let s: String = self.raw("__host.snapshot()")?;
        Ok(serde_json::from_str(&s)?)
    }
    pub fn diagnostics(&self) -> Result<Value> {
        let s: String = self.raw("__host.diagnostics()")?;
        let mut diagnostics: Value = serde_json::from_str(&s)?;
        let documents = self.documents.report();
        // A source can activate a qualified repair or encounter an original
        // error even when the target has neither. Retain UI disclosure and
        // probe failure evidence after the source is discarded.
        for group in ["open", "events"] {
            if let Some(records) = documents[group].as_array() {
                for record in records {
                    for key in ["repairs", "errors"] {
                        if let Some(items) = record["diagnostics"][key].as_array() {
                            for item in items {
                                let mut item = item.clone();
                                item["source_document"] = record["path"].clone();
                                diagnostics[key]
                                    .as_array_mut()
                                    .context("Invalid diagnostic array")?
                                    .push(item);
                            }
                        }
                    }
                }
            }
        }
        diagnostics["documents"] = documents;
        diagnostics["errors"]
            .as_array_mut()
            .context("Invalid diagnostic array")?
            .extend(
                self.documents
                    .services
                    .control_errors
                    .lock()
                    .unwrap()
                    .iter()
                    .cloned(),
            );
        Ok(diagnostics)
    }
    pub fn edit(&self, n: &str, v: &Value) -> Result<()> {
        self.eval(&format!("__host.edit({},{})", serde_json::to_string(n)?, v))?;
        Ok(())
    }
    pub fn user_edit(&self, n: &str, v: &Value) -> Result<()> {
        self.eval(&format!(
            "__host.userEdit({},{})",
            serde_json::to_string(n)?,
            v
        ))?;
        Ok(())
    }
    pub fn advance(&self, ms: u64) -> Result<()> {
        self.eval(&format!("__host.advance({ms})"))?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn imported_icon_tokens_copy_without_duplicate_payloads_and_failures_preserve_selection() {
        let engine = Engine::new().unwrap();
        let context = Context::full(&engine).unwrap();
        context.with(|ctx| {
            let button=json!({"kind":"Btn","flags":65536,"value":"","default_value":"","items":[],"widgets":[],"actions":{}});
            ctx.globals().set("__initial",json!({"fields":{"Portrait":button,"Copy":button},"order":[],"info":{},"bookmarks":{"children":[]},"pages":1,"templates":{}}).to_string()).unwrap();
            ctx.eval::<(),_>(concat!(include_str!("acrobat.js"),"\nvoid 0;")).unwrap();
            let result=ctx.eval::<bool,_>(r#"globalThis.__iconImport=function(){return JSON.stringify({code:0,asset:{id:'fixture',pdf_hex:'00'}})};var a=getField('Portrait'),b=getField('Copy');var imported=a.buttonImportIcon('alpha.png')===0;var token=a.buttonGetIcon();b.buttonSetIcon(token);var first=JSON.parse(__host.snapshot());var rev=__host.revision;dirty=false;globalThis.__iconImport=function(){return JSON.stringify({code:1})};var cancelled=a.buttonImportIcon()===1;var preserved=__host.revision===rev&&!dirty&&JSON.parse(__host.snapshot()).Portrait.icon.asset==='fixture';globalThis.__iconImport=function(){return JSON.stringify({code:-1})};var failed=a.buttonImportIcon('missing.png')===-1;var rejected=false;try{b.buttonSetIcon({asset:{id:'fixture',pdf_hex:'00'}})}catch(e){rejected=true}imported&&cancelled&&preserved&&failed&&rejected&&first.Copy.icon.asset==='fixture'&&Object.keys(first.__iconAssets).length===1"#).unwrap();assert!(result);
        });
    }
    #[test]
    fn metadata_standard_aliases_preserve_custom_case_and_pdf_date_types() {
        host(
            r#"var metadata=__docInfo({Title:'MPMB sheet',SheetVersion:'24.2.0',CreationDate:"D:20160527130739+02'00'"});
          var date=metadata.creationdate;date.setUTCFullYear(1999);
          metadata.title==='MPMB sheet' && metadata.TITLE===metadata.Title &&
          metadata.SheetVersion==='24.2.0' && metadata.sheetversion==='' && metadata.SHEETVERSION==='' &&
          metadata.MissingMetadata==='' && metadata.author==='' &&
          Object.keys(metadata).sort().join(',')==='CreationDate,SheetVersion,Title' &&
          metadata.CREATIONDATE instanceof Date &&
          metadata.CreationDate.getTime()===Date.UTC(2016,4,27,11,7,39) &&
          __pdfInfoDate("D:20240102030405-04'30'").getTime()===Date.UTC(2024,0,2,7,34,5) &&
          isNaN(__pdfInfoDate('D:20230230Z').getTime())"#,
        );
    }
    #[test]
    fn metadata_custom_scalars_and_standard_author_array_match_reader() {
        host(
            r#"var m=__docInfo({Authors:['Alex','Beta'],ContactEmail:'test@example.test',Build:'0012',TrueValue:'true',FalseValue:'false',Fraction:'-.5',Trailing:'12.',Exponent:'1e3',Space:' 42 ',Newline:'1\n'});
          var authors=m.authors;authors[0]='changed';
          m.AUTHORS.join(',')==='Alex,Beta'&&m.contactemail==='test@example.test'&&m.Build===12&&m.build===''&&m.TrueValue===true&&m.FalseValue===false&&m.Fraction===-0.5&&m.Trailing===12&&m.Exponent==='1e3'&&m.Space===' 42 '&&m.Newline==='1\n'"#,
        );
    }
    #[test]
    fn metadata_mutations_fail_instead_of_pretending_to_persist() {
        host("var metadata=__docInfo({Title:'original'}),rejected=false;try{metadata.title='changed'}catch(e){rejected=/metadata mutation/.test(String(e))}rejected&&metadata.Title==='original'");
    }
    #[test]
    fn commit_action_exceptions_are_recorded_without_aborting_setters_or_resets() {
        host("var f=getField('A'),ok=true;for(var kind of ['Keystroke','Validate','Format']){for(var type of ['Keystroke','Validate','Format'])f.setAction(type,'');f.value='baseline';f.defaultValue='default';f.setAction(kind,\"throw Error('field exception sentinel')\");try{f.value='changed';ok=ok&&f.valueAsString==='changed';resetForm(['A']);ok=ok&&f.valueAsString==='default'}catch(e){ok=false}}ok&&JSON.parse(__host.diagnostics()).errors.length===6");
    }
    #[test]
    fn string_resets_used_by_original_feat_removal_commit_and_leave_other_fields_intact() {
        host("app.calculate=false;var f=getField('A'),trace=[];f.defaultValue='default';getField('B').value='unrelated';f.setAction('Keystroke',\"trace.push('K')\");f.setAction('Validate',\"trace.push('V')\");f.setAction('Format',\"trace.push('F')\");resetForm('A');var first=trace.join('');resetForm('nonexistent');first==='KVF'&&trace.join('')==='KVF'&&f.valueAsString==='default'&&getField('B').valueAsString==='unrelated'&&JSON.parse(__host.diagnostics()).errors.length===0");
    }
    #[test]
    fn unimplemented_host_calls_remain_explicit_failures_inside_field_actions() {
        host("var f=getField('A'),rejected=false;f.setAction('Format',\"__host.unsupported('test missing host method')\");try{f.value='changed'}catch(e){rejected=/Unsupported Acrobat API/.test(String(e))}rejected&&JSON.parse(__host.diagnostics()).errors.length===1");
    }
    #[test]
    fn exception_diagnostics_do_not_throw_on_null_or_unavailable_stack_getters() {
        host("var f=getField('A'),ok=true;f.setAction('Format','throw null');try{f.value='first'}catch(e){ok=false}f.setAction('Format',\"var problem=Error('source exception');Object.defineProperty(problem,'stack',{get(){throw Error('stack unavailable')}});throw problem\");try{f.value='second'}catch(e){ok=false}var records=JSON.parse(__host.diagnostics()).errors;ok&&f.valueAsString==='second'&&records.length===2&&records[0].error==='null'&&records[1].stack.getter_error==='Error: stack unavailable'");
    }
    #[test]
    fn scripted_selections_reject_absent_ambiguous_and_disabled_options() {
        let request = json!({"values":{"list":{"group":{"A":-4,"B":2}}}});
        let mut reply = json!({"select":{"list":"A"}});
        select_dialog_options(&request, &mut reply).unwrap();
        assert_eq!(reply["values"]["list"], json!({"group":{"A":4,"B":-2}}));
        assert!(
            select_dialog_options(&request, &mut json!({"select":{"list":"missing"}})).is_err()
        );
        assert!(select_dialog_options(
            &json!({"values":{"list":{"g1":{"A":-1},"g2":{"A":-2}}}}),
            &mut json!({"select":{"list":"A"}})
        )
        .is_err());
        assert!(select_dialog_options(
            &json!({"enabled":{"list":false},"values":request["values"]}),
            &mut json!({"select":{"list":"A"}})
        )
        .is_err());
    }
    #[test]
    fn qualified_dialog_paths_disambiguate_duplicate_subclass_labels() {
        let request =
            json!({"values":{"ExcL":{"Ranger":{"Hunter":-2},"Revised Ranger":{"Hunter":-5}}}});
        let mut reply = json!({"select":{"ExcL":["Revised Ranger","Hunter"]}});
        select_dialog_options(&request, &mut reply).unwrap();
        assert_eq!(
            reply["values"]["ExcL"],
            json!({"Ranger":{"Hunter":-2},"Revised Ranger":{"Hunter":5}})
        );
        for path in [
            json!([]),
            json!(["Hunter"]),
            json!(["Missing", "Hunter"]),
            json!([1, "Hunter"]),
        ] {
            assert!(select_dialog_options(&request, &mut json!({"select":{"ExcL":path}})).is_err());
        }
    }
    #[test]
    fn button_paths_resolve_real_controls_and_reject_ambiguous_or_disabled_choices() {
        let mut request = json!({"description":{"elements":[{"type":"cluster","item_id":"parent","name":"Fighting Style","elements":[{"type":"button","item_id":"one","name":"✓ Archery   \t[PHB 72]"}]}]},"enabled":{},"visible":{}});
        let mut reply = json!({"button_path":["Fighting Style","Archery"]});
        select_dialog_button(&request, &mut reply).unwrap();
        assert_eq!(reply["event"], "one");
        request["enabled"]["parent"] = json!(false);
        assert!(select_dialog_button(&request, &mut reply).is_err());
        request["enabled"]["parent"] = json!(true);
        request["description"]["elements"][0]["elements"]
            .as_array_mut()
            .unwrap()
            .push(json!({"type":"button","item_id":"two","name":"Archery"}));
        assert!(select_dialog_button(&request, &mut reply).is_err());
        assert!(select_dialog_button(
            &request,
            &mut json!({"button_path":["Fighting Style","Absent"]})
        )
        .is_err());
    }
    #[test]
    fn scripted_alerts_require_a_real_button_and_matching_title() {
        let request = json!({"cTitle":"Creating a Sidekick Works Differently","nType":2,"oCheckbox":{"bInitialValue":true}});
        assert!(scripted_alert_response(&request, &json!(1)).is_err());
        assert_eq!(
            scripted_alert_response(
                &request,
                &json!({"title":"Creating a Sidekick Works Differently","button":4})
            )
            .unwrap(),
            json!({"button":4,"checked":true})
        );
        assert!(
            scripted_alert_response(&request, &json!({"title":"Other warning","button":4}))
                .is_err()
        );
        assert_eq!(
            scripted_alert_response(&request, &json!(3)).unwrap()["button"],
            3
        );
    }
    fn host(test: &str) {
        let engine = Engine::new().unwrap();
        engine.set_max_stack_size(1024 * 1024);
        let context = Context::full(&engine).unwrap();
        context.with(|ctx|{
            ctx.globals().set("__roundRichMetric",Function::new(ctx.clone(),round_rich_metric).unwrap()).unwrap();
            ctx.globals().set("__normalizePdfText",Function::new(ctx.clone(),normalize_pdf_text).unwrap()).unwrap();
            ctx.globals().set("__xfdfRich",Function::new(ctx.clone(),decode_xfdf_rich).unwrap()).unwrap();
            let field=|name:&str,value:&str,actions:Value|json!({"name":name,"value":value,"default_value":"","user_name":"","submit_name":"","kind":"Tx","flags":0,"display":0,"text_size":10,"widgets":[],"items":[],"actions":actions});
            ctx.globals().set("__initial",json!({"fields":{"A":field("A","2",json!({"V":"if (Number(event.value)<0) event.rc=false;"})),"B":field("B","0",json!({"C":"event.value=getField('A').value+1;"})),"C":field("C","0",json!({"C":"event.value=getField('B').value+1;"})),"Choice":json!({"name":"Choice","kind":"Ch","flags":131072,"value":"Quarterstaff","default_value":"","items":[],"widgets":[],"actions":{}}),"Unchecked":json!({"kind":"Btn","flags":0,"value":"Off","default_value":"","items":[],"widgets":[],"actions":{},"export_values":["True"]})},"order":["B","C"],"info":{},"bookmarks":{"children":[]},"pages":1,"templates":{"blank":{"fields":{},"order":[]}}}).to_string()).unwrap();
            ctx.eval::<(),_>(concat!(include_str!("acrobat.js"),"\nvoid 0;")).unwrap();
            let result=ctx.eval::<bool,_>(test);if result.is_err(){panic!("{:?}",ctx.catch());}assert!(result.unwrap());
        });
    }
    #[test]
    fn xfdf_import_batches_document_events_and_rejects_invalid_commits() {
        host(
            r#"var trace=[];
          getField('A').setAction('Keystroke',"trace.push(['K',event.source,event.value,getField('B').value]);");
          getField('A').setAction('Format',"trace.push(['F',event.source,event.value,getField('B').value]);");
          getField('B').setAction('Calculate',"trace.push(['C',event.source,getField('A').value,getField('C').value]);event.value=getField('A').value+1;");
          __host.importXFDF({fields:[{name:'A',values:['8'],rich_xml:null},{name:'C',values:['50'],rich_xml:null},{name:'absent',values:['ignored'],rich_xml:null}]});
          var first=JSON.stringify(trace.slice(0,3))===JSON.stringify([['K',null,'8',0],['F',null,'8',0],['C',null,8,50]]);if(!first)throw Error(JSON.stringify(trace));
          __host.importXFDF({fields:[{name:'A',values:['-1'],rich_xml:null}]});
          first&&getField('A').value===8&&getField('B').value===9&&getField('C').value===10"#,
        );
    }
    #[test]
    fn xfdf_rich_import_exposes_incoming_spans_and_preserves_validation_changes() {
        host(
            r#"var f=getField('A');f.richText=true;f.richValue=[{text:'old'}];var incoming;
          f.setAction('Validate',"incoming=event.richValue;var spans=event.richValue;spans[0].linespacing=11;event.richValue=spans;");
          __host.importXFDF({fields:[{name:'A',values:[],rich_xml:'<body xmlns="http://www.w3.org/1999/xhtml"><p><span style="font-size:9pt;font-weight:bold">new Ω</span></p></body>'}]});
          incoming[0].text==='new Ω'&&incoming[0].textSize===9&&incoming[0].fontWeight===700&&f.valueAsString==='new Ω'&&f.richValue[0].linespacing===11"#,
        );
    }
    #[test]
    fn xfdf_valueless_combo_refreshes_without_replacing_or_validating() {
        host(
            r#"var f=getField('Choice'),trace=[];f.setAction('Keystroke',"trace.push('K')");f.setAction('Validate',"trace.push('V')");f.setAction('Format',"trace.push([event.name,event.value,event.source])");
          __host.importXFDF({fields:[{name:'Choice',values:[],rich_xml:null}]});
          f.valueAsString==='Quarterstaff'&&JSON.stringify(trace)===JSON.stringify([['Format','Quarterstaff',null]])"#,
        );
    }
    #[test]
    fn xfdf_import_preflight_and_cancel_do_not_partially_mutate_fields() {
        host(
            r#"var before=getField('A').value,error=false;
          try{__host.importXFDF({fields:[{name:'A',values:['8'],rich_xml:null},{name:'B',values:[],rich_xml:null}]})}catch(e){error=true}
          __host.importXFDF({cancelled:true});error&&getField('A').value===before"#,
        );
    }
    #[test]
    fn explicit_calculation_respects_enable_flags_independently_of_display_delay() {
        host(
            r#"var f=getField('A'),count=0,good=true;getField('B').setAction('Calculate','');getField('C').setAction('Calculate','');f.value='seed';f.setAction('Calculate',"count++;event.value=String(count)");
        for(var a=0;a<2;a++)for(var d=0;d<2;d++)for(var v=0;v<2;v++){app.calculate=!!a;calculate=!!d;delay=!!v;count=0;calculateNow();good=good&&count===(a&&d?1:0);}
        app.calculate=true;calculate=true;delay=false;good"#,
        );
    }
    #[test]
    fn preserved_non_leaf_calculation_slots_count_without_executing() {
        host(
            r#"__host.data.order.splice(1,0,{reference:[99,0]});var a=getField('A'),b=getField('B'),c=getField('C');
        a.setAction('Validate','');a.setAction('Calculate',"event.value='7'");
        var indices=b.calcOrderIndex===0&&c.calcOrderIndex===2&&a.calcOrderIndex===3;
        calculateNow();var executed=a.value===7;
        b.setAction('Calculate','');var state=JSON.parse(__host.snapshot());
        indices&&executed&&b.calcOrderIndex===-1&&c.calcOrderIndex===1&&a.calcOrderIndex===2&&state.__order[0].reference[0]===99"#,
        );
    }
    #[test]
    fn calculate_action_registration_removal_and_readdition_drive_dependencies() {
        host(
            r#"var a=getField('A'),b=getField('B'),c=getField('C');
        a.setAction('Validate','');a.setAction('Calculate',"event.value='7'");
        var appended=a.calcOrderIndex===2&&b.calcOrderIndex===0&&c.calcOrderIndex===1;
        b.setAction('Calculate','');a.setAction('Calculate',"event.value='9'");
        var retained=a.calcOrderIndex===1&&b.calcOrderIndex===-1&&c.calcOrderIndex===0;
        b.setAction('Calculate',"event.value=Number(getField('A').value)+2");
        a.setAction('Calculate','');a.setAction('Calculate',"event.value='11'");
        var readded=c.calcOrderIndex===0&&b.calcOrderIndex===1&&a.calcOrderIndex===2;
        a.calcOrderIndex=0;calculateNow();
        var calculated=a.value===11&&b.value===13;
        a.setAction('Calculate','');var old=a.value;calculateNow();
        appended&&retained&&readded&&calculated&&a.calcOrderIndex===-1&&a.value===old&&JSON.parse(__host.snapshot()).__order.indexOf('A')===-1"#,
        );
    }
    #[test]
    fn decoration_commits_preserve_default_inheritance_and_raw_event_values() {
        host(
            r#"var f=getField('A');f.richText=true;var base=f.defaultStyle;
        f.defaultStyle=Object.assign({},base,{underline:true,strikethrough:true});
        f.richValue=[{text:'inherited',underline:false,strikethrough:false}];
        var inherited=f.richValue[0];
        f.richValue=[{text:'clear',underline:'none'}];var cleared=f.richValue[0];
        var conversions=true;
        [true,1,2,-1,0.5,'1','true'].forEach(function(v){f.defaultStyle=Object.assign({},base,{underline:v,strikethrough:v});conversions=conversions&&f.defaultStyle.underline==='underline'&&f.defaultStyle.strikethrough===true;});
        [false,0,'2','underline','none',null,undefined,[1],{}].forEach(function(v){f.defaultStyle=Object.assign({},base,{underline:v,strikethrough:v});conversions=conversions&&!('underline' in f.defaultStyle)&&!('strikethrough' in f.defaultStyle);});
        f.defaultStyle=base;var immediate;
        f.setAction('Validate',"event.richValue=[{text:'event',underline:true,strikethrough:false}];immediate=event.richValue;");
        f.value='input';
        conversions&&inherited.underline==='underline'&&inherited.strikethrough===true&&cleared.underline===''&&cleared.strikethrough===false&&immediate[0].underline===true&&immediate[0].strikethrough===false&&f.richValue[0].underline==='underline'&&!('strikethrough' in f.richValue[0])"#,
        );
    }
    #[test]
    fn rich_span_metrics_use_reader_decimal_rounding() {
        host("var f=getField('A');f.richText=true;var sizes=[7.25,7.9,8.05,8.5,8.9,9.5,8.049999999999999];var expected=[7.2,7.9,8.1,8.5,8.9,9.5,8];var good=true;sizes.forEach(function(size,i){f.richValue=[{text:'metric',textSize:size,linespacing:14.75}];good=good&&f.richValue[0].textSize===expected[i]&&f.richValue[0].linespacing===14.8;});f.setAction('Format','event.richValue=[{text:\"formatted\",textSize:8.049999999999999,linespacing:7.25}]');f.value='stored';var span=JSON.parse(__host.snapshot()).A.richValue[0];good&&span.textSize===8&&span.linespacing===7.2");
    }
    #[test]
    fn field_event_value_writes_convert_numbers_and_reject_other_types_without_commit() {
        host(
            r#"app.calculate=false;var seen=[],valid=true;
          ['Keystroke','Validate','Format','Calculate'].forEach(function(kind){
            var f=getField(kind==='Calculate'?'B':'A');
            f.setAction(kind,"event.value=-1;seen.push([typeof event.value,event.value]);var bad=[true,false,null,undefined,[],{},new Number(2),new String('text')];bad.forEach(function(value){try{event.value=value;valid=false}catch(error){valid=valid&&error.name==='InvalidSetError'&&event.value==='-1'}});");
            if(kind==='Calculate'){app.calculate=true;calculateNow();app.calculate=false;}else f.value='next '+kind;
            f.setAction(kind,'');
          });
          valid&&seen.length===4&&seen.every(function(item){return item[0]==='string'&&item[1]==='-1'})&&getField('B').value===-1&&getField('B').valueAsString==='-1'"#,
        );
    }
    #[test]
    fn plain_validation_must_write_to_commit_a_keystroke_replacement() {
        host(
            r#"app.calculate=false;var f=getField('A'),validated,formatted;
          f.setAction('Keystroke',"event.value='K replacement'");
          f.setAction('Validate',"validated=event.value");
          f.setAction('Format',"formatted=event.value");f.value='requested';
          var observed=validated==='K replacement'&&formatted==='requested'&&f.valueAsString==='requested';
          f.setAction('Validate',"event.value=event.value");f.value='second';var same=f.valueAsString==='K replacement';
          f.setAction('Validate',"event.value='V replacement'");f.value='third';var replaced=f.valueAsString==='V replacement';
          f.setAction('Validate',"event.rc=false");f.value='rejected';var rejected=f.valueAsString==='V replacement';
          f.setAction('Validate','');f.value='fourth';observed&&same&&replaced&&rejected&&f.valueAsString==='K replacement'"#,
        );
    }
    #[test]
    fn calculated_mirror_validation_reenters_primary_commit_and_formats_in_order() {
        host(
            r#"var f=getField('A'),trace=[],candidate='A\u00a0B';app.calculate=false;f.setAction('Validate','');f.value='seed';
          f.setAction('Keystroke',"trace.push(['K',event.value]);event.value=candidate");
          f.setAction('Format',"trace.push(['F',event.value])");
          getField('B').setAction('Calculate',"trace.push(['C']);event.value=getField('A').valueAsString");getField('B').setAction('Validate',"if(event.value!==getField('A').valueAsString)getField('A').value=event.value");
          app.calculate=true;f.value='requested';
          var sequence=JSON.stringify(trace)===JSON.stringify([['K','requested'],['C'],['K','A B'],['F',candidate],['F',candidate]]);if(!sequence)throw Error(JSON.stringify(trace));
          app.calculate=false;trace=[];f.value='suspended';
          sequence&&JSON.stringify(trace)===JSON.stringify([['K','suspended'],['F',candidate]])&&f.valueAsString===candidate"#,
        );
    }
    #[test]
    fn original_order_and_numeric_values() {
        host("__host.edit('A','18'); getField('A').value===18 && getField('B').value===19 && getField('C').value===20 && getField('A').valueAsString==='18'");
    }
    #[test]
    fn pdfdoc_conversion_preserves_unicode_and_folds_only_narrow_text() {
        for (input, expected) in [
            ("A\u{a0}B", "A B"),
            ("€\u{a0}œ", "€ œ"),
            ("Ł\u{a0}ı", "Ł ı"),
            ("ﬁ\u{a0}ﬂ", "fi fl"),
            ("½\u{a0}µ", "½ µ"),
            ("A\u{a0}Ω", "A\u{a0}Ω"),
            ("Ā\u{a0}B", "Ā\u{a0}B"),
            ("\u{ad}\u{a0}B", "\u{ad}\u{a0}B"),
            ("ﬁ\u{a0}Ω", "ﬁ\u{a0}Ω"),
        ] {
            assert_eq!(normalize_pdf_text(input.into()), expected);
        }
    }
    #[test]
    fn rich_assignments_convert_each_span_then_commit_merged_text() {
        host(
            r#"var f=getField('A');f.richText=true;f.richValue=[{text:'A\u00a0B'},{text:'Ω'}];var merged=f.valueAsString==='A BΩ'&&f.richValue.length===1&&f.richValue[0].text==='A BΩ';f.richValue=[{text:'A\u00a0B',fontWeight:700},{text:'Ω',fontWeight:400}];var styles=f.valueAsString==='A BΩ'&&f.richValue.length===2&&f.richValue[0].text==='A B'&&f.richValue[0].fontWeight===700;f.richValue=[{text:'A\u00a0Ω'}];merged&&styles&&f.valueAsString==='A\u00a0Ω'&&f.richValue[0].text===f.valueAsString"#,
        );
    }
    #[test]
    fn rich_assignment_commit_events_expose_previous_spans_and_converted_new_text() {
        host(
            r#"var f=getField('A'),trace=[];f.richText=true;f.richValue=[{text:'old\u00a0Ω'}];f.setAction('Keystroke',"trace.push({name:event.name,value:event.value,rich:event.richValue.map(s=>s.text)});");f.setAction('Validate',"trace.push({name:event.name,value:event.value,rich:event.richValue.map(s=>s.text)});");f.richValue=[{text:'A\u00a0B'},{text:'Ω'}];f.valueAsString==='A BΩ'&&trace.length===2&&trace[0].name==='Keystroke'&&trace[1].name==='Validate'&&trace.every(e=>e.value==='A BΩ'&&e.rich.length===1&&e.rich[0]==='old\u00a0Ω')&&f.richValue[0].text==='A BΩ'"#,
        );
    }
    #[test]
    fn rejected_validation_does_not_change_value() {
        host("__host.edit('A','-5'); getField('A').value===2");
    }
    #[test]
    fn calculate_target_assignment_is_retained() {
        host("getField('B').setAction('Calculate','event.target.value=7');calculateNow();getField('B').value===7 && getField('C').value===8");
    }
    #[test]
    fn timers_are_chronological_and_cancellable() {
        host("var trace=[];var cancelled=app.setTimeOut('trace.push(99)',20);app.clearTimeOut(cancelled);app.setTimeOut(\"trace.push(1);app.setTimeOut('trace.push(2)',10)\",10);__host.advance(25);JSON.stringify(trace)==='[1,2]'");
    }
    #[test]
    fn serializer_preserves_functions_and_regular_expressions() {
        host("var a=eval(({regex:/wolf/i,fn:function(x){return x+1},arr:[undefined,null,2]}).toSource());a.regex.test('WOLF')&&a.fn(2)===3&&a.arr[0]===undefined");
    }
    #[test]
    fn serialized_string_values_and_keys_survive_pdf_text_field_normalization() {
        host(
            r#"var original={'key\u00a0name':'A\u00a0B\u2028C\ud83d\ude00'},f=getField('A');f.setAction('Validate','');var serialized=original.toSource();f.value=serialized;var restored=eval(f.valueAsString);!/[^\x00-\x7f]/.test(serialized)&&Object.keys(restored)[0]===Object.keys(original)[0]&&restored[Object.keys(original)[0]]===original[Object.keys(original)[0]]&&f.valueAsString===serialized"#,
        );
    }
    #[test]
    fn unsupported_api_is_observable() {
        host("var failed=false;try{getTemplate('blank').spawn(0,true,true)}catch(e){failed=String(e).includes('Unsupported Acrobat API')}failed&&JSON.parse(__host.diagnostics()).gaps.includes('Template.spawn overlay')");
    }
    #[test]
    fn acrobat_unmatched_replace_groups_are_empty_strings() {
        host("'x'.replace(/(x)(y)?/,function(all,a,b){return typeof b+':'+String(b)})==='string:'");
    }
    #[test]
    fn formatting_changes_appearance_without_changing_value() {
        host("getField('B').setAction('Format',\"event.value='+'+event.value\");calculateNow();var state=JSON.parse(__host.snapshot());state.B.value==='3'&&state.B.formatted==='+3'");
    }
    #[test]
    fn numeric_format_separators_do_not_change_the_value() {
        host("getField('B').setAction('Format','AFNumber_Format(2,0,0,0,\"\",false)');getField('A').value='1233.5';calculateNow();var state=JSON.parse(__host.snapshot());state.B.value==='1234.5'&&state.B.formatted==='1,234.50'");
    }
    #[test]
    fn unchecked_button_assignments_match_reader() {
        host("var f=getField('Unchecked');var initial=f.value==='Off'&&f.isBoxChecked(0)===0;f.value='';var blank=f.value==='Off';f.value='invalid';var invalid=f.value==='invalid'&&f.isBoxChecked(0)===0;f.checkThisBox(0,true);var on=f.value==='True'&&f.isBoxChecked(0)===1;f.value='';initial&&blank&&invalid&&on&&f.valueAsString==='Off'&&f.isBoxChecked(0)===0");
    }
    #[test]
    fn checkbox_uses_its_real_export_state() {
        host("var f=getField('A');f.exportValues=['0'];f.checkThisBox(0,true);String(f.value)==='0'&&f.isBoxChecked(0)===1&&(f.checkThisBox(0,false),f.value==='Off')");
    }
    #[test]
    fn choice_index_updates_the_export_value() {
        host("var f=getField('A');f.setItems([['nothing',' '],['Wis Mod','Wisdom']]);f.currentValueIndices=1;f.valueAsString==='Wis Mod'&&f.currentValueIndices===1");
    }
    #[test]
    fn pages_keep_inactive_widget_indices_and_rectangles_reject_inactive_widgets() {
        host("var f=getField('A');f._widgets=[{page:-1,rect:[1,2,20,30]},{page:2,rect:[1,2,20,30]}];var errors=0;try{f.rect}catch(e){if(String(e)==='InvalidGetError: Get not possible, invalid or unknown.')errors++}try{getField('A.0').rect}catch(e){if(e.name==='InvalidGetError')errors++}JSON.stringify(f.page)==='[-1,2]'&&errors===2&&getField('A.1').page===2&&JSON.stringify(getField('A.1').rect)==='[1,30,20,2]'");
    }
    #[test]
    fn rectangle_getters_quantize_to_fixed_point_without_mutating_source_geometry() {
        host("var f=getField('A');f._widgets=[{page:2,rect:[30.664100646972656,390.4129943847656,326.3550109863281,768.0960083007812]}];f.rect[0]===30.664108276367188&&f._widgets[0].rect[0]===30.664100646972656");
    }
    #[test]
    fn inactive_rectangle_writes_reject_without_mutating_widgets_or_revision() {
        host("var f=getField('A');f._widgets=[{page:-1,rect:[1,2,20,30]},{page:2,rect:[40,50,60,70]}];var before=JSON.stringify(f._widgets),revision=__host.revision,errors=0;[f,getField('A.0')].forEach(function(widget){try{widget.rect=[10,40,25,5]}catch(e){if(e.name==='InvalidSetError'&&e.message==='Set not possible, invalid or unknown.')errors++}});var rejected=errors===2&&JSON.stringify(f._widgets)===before&&__host.revision===revision;getField('A.1').rect=[41,80,65,52];rejected&&JSON.stringify(f._widgets[0].rect)==='[1,2,20,30]'&&JSON.stringify(f._widgets[1].rect)==='[41,52,65,80]'&&__host.revision===revision+1");
    }
    #[test]
    fn field_rect_uses_acrobat_top_bottom_order() {
        host("var f=getField('A');f._widgets=[{page:0,rect:[1,2,20,30]}];var correct=f.rect[1]===30;f.rect=[10,40,25,5];correct&&JSON.stringify(f._widgets[0].rect)==='[10,5,25,40]'");
    }
    #[test]
    fn indexed_rectangles_and_base_rectangle_change_only_the_selected_widget() {
        host("var f=getField('A');f._widgets=[{page:0,rect:[1,2,20,30]},{page:1,rect:[40,50,60,70]}];var second=getField('A.1'),before=JSON.stringify(second.rect);second.rect=[41,80,65,52];var firstUnchanged=JSON.stringify(f.rect)==='[1,30,20,2]';f.rect=[3,35,24,4];var copy=second.rect;copy[0]=999;var s=JSON.parse(__host.snapshot());before==='[40,70,60,50]'&&firstUnchanged&&JSON.stringify(s.A.widgets[0].rect)==='[3,4,24,35]'&&JSON.stringify(s.A.widgets[1].rect)==='[41,52,65,80]'");
    }
    #[test]
    fn spawned_widgets_rebuild_from_live_values_and_preserve_formatted_display() {
        host(
            r#"var definition=JSON.parse(__initial).fields.A;definition.widgets=[{page:0,id:[90,0],rect:[1,1,10,10]}];__host.data.templates.Test={fields:{A:definition},order:[]};
          var f=getField('A');f.setAction('Format',"event.value='Shown '+event.value");f.value='9';
          getTemplate('Test').spawn(1,true,false);var s=JSON.parse(__host.snapshot()),renamed=s['P1.Test.A'];
          var correct=renamed.value==='9'&&renamed.formatted==='Shown 9'&&renamed.appearanceDirty;
          getTemplate('Test').spawn(2,false,false);s=JSON.parse(__host.snapshot());correct&&s.A.value==='9'&&s.A.formatted==='Shown 9'&&s.A.appearanceDirty&&s.A.widgets.length===1"#,
        );
    }
    #[test]
    fn template_spawn_and_deletion_update_the_live_model() {
        host("var definition=JSON.parse(__initial).fields.A;definition.widgets=[{page:0,id:[90,0],rect:[1,1,10,10]}];__host.data.templates.Test={fields:{A:definition},order:[]};getTemplate('Test').spawn(1,true,false);var added=getField('P1.Test.A')!==null&&numPages===2;deletePages(1);added&&numPages===1&&getField('P1.Test.A')===null&&getField('A')!==null");
    }
    #[test]
    fn dialog_list_operations_and_ok_handler_are_committed() {
        host("var saved;globalThis.__dialog=function(){return JSON.stringify({result:'ok'})};__host.execDialog({description:{elements:[]},initialize:function(d){d.load({list:{A:-1}});d.insertEntryInList({list:{B:-2}});d.focus('list')},ok:function(d){saved=d.store().list},commit:function(d){d.removeAllEntriesFromList('list')}});saved.A===-1&&saved.B===-2");
    }
    #[test]
    fn rich_getters_copy_normalized_spans_and_string_assignments_only_format() {
        host("var f=getField('A');f.richText=true;f.richValue=[{text:'alpha\\u00a0beta',fontWeight:700},{text:'second',endParagraph:true}];var copy=f.richValue;copy[0].text='changed';var good=f.valueAsString==='alpha betasecond'&&f.richValue[0].text==='alpha beta'&&f.richValue[0].fontWeight===700&&!('endParagraph' in f.richValue[1]);var trace=[];f.setAction('Keystroke',\"trace.push('K')\");f.setAction('Validate',\"trace.push('V')\");f.setAction('Format',\"trace.push('F')\");f.richValue='';f.richValue='ignored';good&&f.valueAsString==='alpha betasecond'&&JSON.stringify(trace)==='[\"F\",\"F\"]'");
    }
    #[test]
    fn validate_plain_assignment_wins_and_rich_assignment_alone_commits() {
        host("var f=getField('A');f.richText=true;f.setAction('Validate',\"event.richValue=[{text:'rich',fontWeight:700}];\");f.value='input';var rich=f.valueAsString==='rich'&&f.richValue[0].fontWeight===700;f.setAction('Validate',\"event.value='plain';event.richValue=[{text:'ignored'}];\");f.value='input';var plain=f.valueAsString==='plain'&&f.richValue[0].fontWeight===400;f.setAction('Validate',\"event.richValue=[{text:'ignored'}];event.value='last';\");f.value='input';rich&&plain&&f.valueAsString==='last'");
    }
    #[test]
    fn json_host_boundary_preserves_reader_fixed_point_color() {
        let value: Value = serde_json::from_str("0.9960784912109375").unwrap();
        assert_eq!(value.as_f64().unwrap(), 65279.0 / 65536.0);
    }
    #[test]
    fn rich_colors_use_reader_fixed_input_truncation_and_getter_reassignment() {
        host("var f=getField('A');f.richText=true;f.richValue=[{text:'skill',textColor:['RGB',.658,.654,.2]}];var first=JSON.stringify(f.richValue[0].textColor)==='[\"RGB\",0.6549072265625,0.6509857177734375,0.196075439453125]';f.richValue=f.richValue;first&&JSON.stringify(f.richValue[0].textColor)==='[\"RGB\",0.6549072265625,0.6509857177734375,0.1921539306640625]'");
    }
    #[test]
    fn rich_formatting_changes_display_without_replacing_stored_text_or_spans() {
        host("var f=getField('A');f.richText=true;f.setAction('Format',\"event.richValue=[{text:'display',fontWeight:700}];\");f.value='stored';var s=JSON.parse(__host.snapshot()).A;var rich=f.valueAsString==='stored'&&f.richValue[0].text==='stored'&&s.rawRichValue[0].text==='stored'&&s.richValue[0].text==='display'&&s.richRenderActive;f.setAction('Format',\"event.value='plain display';event.richValue=[{text:'ignored'}];\");f.value='next';s=JSON.parse(__host.snapshot()).A;rich&&f.valueAsString==='next'&&s.formatted==='plain display'&&!s.richRenderActive");
    }
    #[test]
    fn calculate_cross_field_unchanged_assignment_formats_synchronously() {
        host(
            r#"app.calculate=false;var a=getField('A'),trace=[],operand=15;a.valueCalculated=10;a.setAction('Format',"trace.push('F'+event.target.valueCalculated);event.value=event.target.valueCalculated;");a.value='formula';getField('B').setAction('Calculate',"trace.push('C-start');var other=getField('A');other.valueCalculated=operand;other.value=other.value;trace.push('C-end');event.value=0;");app.calculate=true;calculateNow();var state=JSON.parse(__host.snapshot()).A;state.value==='formula'&&state.formatted==='15'&&trace.join(',')==='F10,C-start,F15,C-end'&&JSON.parse(__host.diagnostics()).errors.length===0"#,
        );
    }
    #[test]
    fn formatted_display_invalidates_appearance_without_changing_canonical_value() {
        host("var f=getField('A');var offset=10;f.setAction('Format','event.value=Number(event.value)+offset');f.value=2;f._appearanceDirty=false;offset=20;f.value=2;var s=JSON.parse(__host.snapshot()).A;s.value==='2'&&s.formatted==='22'&&s.appearanceDirty");
    }
    #[test]
    fn rich_format_invalidation_survives_an_unchanged_value_commit() {
        host("var f=getField('A');f.richText=true;var label='one';f.setAction('Format','event.richValue=[{text:label}]');f.value='stored';f._appearanceDirty=false;label='two';f.value='stored';var s=JSON.parse(__host.snapshot()).A;s.value==='stored'&&s.rawRichValue[0].text==='stored'&&s.richValue[0].text==='two'&&s.appearanceDirty");
    }
    #[test]
    fn partial_default_style_replaces_omitted_properties_and_keeps_existing_spans() {
        host("var f=getField('A');f.richText=true;f.textFont='Courier';f.value='existing';var spans=JSON.stringify(f.richValue);f.defaultStyle={textSize:9,alignment:'right',textColor:['RGB',0,0,1]};f.textFont==='Helvetica'&&f.textSize===9&&f.defaultStyle.fontFamily[0]==='Helvetica'&&f.alignment==='right'&&JSON.stringify(f.richValue)===spans");
    }
    #[test]
    fn empty_default_style_separates_default_size_from_auto_field_size() {
        host("var f=getField('A');f.richText=true;f.defaultStyle={};f.textFont==='Helvetica'&&f.textSize===0&&f.defaultStyle.textSize===12&&f.alignment==='left'&&JSON.stringify(f.textColor)==='[\"G\",0]'&&JSON.stringify(f.defaultStyle.textColor)==='[\"RGB\",0,0,0]'");
    }
    #[test]
    fn rich_event_getters_are_copies_and_plain_getters_raise_reader_error() {
        host("var f=getField('A');f.richText=true;f.setAction('Validate',\"var copy=event.richValue;copy[0].text='ignored';\");f.value='original';var good=f.valueAsString==='original';f.setAction('Validate','');f.setAction('Keystroke',\"event.richValue=[{text:'keystroke'}];\");var seen='';f.setAction('Validate',\"seen=event.richValue[0].text;\");f.richValue=[{text:'styled',fontWeight:700}];good=good&&seen==='keystroke'&&f.valueAsString==='styled'&&f.richValue[0].fontWeight===700;f.setAction('Keystroke','');f.setAction('Validate','');f.richText=false;var raised=false;try{f.richValue}catch(e){raised=String(e)==='InvalidGetError: Get not possible, invalid or unknown.'}good&&raised&&JSON.parse(__host.snapshot()).A.richValue.length===0");
    }
    #[test]
    fn default_style_is_copied_coupled_and_formats_after_unchanged_assignments() {
        host("var f=getField('A');f.richText=true;f.defaultStyle={alignment:'left',fontFamily:['Helvetica','sans-serif'],fontStretch:'normal',fontStyle:'normal',fontWeight:400,textColor:['RGB',0,0,0],textSize:10};var formats=0;f.setAction('Format','formats++');var copy=f.defaultStyle;copy.fontFamily[0]='changed';copy.textSize=99;var copied=f.defaultStyle.fontFamily[0]==='Helvetica'&&f.defaultStyle.textSize===10;f.textSize=9;f.textSize=9;f.textFont='Helvetica';f.textColor=['RGB',0.25,0.5,0.75];f.alignment='right';var s=f.defaultStyle,coupled=s.textSize===9&&s.alignment==='right'&&JSON.stringify(s.textColor)==='[\"RGB\",0.2509765625,0.5019683837890625,0.7490234375]'&&formats===5;f.defaultStyle={alignment:'center',fontFamily:['Helvetica','sans-serif'],fontStretch:'normal',fontStyle:'italic',fontWeight:700,textColor:['RGB',1,0,0],textSize:11};var assigned=f.textSize===11&&f.textFont==='Helvetica-BoldOblique'&&f.alignment==='center'&&formats===6;f.richText=false;var unavailable=false;try{f.defaultStyle}catch(e){unavailable=String(e)==='InvalidGetError: Get not possible, invalid or unknown.'}copied&&coupled&&assigned&&unavailable");
    }
    #[test]
    fn popup_edit_combos_store_selected_text_while_lists_retain_maps() {
        host("var rows=[];globalThis.__dialog=()=>JSON.stringify({result:'ok'});__host.execDialog({description:{elements:[{type:'edit_text',item_id:'ed01',PopupEdit:true},{type:'edit_text',item_id:'ed02',PopupEdit:true,SpinEdit:true},{type:'edit_text',item_id:'ed03',PopupEdit:true,SpinEdit:true},{type:'popup',item_id:'pop1'},{type:'list_box',item_id:'list'}]},initialize(d){d.load({ed01:{Alpha:-1,Beta:2},ed02:{Alpha:-1,Beta:2},ed03:'Beta',pop1:{Alpha:-1,Beta:2},list:{Alpha:-1,Beta:2}});var copy=d.store();copy.list.Beta=99;rows.push(d.store())},commit(d){rows.push(d.store())}});rows.length===2&&rows.every(r=>r.ed01===''&&r.ed02==='Beta'&&r.ed03===''&&r.pop1.Beta===2&&r.list.Beta===2)");
    }
    #[test]
    fn dialog_defaults_exist_before_initialize_and_preserve_reader_types() {
        host(
            r#"var seen;globalThis.__dialog=function(){return JSON.stringify({result:'ok'})};__host.execDialog({description:{elements:[{type:'edit_text',item_id:'text',name:'7'},{type:'edit_text',item_id:'spin',name:'7',SpinEdit:true},{type:'edit_text',item_id:'none',SpinEdit:true},{type:'edit_text',item_id:'read',name:'9',SpinEdit:true,readonly:true},{type:'edit_text',item_id:'comb',name:'8',SpinEdit:true,PopupEdit:true},{type:'static_text',item_id:'stat',name:'Label'},{type:'check_box',item_id:'chek',name:'Check'},{type:'radio',item_id:'radi',name:'Radio'},{type:'button',item_id:'butn',name:'Button'}]},initialize(d){seen=d.store();d.load({text:'11'})},commit(d){var r=d.store();seen.loaded=r.text}});seen.text===''&&seen.spin==='0'&&seen.none==='0'&&seen.read===''&&seen.comb===''&&seen.stat==='Label'&&seen.chek===false&&seen.radi===false&&seen.loaded==='11'&&!Object.prototype.hasOwnProperty.call(seen,'butn')"#,
        );
    }
    #[test]
    fn dialog_destroy_runs_after_commit_cancel_and_custom_end() {
        host("var trace=[],reply={result:'ok'};globalThis.__dialog=()=>JSON.stringify(reply);var def={description:{elements:[]},commit(){trace.push('commit')},cancel(){trace.push('cancel')},destroy(){trace.push('destroy')},other(d){d.end('save')}};__host.execDialog(def);reply={result:'cancel'};__host.execDialog(def);reply={result:'other'};var result=__host.execDialog(def);result==='save'&&JSON.stringify(trace)==='[\"commit\",\"destroy\",\"cancel\",\"destroy\",\"destroy\"]'");
    }
    #[test]
    fn popup_menu_returns_the_original_leaf_command() {
        host("globalThis.__dialog=function(){return JSON.stringify({event:'menu1'})};app.popUpMenuEx({cName:'Pages',oSubMenu:[{cName:'Companion',cReturn:'template#AScomp#add'}]})==='template#AScomp#add'");
    }
    #[test]
    fn cancelled_popup_returns_null_for_original_mpmb_get_menu() {
        host("globalThis.__dialog=function(){return JSON.stringify({result:'cancel'})};var value=app.popUpMenuEx({cName:'Spell options',cReturn:'move#down'});value===null&&(value===null?['nothing','toreport']:value.toLowerCase().split('#'))[0]==='nothing'");
    }
    #[test]
    fn copied_button_icon_survives_source_reassignment() {
        host("var a=getField('A'),b=getField('B');b.buttonSetIcon(a.buttonGetIcon());a.buttonSetIcon(getField('C').buttonGetIcon());b.buttonSetCaption('>',0);b.buttonSetCaption('>',1);b.buttonSetCaption('>',2);var s=JSON.parse(__host.snapshot());s.B.icon.field==='A'&&s.A.icon.field==='C'&&s.B.captions[2]==='>'&&b.buttonGetCaption(1)==='>'");
    }
    #[test]
    fn widget_activation_delivers_original_target_and_updates_checkbox() {
        host(
            r#"var f=getField('A');f.type='checkbox';f.exportValues=['True'];f.setAction('MouseDown',"globalThis.down=event.target.name");f.setAction('MouseUp',"globalThis.up=event.target.valueAsString");__host.activate('A');down==='A'&&up==='True'&&f.isBoxChecked(0)===1"#,
        );
    }
    #[test]
    fn field_focus_changes_and_user_commits_deliver_original_blur_actions() {
        host(
            r#"var trace=[],a=getField('A'),b=getField('B');b.setAction('Calculate','');a.setAction('OnFocus','trace.push(event.name+":"+event.target.name)');a.setAction('OnBlur','trace.push(event.name+":"+event.target.name);getField("B").value=Number(event.target.value)+10');a.setFocus();a.setFocus();getField('C').setFocus();var switched=b.value===12;__host.userEdit('A','18');switched&&b.value===28&&__host.data.focus===null&&JSON.stringify(trace)==='["Focus:A","Blur:A","Focus:A","Blur:A"]'"#,
        );
    }
    #[test]
    fn mouse_modifiers_reach_original_actions_without_leaking_to_next_click() {
        host(
            r#"var f=getField('A'),trace=[];getField('B').setAction('Calculate','');f.setAction('MouseDown','trace.push([event.shift,event.modifier])');f.setAction('MouseUp','trace.push([event.shift,event.modifier]);if(event.shift||event.modifier)getField("B").value="options";else getField("B").value="prepare"');__host.activate('A',0,{shift:true});var shifted=getField('B').value==='options';__host.activate('A',0,{modifier:true});__host.activate('A');shifted&&getField('B').value==='prepare'&&JSON.stringify(trace)==='[[true,false],[true,false],[false,true],[false,true],[false,false],[false,false]]'"#,
        );
    }
    #[test]
    fn modified_actions_are_in_the_authoritative_snapshot() {
        host("getField('B').setAction('Calculate','event.value=42');calculateNow();var s=JSON.parse(__host.snapshot());s.B.value==='42'&&s.B.actions.C==='event.value=42'&&s.A.actions===undefined");
    }
    #[test]
    fn bookmark_actions_deliver_target_restore_event_and_persist_removal() {
        host("var previous=event;bookmarkRoot.createChild({cName:'Parent',cExpr:\"getField('A').value=event.target.name;pageNum=2\"});var b=bookmarkRoot.children[0];b.createChild({cName:'Delete'});b.createChild({cName:'Keep',nIndex:1});b.children[0].remove();b.style=2;b.open=true;b.execute();var s=JSON.parse(__host.snapshot()).__bookmarks;event===previous&&getField('A').value==='Parent'&&pageNum===2&&s.children[0].children.length===1&&s.children[0].children[0].name==='Keep'&&s.children[0].style===2");
    }
    #[test]
    fn focus_selects_the_target_widget_page() {
        host("Array.prototype.find=function(){return -1};var f=getField('A');f._widgets=[{page:1},{page:2}];getField('A.1').setFocus();var exact=pageNum===2;f.setFocus();exact&&pageNum===1");
    }
    #[test]
    fn print_constants_match_qualified_reader_values() {
        host(
            r#"var p=getPrintParams();p.firstPage===0&&p.lastPage===0&&p.interactive===0&&p.DuplexType===1&&JSON.stringify(p.constants)==='{"interactionLevel":{"full":0,"automatic":1,"silent":2},"duplexTypes":{"Simplex":1,"DuplexFlipLongEdge":2,"DuplexFlipShortEdge":3}}'"#,
        );
    }
    #[test]
    fn null_and_undefined_are_text_and_numeric_keystrokes_can_reject_them() {
        host(
            r#"var f=getField('A');f.value=undefined;var text=f.value==='undefined';f.value=null;text=text&&f.value==='null';f.value='7';f.setAction('Keystroke',"event.rc=!isNaN(event.value)");f.value=undefined;text&&f.value===7"#,
        );
    }
    #[test]
    fn script_assignments_deliver_commit_keystrokes_before_string_validation() {
        host(
            r#"var f=getField('A'),trace=[];f.setAction('Keystroke',"trace.push([event.name,typeof event.value,event.value,event.willCommit]);event.rc=event.value!=='bad'");f.setAction('Validate',"trace.push([event.name,typeof event.value,event.value,event.willCommit])");f.value=17;f.value=17;f.value='bad';f.value===17&&JSON.stringify(trace)==='[["Keystroke","string","17",true],["Validate","string","17",false],["Keystroke","string","bad",true]]'"#,
        );
    }
    #[test]
    fn text_fields_coerce_arrays_before_snapshot() {
        host(
            r#"var f=getField('A');f.setAction('Validate','');f.value=['','P3.AScomp.'];var first=JSON.parse(__host.snapshot()).A.value;f.value=[''];first===',P3.AScomp.'&&JSON.parse(__host.snapshot()).A.value===''"#,
        );
    }
    #[test]
    fn attachment_descriptors_do_not_mutate_document_resources() {
        host(
            r#"__host.data.attachments=[{name:'FAQ.pdf',path:'FAQ.pdf',size:3}];var list=dataObjects;list[0].name='changed';var object=getDataObject('FAQ.pdf');object.size=0;dataObjects[0].name==='FAQ.pdf'&&getDataObject('FAQ.pdf').size===3"#,
        );
    }
    #[test]
    fn default_appearance_retains_canonical_numeric_spelling() {
        host("getField('A').value='+4';var s=JSON.parse(__host.snapshot());getField('A').value===4&&s.A.value==='+4'&&s.A.formatted==='+4'");
    }
    #[test]
    fn line_endings_are_normalized_before_commit_events() {
        host(
            r#"var f=getField('A'),seen=[];f.setAction('Keystroke','seen.push(event.value)');f.value='a\nb';f.value='a\r\nb';var plain=seen.length===1&&seen[0]==='a b';f.multiline=true;f.richText=true;f.value='a\nb';f.value='a\r\nb';plain&&f.valueAsString==='a\rb'&&seen.length===4&&seen[1]==='a b'&&seen[2]==='a\rb'&&seen[3]==='a\rb'"#,
        );
    }
    #[test]
    fn nonbreaking_spaces_normalize_before_plain_and_rich_commit_events() {
        host(
            r#"var f=getField('A'),seen=[];f.setAction('Keystroke','seen.push(event.value)');f.value='a\u00a0b\tc';var plain=seen[0]==='a b\tc'&&f.valueAsString==='a b\tc';f.multiline=true;f.richText=true;f.value='a\u00a0b\r\u00a0\u00a0indented';plain&&seen[1]==='a b\tc'&&seen[2]==='a b\r  indented'&&f.valueAsString==='a b\r  indented'"#,
        );
    }
    #[test]
    fn rich_text_mode_assignments_deliver_reader_commit_and_format_events() {
        host(
            r#"var f=getField('A'),seen=[];f.setAction('Keystroke',"seen.push('K')");f.setAction('Validate',"seen.push('V')");f.setAction('Format',"seen.push('F')");f.richText=false;f.richText=false;f.richText=true;f.richText=true;JSON.stringify(seen)==='["F","F","K","V","F","K","V","F"]'&&f.valueAsString==='2'"#,
        );
    }
    #[test]
    fn untouched_widgets_retain_print_bits_and_display_assignment_normalizes_them() {
        host("var f=getField('A');f._widgets=[{page:0,flags:134},{page:1,flags:130}];var s=JSON.parse(__host.snapshot());var kept=s.A.widgets[0].flags===134&&s.A.widgets[1].flags===130;f.display=display.hidden;kept&&f._widgets.every(w=>w.flags===134)&&f.display===display.hidden&&__host.pageWidgets(0).length===0");
    }
    #[test]
    fn indexed_display_changes_only_its_widget_and_survives_snapshot() {
        host("var f=getField('A');f._widgets=[{page:0,flags:132},{page:1,flags:132}];getField('A.1').display=display.hidden;var hidden=f._widgets[0].flags===132&&f._widgets[1].flags===134&&f.display===display.visible&&getField('A.1').display===display.hidden;f.display=display.noView;getField('A.1').display=display.noPrint;var s=JSON.parse(__host.snapshot());hidden&&s.A.widgets[0].flags===164&&s.A.widgets[1].flags===128&&__host.pageWidgets(0).length===0&&__host.pageWidgets(1)[0].name==='A'");
    }
}
