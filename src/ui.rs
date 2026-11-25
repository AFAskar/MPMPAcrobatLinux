mod state;
mod theme;

use crate::{pdf::Pdf, render::Renderer, runtime::Runtime};
use anyhow::{bail, Result};
use eframe::egui::{self, ColorImage};
use serde_json::{json, Value};
use state::{
    filter_fields, pdf_rect_to_screen, FieldFilter, ProjectionCache, SidebarTab, ZoomState,
};
use std::{
    collections::{BTreeMap, BTreeSet},
    io::{Read, Write},
    path::PathBuf,
    sync::{Arc, Mutex},
};
use theme::{Palette, ThemeMode};

// Use the release's position and keys: later movement/key releases in the
// same frame can already have changed InputState's final pointer/key state.
fn activation_input(events: &[egui::Event], rect: egui::Rect) -> Option<(egui::Pos2, Value)> {
    events.iter().rev().find_map(|event| match event {
        egui::Event::PointerButton {
            pos,
            button: egui::PointerButton::Primary,
            pressed: false,
            modifiers,
        } if rect.contains(*pos) => Some((
            *pos,
            json!({"shift":modifiers.shift,"modifier":modifiers.ctrl || modifiers.mac_cmd}),
        )),
        _ => None,
    })
}

fn page_widget_hit(widgets: &[Value], x: f32, y: f32) -> Option<Value> {
    widgets
        .iter()
        .rev()
        .find(|widget| {
            // MPMB uses large read-only push buttons for page artwork. They
            // remain visible, but must not intercept the editable fields drawn
            // over them (for example the Constitution score).
            if widget["type"] == "button" && widget["readonly"] == true {
                return false;
            }
            let rect = &widget["rect"];
            x >= rect[0].as_f64().unwrap_or(0.) as f32
                && x <= rect[2].as_f64().unwrap_or(0.) as f32
                && y >= rect[1].as_f64().unwrap_or(0.) as f32
                && y <= rect[3].as_f64().unwrap_or(0.) as f32
        })
        .cloned()
}

const TOOLBAR_IMPORT_SCRIPT_ACTION: &str = "if(ImportUserScriptFile())RunUserScript(false,false)";

pub fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.first().map(String::as_str) == Some("--dialog") {
        return dialog_process();
    }
    if matches!(
        args.first().map(String::as_str),
        Some("-h" | "--help" | "--version")
    ) {
        println!(
            "mpmb-reader {} — native desktop reader for MPMB Character Record Sheets\n\
             Usage: mpmb-reader [<sheet.pdf>] [--probe <scenario.json> <report.json>]\n\
             PDFium: auto-discovered (MPMB_PDFIUM overrides)\n\
             Theme: MPMB_THEME=dark|light",
            env!("CARGO_PKG_VERSION")
        );
        return Ok(());
    }
    let pdf_path = if let Some(first) = args.first() {
        PathBuf::from(first)
    } else {
        match crate::platform::open_file_dialog(
            "Open MPMB Character Sheet",
            "PDF documents",
            &["*.pdf"],
            None,
            false,
        ) {
            Ok(Some(chosen)) => chosen,
            Ok(None) => return Ok(()),
            Err(_) => {
                println!(
                    "mpmb-reader <sheet.pdf> [--probe <scenario.json> <report.json>]\n\
                     PDFium: auto-discovered (MPMB_PDFIUM overrides)\n\
                     Native UI: edit fields, class selection, page navigation and save a new copy."
                );
                return Ok(());
            }
        }
    };
    let pdf = Arc::new(Pdf::open(&pdf_path)?);
    if args.get(1).map(String::as_str) == Some("--probe") {
        let scenario: Value = serde_json::from_slice(&std::fs::read(
            args.get(2)
                .ok_or_else(|| anyhow::anyhow!("missing scenario"))?,
        )?)?;
        let report_path = args
            .get(3)
            .ok_or_else(|| anyhow::anyhow!("missing report"))?;
        let executable_calculations = pdf
            .order
            .iter()
            .filter(|entry| match entry {
                crate::pdf::CalculationEntry::Field(name) => {
                    pdf.fields.get(name).is_some_and(|field| {
                        field.actions.get("C").is_some_and(|code| !code.is_empty())
                    })
                }
                crate::pdf::CalculationEntry::Preserved { .. } => false,
            })
            .count();
        let mut report = json!({"passed":false,"stages":[],"script_count":pdf.scripts.len(),"field_count":pdf.fields.len(),"calculation_count":executable_calculations,"calculation_order_entries":pdf.order.len()});
        let result = (|| -> Result<()> {
            let runtime = Runtime::new(
                &pdf,
                scenario["dialogs"].as_array().cloned().unwrap_or_default(),
                scenario["alerts"].as_array().cloned().unwrap_or_default(),
                scenario["interactive"].as_bool().unwrap_or(false),
                scenario["print_output_dir"].as_str().map(PathBuf::from),
                scenario["attachment_output_dir"]
                    .as_str()
                    .map(PathBuf::from),
            )?;
            report["loaded_scripts"] = json!(runtime.loaded);
            if let Some(steps) = scenario["steps"].as_array() {
                for step in steps {
                    let result = match step["op"].as_str().unwrap_or("") {
                        "edit" => runtime
                            .edit(step["field"].as_str().unwrap_or(""), &step["value"])
                            .map(|_| Value::Null),
                        "user-edit" => runtime
                            .user_edit(step["field"].as_str().unwrap_or(""), &step["value"])
                            .map(|_| Value::Null),
                        "select-choice" => runtime
                            .select_choice(step["field"].as_str().unwrap_or(""), &step["value"])
                            .map(|_| Value::Null),
                        "eval" => runtime.eval(step["code"].as_str().unwrap_or("")),
                        "advance" => runtime
                            .advance(step["ms"].as_u64().unwrap_or(0))
                            .map(|_| Value::Null),
                        "assert" => {
                            let state = runtime.snapshot()?;
                            for (k, v) in step["values"]
                                .as_object()
                                .ok_or_else(|| anyhow::anyhow!("assert needs values"))?
                            {
                                if state[k]["value"]
                                    .as_str()
                                    .map(str::to_owned)
                                    .unwrap_or_else(|| state[k]["value"].to_string())
                                    != v.as_str()
                                        .map(str::to_owned)
                                        .unwrap_or_else(|| v.to_string())
                                {
                                    bail!("field {k}: got {}, expected {v}", state[k]["value"])
                                }
                            }
                            Ok(Value::Null)
                        }
                        "save" => {
                            runtime.ready()?;
                            pdf.save_new(
                                &runtime.snapshot()?,
                                std::path::Path::new(step["path"].as_str().unwrap_or("")),
                            )
                            .map(|_| Value::Null)
                        }
                        "render" => {
                            let renderer = Renderer::new()?;
                            let (w, h, pixels) = renderer.render(
                                &pdf.project(&runtime.snapshot()?)?,
                                if let Some(code) = step["page_eval"].as_str() {
                                    runtime.eval(code)?.as_i64().ok_or_else(|| {
                                        anyhow::anyhow!("page expression must yield an integer")
                                    })? as i32
                                } else {
                                    step["page"].as_i64().unwrap_or(0) as i32
                                },
                                900,
                            )?;
                            let mut file = std::fs::File::create(
                                step["path"].as_str().unwrap_or("output/testing/render.ppm"),
                            )?;
                            write!(file, "P6\n{w} {h}\n255\n")?;
                            for p in pixels.chunks_exact(4) {
                                file.write_all(&p[..3])?
                            }
                            Ok(json!({"width":w,"height":h}))
                        }
                        _ => bail!("unknown probe operation"),
                    };
                    report["stages"].as_array_mut().unwrap().push(json!({"op":step["op"],"passed":result.is_ok(),"result":result.as_ref().ok(),"error":result.as_ref().err().map(|e|format!("{e:#}"))}));
                    report["diagnostics"] = runtime.diagnostics()?;
                    result?;
                }
            }
            report["diagnostics"] = runtime.diagnostics()?;
            if report["diagnostics"]["errors"]
                .as_array()
                .is_some_and(|e| !e.is_empty())
            {
                bail!("original scripts reported errors; see diagnostics")
            }
            Ok(())
        })();
        report["passed"] = json!(result.is_ok());
        if let Err(e) = &result {
            report["error"] = json!(format!("{e:#}"))
        }
        std::fs::write(report_path, serde_json::to_vec_pretty(&report)?)?;
        println!("{}", serde_json::to_string_pretty(&report)?);
        return result;
    }
    let smoke = if args.get(1).map(String::as_str) == Some("--desktop-smoke") {
        Some(PathBuf::from(
            args.get(2)
                .ok_or_else(|| anyhow::anyhow!("missing smoke directory"))?,
        ))
    } else {
        None
    };
    if let Some(dir) = &smoke {
        std::fs::create_dir_all(dir)?;
        std::env::set_var("MPMB_UI_SMOKE_DIR", dir);
    }
    let mut smoke_dialogs = if smoke.is_some() {
        vec![json!({"result":"ok"})]
    } else {
        vec![]
    };
    if smoke.is_some() && std::env::var_os("MPMB_UI_SMOKE_CONSOLE").is_some() {
        if let Some(source) = std::env::var_os("MPMB_UI_SMOKE_IMPORT_SOURCE") {
            let source = PathBuf::from(source).canonicalize()?;
            smoke_dialogs.push(json!({"title":"IMPORT FROM PDF DIALOG","result":"ok","values":{"fLoc":source,"fRel":false,"icYe":false,"icNo":true}}));
        }
    }
    let rt = Runtime::new(
        &pdf,
        smoke_dialogs,
        if smoke.is_some() {
            vec![json!(1), json!(1)]
        } else {
            vec![]
        },
        true,
        None,
        None,
    )?;
    if smoke.is_some() {
        rt.advance(4100)?;
        rt.edit("PC Name", &json!("Native Vertical Slice"))?;
        rt.edit("Str", &json!("18"))?;
        if std::env::var_os("MPMB_UI_SMOKE_BOOKMARK").is_some() {
            rt.command("createBookmarks(bookmarkRoot,{'Native bookmark navigation':{cExpr:\"getField('PC Name').value=event.target.name;pageNum=1;\"}});bookmarkRoot.children[0].color=['RGB',0.2,0.7,0.4]")?;
        }
    }
    let mut editor = SidebarEditor::new("PC Name");
    let _ = editor.refresh(&rt);
    let initial_tab = if std::env::var_os("MPMB_UI_SMOKE_BOOKMARK").is_some() {
        SidebarTab::Bookmarks
    } else {
        SidebarTab::Fields
    };
    let doc_title = pdf
        .path
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_else(|| "Character Sheet".into());
    let initial_rev = rt
        .eval("__host.revision")
        .ok()
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    let mut cache = ProjectionCache::default();
    cache.ensure_metadata(&rt, &pdf, initial_rev);
    let app = Reader {
        doc_title,
        menu_images: BTreeMap::new(),
        render_revision: initial_rev,
        cache,
        theme_mode: ThemeMode::from_env(),
        theme_applied: None,
        sidebar_open: true,
        sidebar_tab: initial_tab,
        field_filter: FieldFilter::All,
        zoom: ZoomState::default(),
        rendered_width: 0,
        rendered_page: -1,
        rendered_rev: u64::MAX,
        hovered_field: None,
        page_jump_buf: "1".into(),
        save_modal_open: false,
        unsaved: false,
        confirm_close: false,
        allow_close: false,
        smoke,
        smoke_phase: 0,
        pdf,
        rt,
        renderer: Renderer::new()?,
        page: 0,
        texture: None,
        filter: String::new(),
        editor,
        status: "Ready".into(),
        status_is_error: false,
        last_tick: std::time::Instant::now(),
        bookmarks_pane_applied: false,
        save_path: format!(
            "output/testing/native-{}.pdf",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)?
                .as_millis()
        ),
    };
    eframe::run_native(
        "MPMB Linux Reader",
        options(),
        Box::new(|_| Ok(Box::new(app))),
    )
    .map_err(|e| anyhow::anyhow!(e.to_string()))
}
fn options() -> eframe::NativeOptions {
    eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1360., 900.])
            .with_min_inner_size([920., 620.]),
        ..Default::default()
    }
}
fn dialog_options() -> eframe::NativeOptions {
    eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([960., 720.])
            .with_min_inner_size([420., 220.]),
        ..Default::default()
    }
}
fn browse_save_path(current: &str) -> Option<String> {
    let chosen = crate::platform::save_file_dialog(
        "Save Character Sheet Copy",
        Some(("PDF documents", &["*.pdf"])),
        Some(current),
    )
    .ok()??;
    let trimmed = chosen.to_string_lossy().into_owned();
    if trimmed.is_empty() {
        None
    } else if !trimmed.to_ascii_lowercase().ends_with(".pdf") {
        Some(format!("{trimmed}.pdf"))
    } else {
        Some(trimmed)
    }
}
struct SidebarEditor {
    name: String,
    value: String,
    kind: String,
    editable: bool,
    readonly: bool,
    items: Vec<(String, String)>,
    dirty: bool,
}

impl SidebarEditor {
    fn new(name: &str) -> Self {
        Self {
            name: name.to_owned(),
            value: String::new(),
            kind: "text".into(),
            editable: true,
            readonly: false,
            items: Vec::new(),
            dirty: false,
        }
    }

    fn can_edit(&self) -> bool {
        !self.readonly && self.kind != "button"
    }

    fn refresh(&mut self, rt: &Runtime) -> Result<()> {
        let info = rt.eval(&format!(
            "(function(){{var f=getField({});if(!f)return null;return {{value:f.valueAsString,type:f.type,editable:!!f.editable,readonly:!!f.readonly,items:(f.items||[]).map(function(it){{return Array.isArray(it)?[String(it[0]),String(it.length>1?it[1]:it[0])]:[String(it),String(it)]}})}}}})()",
            serde_json::to_string(&self.name)?
        ))?;
        self.value = info["value"].as_str().unwrap_or("").to_owned();
        self.kind = info["type"].as_str().unwrap_or("text").to_owned();
        self.editable = info["editable"].as_bool().unwrap_or(true);
        self.readonly = info["readonly"].as_bool().unwrap_or(false);
        self.items = info["items"]
            .as_array()
            .map(|items| {
                items
                    .iter()
                    .filter_map(|pair| {
                        let pair = pair.as_array()?;
                        Some((
                            pair.first()?.as_str()?.to_owned(),
                            pair.get(1)?.as_str()?.to_owned(),
                        ))
                    })
                    .collect()
            })
            .unwrap_or_default();
        Ok(())
    }

    fn commit(&mut self, rt: &Runtime) -> Result<()> {
        rt.user_edit(&self.name, &json!(self.value))?;
        self.refresh(rt)?;
        self.dirty = false;
        Ok(())
    }

    fn commit_choice(&mut self, rt: &Runtime, value: &str) -> Result<()> {
        rt.select_choice(&self.name, &json!(value))?;
        self.refresh(rt)?;
        self.dirty = false;
        Ok(())
    }

    fn commit_pending(&mut self, rt: &Runtime) -> Result<()> {
        if self.dirty {
            self.commit(rt)?;
        }
        Ok(())
    }

    fn discard(&mut self, rt: &Runtime) -> Result<()> {
        self.dirty = false;
        self.refresh(rt)
    }

    fn select(&mut self, rt: &Runtime, name: &str) -> Result<()> {
        self.commit_pending(rt)?;
        self.name = name.to_owned();
        self.refresh(rt)?;
        self.dirty = false;
        Ok(())
    }
}

struct Reader {
    doc_title: String,
    menu_images: BTreeMap<String, egui::TextureHandle>,
    render_revision: u64,
    cache: ProjectionCache,
    theme_mode: ThemeMode,
    theme_applied: Option<ThemeMode>,
    sidebar_open: bool,
    sidebar_tab: SidebarTab,
    field_filter: FieldFilter,
    zoom: ZoomState,
    rendered_width: usize,
    rendered_page: i32,
    rendered_rev: u64,
    hovered_field: Option<(String, String)>,
    page_jump_buf: String,
    save_modal_open: bool,
    unsaved: bool,
    confirm_close: bool,
    allow_close: bool,
    smoke: Option<PathBuf>,
    smoke_phase: u8,
    pdf: Arc<Pdf>,
    rt: Runtime,
    renderer: Renderer,
    page: i32,
    texture: Option<egui::TextureHandle>,
    filter: String,
    editor: SidebarEditor,
    status: String,
    status_is_error: bool,
    last_tick: std::time::Instant,
    bookmarks_pane_applied: bool,
    save_path: String,
}
fn bookmark_items(ui: &mut egui::Ui, node: &Value, path: &str, action: &mut Option<String>) {
    if let Some(children) = node["children"].as_array() {
        for (index, child) in children.iter().enumerate() {
            let path = format!("{path}.children[{index}]");
            let open = child["open"] == true;
            ui.horizontal(|ui| {
                if child["children"].as_array().is_some_and(|c| !c.is_empty()) {
                    if ui.small_button(if open { "−" } else { "+" }).clicked() {
                        *action = Some(format!("{path}.open=!{path}.open"));
                    }
                } else {
                    ui.add_space(18.);
                }
                let mut text = egui::RichText::new(child["name"].as_str().unwrap_or(""));
                let style = child["style"].as_i64().unwrap_or(0);
                if style & 2 != 0 {
                    text = text.strong();
                }
                if style & 1 != 0 {
                    text = text.italics();
                }
                if let Some(color) = child["color"].as_array().filter(|c| {
                    c.len() == 4
                        && c[0] == "RGB"
                        && c[1..].iter().any(|v| v.as_f64().unwrap_or(0.) > 0.)
                }) {
                    let component = |index: usize| {
                        (color[index].as_f64().unwrap_or(0.).clamp(0., 1.) * 255.).round() as u8
                    };
                    text = text.color(egui::Color32::from_rgb(
                        component(1),
                        component(2),
                        component(3),
                    ));
                }
                if ui.link(text).clicked() {
                    *action = Some(format!("{path}.execute()"));
                }
            });
            if open {
                ui.indent(&path, |ui| bookmark_items(ui, child, &path, action));
            }
        }
    }
}
impl Reader {
    fn refresh_editor(&mut self) -> Result<()> {
        self.editor.refresh(&self.rt)
    }

    fn commit_choice(&mut self, value: &str) -> Result<()> {
        self.editor.commit_choice(&self.rt, value)?;
        self.unsaved = true;
        self.texture = None;
        Ok(())
    }

    fn commit_editor(&mut self) -> Result<()> {
        self.editor.commit(&self.rt)?;
        self.unsaved = true;
        self.texture = None;
        Ok(())
    }

    fn discard_editor(&mut self) -> Result<()> {
        self.editor.discard(&self.rt)?;
        self.texture = None;
        Ok(())
    }

    fn commit_pending_edit(&mut self) -> Result<()> {
        if self.editor.dirty {
            self.commit_editor()?;
        }
        Ok(())
    }

    fn select_editor(&mut self, name: &str) -> Result<()> {
        self.editor.select(&self.rt, name)
    }

    fn save_copy(&mut self) -> Result<()> {
        self.commit_pending_edit()?;
        self.rt.ready()?;
        self.pdf
            .save_new(&self.rt.snapshot()?, std::path::Path::new(&self.save_path))
    }

    fn draw_console(&mut self, ctx: &egui::Context) {
        let Ok(state) = self.rt.eval("__host.consoleView()") else {
            return;
        };
        if state["visible"] != true {
            return;
        }
        let text = state["messages"]
            .as_array()
            .map(|messages| {
                messages
                    .iter()
                    .map(|message| {
                        format!(
                            "[{}]\n{}",
                            message["document"].as_str().unwrap_or(""),
                            message["text"].as_str().unwrap_or("")
                        )
                    })
                    .collect::<Vec<_>>()
                    .join("\n")
            })
            .unwrap_or_default();
        let mut open = true;
        let mut clear = false;
        egui::Window::new("JavaScript Console")
            .open(&mut open)
            .default_size([820., 350.])
            .show(ctx, |ui| {
                clear = ui.button("Clear").clicked();
                if text.is_empty() {
                    ui.label("Console is empty");
                } else {
                    egui::ScrollArea::vertical()
                        .auto_shrink([false, false])
                        .show(ui, |ui| {
                            let mut read_only = text.as_str();
                            ui.add(
                                egui::TextEdit::multiline(&mut read_only)
                                    .font(egui::TextStyle::Monospace)
                                    .desired_width(ui.available_width()),
                            );
                        });
                }
            });
        let result = if clear {
            self.rt.eval("console.clear()")
        } else {
            Ok(Value::Null)
        };
        if let Err(error) = result {
            self.status = format!("Console clear failed: {error:#}");
        }
        if !open {
            if let Err(error) = self.rt.eval("__host.consoleVisible(false)") {
                self.status = format!("Console close failed: {error:#}");
            }
        }
    }
    fn console_smoke(&mut self, ctx: &egui::Context, dir: &std::path::Path) {
        let import_failure = std::env::var_os("MPMB_UI_SMOKE_IMPORT_SOURCE").is_some();
        let step = (|| -> Result<bool> {
            match self.smoke_phase {
                0 if self.texture.is_some() => {
                    if import_failure {
                        self.rt.command("console.clear();DirectImport(true)")?;
                    } else {
                        self.rt.command("console.clear();console.println('Native console output\\nSecond line.');console.show()")?;
                    }
                    self.smoke_phase = 1;
                }
                1 => {
                    ctx.send_viewport_cmd(egui::ViewportCommand::Screenshot(Default::default()));
                    self.smoke_phase = 2;
                }
                2 if capture(ctx, &dir.join("console-visible.png")) => {
                    let state = self.rt.eval("__host.consoleView()")?;
                    if state["visible"] != true {
                        bail!("Console did not become visible");
                    }
                    let messages = state["messages"]
                        .as_array()
                        .ok_or_else(|| anyhow::anyhow!("Missing console messages"))?;
                    if import_failure {
                        if !messages.iter().any(|m| {
                            m["text"]
                                .as_str()
                                .unwrap_or("")
                                .contains("An error occurred during importing:")
                        }) {
                            bail!("Original import error was not displayed");
                        }
                        let diagnostics = self.rt.diagnostics()?;
                        let errors = diagnostics["errors"].as_array().ok_or_else(|| {
                            anyhow::anyhow!("Missing original field error evidence")
                        })?;
                        if errors.len() != 2
                            || !errors.iter().all(|e| {
                                e["field"] == "Carrying Capacity Multiplier" && e["event"] == "F"
                            })
                        {
                            bail!("Original field error profile changed");
                        }
                    } else if messages.len() != 1
                        || messages[0]["text"] != "Native console output\nSecond line."
                    {
                        bail!("Console text changed");
                    }
                    std::fs::write(
                        dir.join("console-visible.json"),
                        serde_json::to_vec_pretty(&state)?,
                    )?;
                    self.rt.eval("console.clear()")?;
                    self.smoke_phase = 3;
                }
                3 => {
                    ctx.send_viewport_cmd(egui::ViewportCommand::Screenshot(Default::default()));
                    self.smoke_phase = 4;
                }
                4 if capture(ctx, &dir.join("console-cleared.png")) => {
                    let state = self.rt.eval("__host.consoleView()")?;
                    if state["visible"] != true || state["messages"] != json!([]) {
                        bail!("Clear did not preserve an empty visible console");
                    }
                    std::fs::write(
                        dir.join("console-cleared.json"),
                        serde_json::to_vec_pretty(&state)?,
                    )?;
                    self.rt.eval("__host.consoleVisible(false)")?;
                    self.smoke_phase = 5;
                }
                5 => {
                    ctx.send_viewport_cmd(egui::ViewportCommand::Screenshot(Default::default()));
                    self.smoke_phase = 6;
                }
                6 if capture(ctx, &dir.join("console-closed.png")) => {
                    let state = self.rt.eval("__host.consoleView()")?;
                    if state["visible"] != false {
                        bail!("Console did not close");
                    }
                    std::fs::write(
                        dir.join("console-closed.json"),
                        serde_json::to_vec_pretty(&state)?,
                    )?;
                    return Ok(true);
                }
                _ => {}
            }
            Ok(false)
        })();
        if matches!(step, Ok(false)) {
            return;
        }
        let report = json!({"passed":step.is_ok(),"status":self.status,"scope":"Actual native console window show/output/clear/close. Scripted original import dialogs only; this is not clean-import or pointer-control qualification.","expected_original_import_failure":import_failure,"mpmb_workflow_passed":if import_failure {Some(false)} else {None},"error":step.err().map(|e|format!("{e:#}")),"diagnostics":self.rt.diagnostics().unwrap_or(Value::Null)});
        let _ = std::fs::write(
            dir.join("desktop-result.json"),
            serde_json::to_vec_pretty(&report).unwrap(),
        );
        self.smoke_phase = 7;
        ctx.send_viewport_cmd(egui::ViewportCommand::Close);
    }
    fn result(&mut self, r: Result<()>) {
        if r.is_ok() {
            self.unsaved = true;
            self.status_is_error = false;
            if let Ok(value) = self.rt.eval("__host.revision") {
                self.render_revision = value.as_u64().unwrap_or(self.render_revision);
            }
            self.cache.invalidate_all();
            if !self.editor.dirty {
                let _ = self.refresh_editor();
            }
        } else {
            self.status_is_error = true;
        }
        self.status = match r {
            Ok(_) => "Completed".into(),
            Err(e) => format!("{e:#}"),
        };
        self.texture = None;
    }

    fn go_to_page(&mut self, target: i32, page_count: i32) {
        if let Err(error) = self.commit_pending_edit() {
            self.result(Err(error));
            return;
        }
        let next = target.clamp(0, (page_count - 1).max(0));
        if next != self.page {
            self.page = next;
            self.page_jump_buf = (next + 1).to_string();
            let _ = self.rt.eval(&format!("pageNum={}", self.page));
            self.texture = None;
        }
    }

    fn perform_save(&mut self) -> bool {
        let r = self.save_copy();
        let saved = r.is_ok();
        let saved_path = self.save_path.clone();
        self.result(r);
        if saved {
            self.unsaved = false;
            self.status = format!("Saved copy to {saved_path}");
            self.status_is_error = false;
        }
        saved
    }

    fn handle_shortcuts(&mut self, ctx: &egui::Context, page_count: i32) {
        let typing = ctx.wants_keyboard_input();
        if ctx.input_mut(|i| i.consume_key(egui::Modifiers::COMMAND, egui::Key::S)) {
            self.save_modal_open = true;
        }
        if ctx.input_mut(|i| i.consume_key(egui::Modifiers::COMMAND, egui::Key::B)) {
            self.sidebar_open = !self.sidebar_open;
        }
        if ctx.input_mut(|i| i.consume_key(egui::Modifiers::COMMAND, egui::Key::Equals))
            || ctx.input_mut(|i| i.consume_key(egui::Modifiers::COMMAND, egui::Key::Plus))
        {
            self.zoom.zoom_in();
        }
        if ctx.input_mut(|i| i.consume_key(egui::Modifiers::COMMAND, egui::Key::Minus)) {
            self.zoom.zoom_out();
        }
        if ctx.input_mut(|i| i.consume_key(egui::Modifiers::COMMAND, egui::Key::Num0)) {
            self.zoom.set_fit_width();
        }
        if !typing {
            if ctx.input_mut(|i| i.consume_key(egui::Modifiers::NONE, egui::Key::PageDown)) {
                self.go_to_page(self.page + 1, page_count);
            }
            if ctx.input_mut(|i| i.consume_key(egui::Modifiers::NONE, egui::Key::PageUp)) {
                self.go_to_page(self.page - 1, page_count);
            }
        }
    }

    fn draw_toolbar(&mut self, ctx: &egui::Context, p: &Palette, page_count: i32) {
        let toolbar_frame = egui::Frame::new()
            .fill(p.toolbar_bg)
            .inner_margin(egui::Margin::symmetric(12, 8))
            .stroke(egui::Stroke::new(1.0, p.card_stroke));
        egui::TopBottomPanel::top("toolbar")
            .frame(toolbar_frame)
            .show(ctx, |ui| {
                ui.horizontal_wrapped(|ui| {
                    ui.spacing_mut().item_spacing.x = 6.0;
                    if ui
                        .selectable_label(self.sidebar_open, "☰ Panel")
                        .on_hover_text("Toggle sidebar (Ctrl+B)")
                        .clicked()
                    {
                        self.sidebar_open = !self.sidebar_open;
                    }
                    ui.separator();

                    // Document title & clean/unsaved pill
                    let display_title = if self.doc_title.chars().count() > 20 {
                        let clipped: String = self.doc_title.chars().take(19).collect();
                        format!("{clipped}…")
                    } else {
                        self.doc_title.clone()
                    };
                    ui.label(egui::RichText::new(display_title).strong())
                        .on_hover_text(&self.doc_title);
                    if self.unsaved || self.editor.dirty {
                        theme::status_pill(ui, "Unsaved", p.warn, p.warn_bg);
                    } else {
                        theme::status_pill(ui, "Clean", p.ok, p.ok_bg);
                    }

                    ui.separator();

                    // Page navigation group
                    if ui
                        .add_enabled(self.page > 0, egui::Button::new("◀"))
                        .on_hover_text("Previous page (PageUp)")
                        .clicked()
                    {
                        self.go_to_page(self.page - 1, page_count);
                    }
                    let page_edit = ui.add(
                        egui::TextEdit::singleline(&mut self.page_jump_buf)
                            .desired_width(32.0)
                            .horizontal_align(egui::Align::Center),
                    );
                    if page_edit.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter)) {
                        if let Ok(num) = self.page_jump_buf.trim().parse::<i32>() {
                            self.go_to_page(num - 1, page_count);
                        }
                        self.page_jump_buf = (self.page + 1).to_string();
                    } else if !page_edit.has_focus() {
                        let current = (self.page + 1).to_string();
                        if self.page_jump_buf != current {
                            self.page_jump_buf = current;
                        }
                    }
                    ui.label(
                        egui::RichText::new(format!("/ {page_count}")).color(p.text_secondary),
                    );
                    if ui
                        .add_enabled(self.page + 1 < page_count, egui::Button::new("▶"))
                        .on_hover_text("Next page (PageDown)")
                        .clicked()
                    {
                        self.go_to_page(self.page + 1, page_count);
                    }

                    ui.separator();

                    // Zoom controls
                    if ui.button("−").on_hover_text("Zoom out (Ctrl+-)").clicked() {
                        self.zoom.zoom_out();
                    }
                    if ui
                        .button(self.zoom.percent_label())
                        .on_hover_text("Fit page width (Ctrl+0)")
                        .clicked()
                    {
                        self.zoom.set_fit_width();
                    }
                    if ui.button("+").on_hover_text("Zoom in (Ctrl+=)").clicked() {
                        self.zoom.zoom_in();
                    }

                    ui.separator();

                    // Primary MPMB actions
                    if theme::accent_button(ui, p, "Classes…")
                        .on_hover_text("Open original MPMB Class Selection dialog")
                        .clicked()
                    {
                        let r = self.commit_pending_edit().and_then(|_| {
                            self.rt
                                .eval("__host.invokeMenu('ClassesButton')")
                                .map(|_| ())
                        });
                        self.result(r);
                    }

                    ui.menu_button("Tools", |ui| match self.rt.eval("__host.menuItems()") {
                        Ok(items) => {
                            if let Some(items) = items.as_array() {
                                for item in items {
                                    let name = item["name"].as_str().unwrap_or("");
                                    if !self.menu_images.contains_key(name) {
                                        if let Some(image) = argb_image(&item["icon"]) {
                                            self.menu_images.insert(
                                                name.into(),
                                                ctx.load_texture(name, image, Default::default()),
                                            );
                                        }
                                    }
                                    ui.horizontal(|ui| {
                                        if let Some(image) = self.menu_images.get(name) {
                                            ui.image(image);
                                        }
                                        if ui
                                            .add_enabled(
                                                item["enabled"] == true,
                                                egui::Button::new(format!(
                                                    "{}{}",
                                                    if item["marked"] == true {
                                                        "[x] "
                                                    } else {
                                                        ""
                                                    },
                                                    item["label"].as_str().unwrap_or(name)
                                                )),
                                            )
                                            .on_hover_text(item["tooltip"].as_str().unwrap_or(""))
                                            .clicked()
                                        {
                                            let r = self.commit_pending_edit().and_then(|_| {
                                                self.rt
                                                    .eval(&format!(
                                                        "__host.invokeMenu({})",
                                                        serde_json::to_string(name).unwrap()
                                                    ))
                                                    .map(|_| ())
                                            });
                                            self.result(r);
                                            ui.close();
                                        }
                                    });
                                }
                            }
                        }
                        Err(e) => {
                            ui.label(format!("Menu error: {e:#}"));
                        }
                    });

                    ui.menu_button("Sheets", |ui| {
                        for (label, code) in [
                            ("Add Companion Page", "DoTemplate('AScomp','Add',null,true)"),
                            (
                                "Add Wild-Shape Page",
                                "DoTemplate('WSfront','Add',null,true)",
                            ),
                            ("Generate Spell Sheet…", "GenerateSpellSheet()"),
                        ] {
                            if ui.button(label).clicked() {
                                let r = self
                                    .commit_pending_edit()
                                    .and_then(|_| self.rt.command(code));
                                self.result(r);
                                ui.close();
                            }
                        }
                        ui.separator();
                        if ui.button("Import User Script…").clicked() {
                            let r = self.commit_pending_edit().and_then(|_| {
                                self.rt.eval(TOOLBAR_IMPORT_SCRIPT_ACTION).map(|_| ())
                            });
                            self.result(r);
                            ui.close();
                        }
                        if ui.button("Recalculate Sheet").clicked() {
                            let r = self
                                .commit_pending_edit()
                                .and_then(|_| self.rt.eval("calculateNow()").map(|_| ()));
                            self.result(r);
                            ui.close();
                        }
                        if ui.button("JavaScript Console").clicked() {
                            if let Err(error) = self.rt.eval("console.show()") {
                                self.status = format!("Console failed: {error:#}");
                                self.status_is_error = true;
                            }
                            ui.close();
                        }
                    });

                    ui.separator();

                    if ui
                        .button("Save…")
                        .on_hover_text("Save character sheet to a new PDF file (Ctrl+S)")
                        .clicked()
                    {
                        self.save_modal_open = true;
                    }
                    let theme_label = match self.theme_mode {
                        ThemeMode::Dark => "Light",
                        ThemeMode::Light => "Dark",
                    };
                    if ui
                        .button(theme_label)
                        .on_hover_text("Switch color theme (Dark / Light)")
                        .clicked()
                    {
                        self.theme_mode = self.theme_mode.toggled();
                        set_active_theme(self.theme_mode);
                    }
                });
            });
    }

    fn draw_save_modal(&mut self, ctx: &egui::Context, p: &Palette) {
        if !self.save_modal_open {
            return;
        }
        let mut open = self.save_modal_open;
        egui::Window::new("Save Character Sheet Copy")
            .open(&mut open)
            .collapsible(false)
            .resizable(false)
            .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
            .show(ctx, |ui| {
                ui.set_min_width(440.0);
                ui.label(
                    egui::RichText::new(
                        "Saves a new interactive PDF preserving all original MPMB scripts. Existing files are never overwritten.",
                    )
                    .color(p.text_secondary),
                );
                ui.add_space(6.0);
                ui.horizontal(|ui| {
                    ui.add(
                        egui::TextEdit::singleline(&mut self.save_path)
                            .desired_width(340.0)
                            .hint_text("output/testing/my-character.pdf"),
                    );
                    if ui.button("Browse…").clicked() {
                        if let Some(chosen) = browse_save_path(&self.save_path) {
                            self.save_path = chosen;
                        }
                    }
                });
                ui.add_space(10.0);
                ui.horizontal(|ui| {
                    if theme::accent_button(ui, p, "Save Copy").clicked() && self.perform_save() {
                        self.save_modal_open = false;
                    }
                    if ui.button("Cancel").clicked() {
                        self.save_modal_open = false;
                    }
                });
                if self.status_is_error {
                    ui.add_space(6.0);
                    egui::Frame::new()
                        .fill(p.err_bg)
                        .corner_radius(egui::CornerRadius::same(6))
                        .inner_margin(egui::Margin::symmetric(8, 6))
                        .show(ui, |ui| {
                            ui.label(egui::RichText::new(&self.status).color(p.err));
                        });
                }
            });
        if !open {
            self.save_modal_open = false;
        }
    }

    fn draw_character_card(&self, ui: &mut egui::Ui, p: &Palette) {
        let s = &self.cache.summary;
        theme::card_frame(p).show(ui, |ui| {
            let name = if s.name.is_empty() {
                "Unnamed Character"
            } else {
                &s.name
            };
            ui.horizontal(|ui| {
                ui.label(egui::RichText::new(name).strong().size(15.0));
                if !s.level.is_empty() {
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        theme::badge(ui, &format!("Lv {}", s.level), p.accent, p.accent_soft);
                    });
                }
            });
            if !s.class_and_levels.is_empty() {
                ui.label(
                    egui::RichText::new(&s.class_and_levels)
                        .small()
                        .color(p.text_secondary),
                );
            }
            let has_vitals = !s.ac.is_empty() || !s.hp_max.is_empty() || !s.proficiency.is_empty();
            if has_vitals {
                ui.add_space(4.0);
                ui.horizontal_wrapped(|ui| {
                    if !s.ac.is_empty() {
                        theme::badge(ui, &format!("AC {}", s.ac), p.text_primary, p.ro_badge_bg);
                    }
                    if !s.hp_max.is_empty() {
                        let hp = if s.hp_current.is_empty() {
                            format!("HP {}", s.hp_max)
                        } else {
                            format!("HP {}/{}", s.hp_current, s.hp_max)
                        };
                        theme::badge(ui, &hp, p.ok, p.ok_bg);
                    }
                    if !s.proficiency.is_empty() {
                        let prof = if s.proficiency.starts_with('+') {
                            format!("Prof {}", s.proficiency)
                        } else {
                            format!("Prof +{}", s.proficiency)
                        };
                        theme::badge(ui, &prof, p.text_secondary, p.ro_badge_bg);
                    }
                });
            }
            if !s.abilities.is_empty() {
                ui.add_space(6.0);
                ui.columns(s.abilities.len(), |cols| {
                    for (col, ab) in cols.iter_mut().zip(&s.abilities) {
                        col.vertical_centered(|ui| {
                            ui.label(egui::RichText::new(ab.label).small().color(p.text_muted));
                            let score = if ab.score.is_empty() {
                                "—"
                            } else {
                                &ab.score
                            };
                            ui.label(egui::RichText::new(score).strong());
                            let formatted_mod = if ab.modifier.is_empty() {
                                " ".to_string()
                            } else if let Ok(n) = ab.modifier.trim().parse::<i32>() {
                                if n > 0 {
                                    format!("+{n}")
                                } else {
                                    n.to_string()
                                }
                            } else {
                                ab.modifier.clone()
                            };
                            ui.label(egui::RichText::new(formatted_mod).small().color(p.accent));
                        });
                    }
                });
            }
        });
    }

    fn draw_sidebar(&mut self, ctx: &egui::Context, p: &Palette) {
        if !self.sidebar_open {
            return;
        }
        let want_bookmarks = !self.bookmarks_pane_applied
            && self
                .rt
                .eval("pane")
                .ok()
                .and_then(|v| v.as_str().map(|s| s == "bookmarks"))
                .unwrap_or(false);
        if want_bookmarks {
            self.bookmarks_pane_applied = true;
            self.sidebar_tab = SidebarTab::Bookmarks;
        }
        let page_widget_names: BTreeSet<String> = self
            .cache
            .widgets_for_page(&self.rt, self.page, self.render_revision)
            .iter()
            .filter_map(|w| w["name"].as_str().map(str::to_owned))
            .collect();

        let side_frame = egui::Frame::new()
            .fill(p.panel_bg)
            .inner_margin(egui::Margin::same(10))
            .stroke(egui::Stroke::new(1.0, p.card_stroke));
        egui::SidePanel::left("fields")
            .frame(side_frame)
            .default_width(330.0)
            .min_width(270.0)
            .max_width(480.0)
            .show(ctx, |ui| {
                self.draw_character_card(ui, p);
                ui.add_space(8.0);

                // Tab bar
                ui.horizontal(|ui| {
                    ui.selectable_value(&mut self.sidebar_tab, SidebarTab::Fields, "Fields");
                    ui.selectable_value(&mut self.sidebar_tab, SidebarTab::Bookmarks, "Bookmarks");
                    ui.selectable_value(
                        &mut self.sidebar_tab,
                        SidebarTab::Diagnostics,
                        "Diagnostics",
                    );
                });
                ui.separator();

                match self.sidebar_tab {
                    SidebarTab::Fields => {
                        ui.horizontal(|ui| {
                            ui.add(
                                egui::TextEdit::singleline(&mut self.filter)
                                    .desired_width(ui.available_width() - 28.0)
                                    .hint_text("Search fields…"),
                            );
                            if !self.filter.is_empty() && ui.small_button("×").clicked() {
                                self.filter.clear();
                            }
                        });
                        ui.horizontal(|ui| {
                            ui.selectable_value(&mut self.field_filter, FieldFilter::All, "All");
                            ui.selectable_value(
                                &mut self.field_filter,
                                FieldFilter::CurrentPage,
                                "This page",
                            );
                            ui.selectable_value(
                                &mut self.field_filter,
                                FieldFilter::Writable,
                                "Writable",
                            );
                        });
                        ui.add_space(4.0);

                        let filtered = filter_fields(
                            &self.cache.field_catalog,
                            &self.filter,
                            self.field_filter,
                            &page_widget_names,
                        );
                        ui.label(
                            egui::RichText::new(format!("{} matching fields", filtered.len()))
                                .small()
                                .color(p.text_muted),
                        );
                        let list_height = (ui.available_height() - 145.0).clamp(56.0, 420.0);
                        let mut selected = None;
                        egui::ScrollArea::vertical()
                            .id_salt("field-catalog")
                            .max_height(list_height)
                            .show(ui, |ui| {
                                for entry in &filtered {
                                    let is_sel = self.editor.name == entry.name;
                                    ui.horizontal(|ui| {
                                        ui.label(
                                            egui::RichText::new(entry.short_type())
                                                .monospace()
                                                .small()
                                                .color(if entry.readonly {
                                                    p.text_muted
                                                } else {
                                                    p.accent
                                                }),
                                        );
                                        let label = if entry.readonly {
                                            format!("{} [RO]", entry.name)
                                        } else {
                                            entry.name.clone()
                                        };
                                        if ui.selectable_label(is_sel, label).clicked() {
                                            selected = Some(entry.name.clone());
                                        }
                                    });
                                }
                            });
                        if let Some(name) = selected {
                            if let Err(error) = self.select_editor(&name) {
                                self.result(Err(error));
                            }
                        }

                        ui.add_space(8.0);
                        // Field Inspector Card
                        let mut chosen = None;
                        let mut commit_clicked = false;
                        let mut discard_clicked = false;
                        theme::card_frame(p).show(ui, |ui| {
                            ui.horizontal_wrapped(|ui| {
                                ui.label(egui::RichText::new(&self.editor.name).strong());
                                theme::badge(
                                    ui,
                                    &self.editor.kind,
                                    p.text_secondary,
                                    p.ro_badge_bg,
                                );
                                if self.editor.readonly {
                                    theme::badge(ui, "Read-only", p.warn, p.warn_bg);
                                }
                            });
                            ui.add_space(4.0);
                            let editable_here = self.editor.can_edit();
                            let is_choice =
                                matches!(self.editor.kind.as_str(), "combobox" | "listbox");
                            ui.add_enabled_ui(editable_here, |ui| {
                                if is_choice && !self.editor.items.is_empty() {
                                    let selected_label = self
                                        .editor
                                        .items
                                        .iter()
                                        .find(|(exp, _)| *exp == self.editor.value)
                                        .map(|(_, label)| label.clone())
                                        .unwrap_or_else(|| self.editor.value.clone());
                                    egui::ComboBox::from_id_salt((
                                        "sidebar-choice",
                                        &self.editor.name,
                                    ))
                                    .width(ui.available_width())
                                    .selected_text(selected_label)
                                    .show_ui(ui, |ui| {
                                        for (exp, label) in &self.editor.items {
                                            let display =
                                                if label.is_empty() { "(blank)" } else { label };
                                            if ui
                                                .selectable_label(
                                                    self.editor.value == *exp,
                                                    display,
                                                )
                                                .clicked()
                                            {
                                                chosen = Some(exp.clone());
                                            }
                                        }
                                    });
                                }
                                if !is_choice
                                    || self.editor.editable
                                    || self.editor.items.is_empty()
                                {
                                    let resp = ui.add(
                                        egui::TextEdit::multiline(&mut self.editor.value)
                                            .desired_width(f32::INFINITY)
                                            .desired_rows(2),
                                    );
                                    if resp.changed() {
                                        self.editor.dirty = true;
                                        self.unsaved = true;
                                    }
                                    if resp.has_focus()
                                        && self.editor.dirty
                                        && ui.input_mut(|i| {
                                            i.consume_key(
                                                egui::Modifiers::COMMAND,
                                                egui::Key::Enter,
                                            )
                                        })
                                    {
                                        commit_clicked = true;
                                    }
                                    if resp.has_focus()
                                        && self.editor.dirty
                                        && ui.input_mut(|i| {
                                            i.consume_key(egui::Modifiers::NONE, egui::Key::Escape)
                                        })
                                    {
                                        discard_clicked = true;
                                    }
                                }
                            });
                            if editable_here || self.editor.dirty {
                                ui.add_space(6.0);
                                ui.horizontal(|ui| {
                                    if editable_here
                                        && theme::accent_button(ui, p, "Apply Edit")
                                            .on_hover_text("Commit edit (Ctrl+Enter)")
                                            .clicked()
                                    {
                                        commit_clicked = true;
                                    }
                                    if self.editor.dirty
                                        && ui
                                            .button("Discard pending edit")
                                            .on_hover_text("Revert uncommitted draft (Esc)")
                                            .clicked()
                                    {
                                        discard_clicked = true;
                                    }
                                });
                            }
                        });
                        if let Some(exp) = chosen {
                            self.editor.value = exp.clone();
                            let r = self.commit_choice(&exp);
                            self.result(r);
                        }
                        if commit_clicked {
                            let r = self.commit_editor();
                            self.result(r);
                        }
                        if discard_clicked {
                            let r = self.discard_editor();
                            self.result(r);
                        }
                    }
                    SidebarTab::Bookmarks => {
                        let mut action = None;
                        let tree = self.cache.bookmarks.clone();
                        egui::ScrollArea::vertical()
                            .id_salt("bookmarks")
                            .show(ui, |ui| {
                                bookmark_items(ui, &tree, "bookmarkRoot", &mut action);
                            });
                        if let Some(code) = action {
                            let r = self
                                .commit_pending_edit()
                                .and_then(|_| self.rt.eval(&code).map(|_| ()));
                            self.result(r);
                        }
                    }
                    SidebarTab::Diagnostics => {
                        let d = &self.cache.diagnostics;
                        theme::card_frame(p).show(ui, |ui| {
                            let rows = [
                                ("Fields", d["field_count"].as_u64().unwrap_or(0).to_string()),
                                (
                                    "Menus",
                                    d["menus"]
                                        .as_array()
                                        .map(|a| a.len())
                                        .unwrap_or(0)
                                        .to_string(),
                                ),
                                (
                                    "Pending timers",
                                    d["timers"].as_u64().unwrap_or(0).to_string(),
                                ),
                                (
                                    "Script errors",
                                    d["errors"]
                                        .as_array()
                                        .map(|a| a.len())
                                        .unwrap_or(0)
                                        .to_string(),
                                ),
                                (
                                    "API gaps",
                                    d["gaps"]
                                        .as_array()
                                        .map(|a| a.len())
                                        .unwrap_or(0)
                                        .to_string(),
                                ),
                                (
                                    "Script overrides",
                                    d["repairs"]
                                        .as_array()
                                        .map(|a| a.len())
                                        .unwrap_or(0)
                                        .to_string(),
                                ),
                                ("PDF projections", self.cache.projection_builds.to_string()),
                            ];
                            egui::Grid::new("diag-grid")
                                .num_columns(2)
                                .spacing(egui::vec2(16.0, 4.0))
                                .show(ui, |ui| {
                                    for (k, v) in rows {
                                        ui.label(egui::RichText::new(k).color(p.text_secondary));
                                        ui.label(egui::RichText::new(v).strong().monospace());
                                        ui.end_row();
                                    }
                                });
                        });
                        ui.add_space(6.0);
                        egui::CollapsingHeader::new("Raw diagnostics JSON").show(ui, |ui| {
                            egui::ScrollArea::vertical()
                                .max_height(260.0)
                                .show(ui, |ui| {
                                    ui.label(
                                        egui::RichText::new(
                                            serde_json::to_string_pretty(d)
                                                .unwrap_or_else(|_| d.to_string()),
                                        )
                                        .monospace()
                                        .small(),
                                    );
                                });
                        });
                    }
                }
            });
    }

    fn draw_canvas(&mut self, ctx: &egui::Context, p: &Palette) {
        let canvas_frame = egui::Frame::new()
            .fill(p.canvas_bg)
            .inner_margin(egui::Margin::same(16));
        egui::CentralPanel::default()
            .frame(canvas_frame)
            .show(ctx, |ui| {
                // Support Ctrl+Scroll wheel zooming only when pointer is over the sheet canvas
                let scroll_zoom = if ui.rect_contains_pointer(ui.max_rect()) {
                    ctx.input(|i| {
                        if i.modifiers.command {
                            i.smooth_scroll_delta.y
                        } else {
                            0.0
                        }
                    })
                } else {
                    0.0
                };
                if scroll_zoom > 4.0 {
                    self.zoom.zoom_in();
                } else if scroll_zoom < -4.0 {
                    self.zoom.zoom_out();
                }

                let avail_w = ui.available_width();
                let target_px = self
                    .zoom
                    .render_pixel_width(avail_w, ctx.pixels_per_point());
                let display_w = self.zoom.display_width(avail_w);
                let need_render = self.texture.is_none()
                    || self.rendered_page != self.page
                    || self.rendered_rev != self.render_revision
                    || self.rendered_width != target_px;
                if need_render {
                    match self
                        .cache
                        .projected_bytes(&self.rt, &self.pdf, self.render_revision)
                        .and_then(|bytes| self.renderer.render(bytes, self.page, target_px))
                    {
                        Ok((w, h, pixels)) => {
                            self.texture = Some(ctx.load_texture(
                                "PDF page",
                                ColorImage::from_rgba_unmultiplied([w, h], &pixels),
                                egui::TextureOptions::LINEAR,
                            ));
                            self.rendered_width = target_px;
                            self.rendered_page = self.page;
                            self.rendered_rev = self.render_revision;
                        }
                        Err(e) => {
                            self.status = format!("Render failed: {e:#}");
                            self.status_is_error = true;
                        }
                    }
                }

                self.hovered_field = None;
                let widgets = self
                    .cache
                    .widgets_for_page(&self.rt, self.page, self.render_revision)
                    .to_vec();
                let page_size = self.renderer.page_size.get();

                egui::ScrollArea::both().show(ui, |ui| {
                    ui.vertical_centered(|ui| {
                        if let Some(t) = &self.texture {
                            let tex_size = t.size_vec2();
                            let aspect = if tex_size.x > 0.0 {
                                tex_size.y / tex_size.x
                            } else {
                                1.294
                            };
                            let img_size = egui::vec2(display_w, display_w * aspect);
                            let page_frame = egui::Frame::new()
                                .fill(egui::Color32::WHITE)
                                .shadow(p.page_shadow)
                                .stroke(egui::Stroke::new(1.0, p.card_stroke));
                            let inner = page_frame.show(ui, |ui| {
                                ui.add(
                                    egui::Image::new((t.id(), img_size))
                                        .sense(egui::Sense::click()),
                                )
                            });
                            let response = inner.inner;
                            let painter = ui.painter();

                            // Highlight currently selected sidebar field on this page
                            for w in &widgets {
                                if w["name"].as_str() == Some(self.editor.name.as_str()) {
                                    if let Some(rect) = w["rect"].as_array().and_then(|r| {
                                        pdf_rect_to_screen(r, page_size, response.rect)
                                    }) {
                                        painter.rect(
                                            rect,
                                            egui::CornerRadius::same(2),
                                            p.widget_selected_fill,
                                            egui::Stroke::new(1.5, p.widget_selected_stroke),
                                            egui::StrokeKind::Outside,
                                        );
                                    }
                                }
                            }

                            // Hover readout + subtle highlight
                            if let Some(hover_pos) = response.hover_pos() {
                                let (pw, ph) = page_size;
                                if pw > 0.0 && ph > 0.0 {
                                    let x = (hover_pos.x - response.rect.left())
                                        / response.rect.width()
                                        * pw;
                                    let y = ph
                                        - (hover_pos.y - response.rect.top())
                                            / response.rect.height()
                                            * ph;
                                    if let Some(hit) = page_widget_hit(&widgets, x, y) {
                                        let hname = hit["name"].as_str().unwrap_or("").to_owned();
                                        let htype =
                                            hit["type"].as_str().unwrap_or("field").to_owned();
                                        let hro = hit["readonly"].as_bool().unwrap_or(false);
                                        if let Some(rect) = hit["rect"].as_array().and_then(|r| {
                                            pdf_rect_to_screen(r, page_size, response.rect)
                                        }) {
                                            painter.rect(
                                                rect,
                                                egui::CornerRadius::same(2),
                                                p.widget_hover_fill,
                                                egui::Stroke::new(1.25, p.widget_hover_stroke),
                                                egui::StrokeKind::Outside,
                                            );
                                        }
                                        if !hro {
                                            ctx.set_cursor_icon(if htype == "text" {
                                                egui::CursorIcon::Text
                                            } else {
                                                egui::CursorIcon::PointingHand
                                            });
                                        }
                                        self.hovered_field = Some((
                                            hname,
                                            if hro {
                                                format!("{htype}, read-only")
                                            } else {
                                                htype
                                            },
                                        ));
                                    }
                                }
                            }

                            if response.clicked() {
                                if let Some((pos, modifiers)) = ctx
                                    .input(|input| activation_input(&input.events, response.rect))
                                {
                                    let (width, height) = page_size;
                                    let x = (pos.x - response.rect.left()) / response.rect.width()
                                        * width;
                                    let y = height
                                        - (pos.y - response.rect.top()) / response.rect.height()
                                            * height;
                                    if let Some(w) = page_widget_hit(&widgets, x, y) {
                                        let r = (|| -> Result<()> {
                                            self.select_editor(w["name"].as_str().unwrap_or(""))?;
                                            let name = serde_json::to_string(&self.editor.name)?;
                                            self.rt.eval(&format!(
                                                "__host.activate({name},{},{modifiers})",
                                                w["index"]
                                            ))?;
                                            self.refresh_editor()
                                        })();
                                        self.result(r);
                                    }
                                }
                            }
                        }
                    });
                });
            });
    }

    fn draw_status_bar(&self, ctx: &egui::Context, p: &Palette, page_count: i32) {
        let bar_frame = egui::Frame::new()
            .fill(p.toolbar_bg)
            .inner_margin(egui::Margin::symmetric(12, 5))
            .stroke(egui::Stroke::new(1.0, p.card_stroke));
        egui::TopBottomPanel::bottom("status_bar")
            .frame(bar_frame)
            .show(ctx, |ui| {
                ui.horizontal(|ui| {
                    let dot_color = if self.status_is_error {
                        p.err
                    } else if self.unsaved {
                        p.warn
                    } else {
                        p.ok
                    };
                    theme::status_dot(ui, dot_color);
                    ui.label(egui::RichText::new(&self.status).small().color(
                        if self.status_is_error {
                            p.err
                        } else {
                            p.text_secondary
                        },
                    ));
                    if let Some((name, kind)) = &self.hovered_field {
                        ui.separator();
                        ui.label(
                            egui::RichText::new(format!("Field: {name} ({kind})"))
                                .small()
                                .color(p.accent),
                        );
                    }
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        ui.label(
                            egui::RichText::new(format!(
                                "Page {}/{}  •  {}  •  {} fields  •  Rev {}",
                                self.page + 1,
                                page_count,
                                self.zoom.percent_label(),
                                self.cache.field_catalog.len(),
                                self.render_revision
                            ))
                            .small()
                            .color(p.text_muted),
                        );
                    });
                });
            });
    }
}

static ACTIVE_THEME: std::sync::atomic::AtomicU8 = std::sync::atomic::AtomicU8::new(0);
fn set_active_theme(mode: ThemeMode) {
    ACTIVE_THEME.store(
        match mode {
            ThemeMode::Dark => 0,
            ThemeMode::Light => 1,
        },
        std::sync::atomic::Ordering::Relaxed,
    );
}
fn active_theme_env() -> &'static str {
    if ACTIVE_THEME.load(std::sync::atomic::Ordering::Relaxed) == 1 {
        ThemeMode::Light.as_env()
    } else {
        ThemeMode::Dark.as_env()
    }
}

impl eframe::App for Reader {
    fn update(&mut self, ctx: &egui::Context, _: &mut eframe::Frame) {
        let palette = if self.theme_applied != Some(self.theme_mode) {
            self.theme_applied = Some(self.theme_mode);
            set_active_theme(self.theme_mode);
            theme::apply(ctx, self.theme_mode)
        } else {
            Palette::for_mode(self.theme_mode)
        };

        if self.confirm_close {
            egui::Window::new("Save your changes?")
                .collapsible(false)
                .resizable(false)
                .anchor(egui::Align2::CENTER_CENTER, egui::vec2(0.0, 0.0))
                .show(ctx, |ui| {
                    ui.set_min_width(420.0);
                    ui.label("The current document has changes. Save a new copy before closing.");
                    ui.add_space(6.0);
                    ui.horizontal(|ui| {
                        ui.add(
                            egui::TextEdit::singleline(&mut self.save_path).desired_width(320.0),
                        );
                        if ui.button("Browse…").clicked() {
                            if let Some(chosen) = browse_save_path(&self.save_path) {
                                self.save_path = chosen;
                            }
                        }
                    });
                    ui.add_space(8.0);
                    ui.horizontal(|ui| {
                        if theme::accent_button(ui, &palette, "Save and close").clicked()
                            && self.perform_save()
                        {
                            self.allow_close = true;
                            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                        }
                        if ui.button("Discard changes").clicked() {
                            self.allow_close = true;
                            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                        }
                        if ui.button("Cancel").clicked() {
                            self.confirm_close = false;
                        }
                    });
                    if self.status_is_error {
                        ui.add_space(4.0);
                        ui.label(egui::RichText::new(&self.status).color(palette.err));
                    }
                });
        }
        if std::env::var_os("MPMB_UI_SMOKE_CONSOLE").is_some() {
            if let Some(dir) = self.smoke.clone() {
                if self.smoke_phase < 7 {
                    self.console_smoke(ctx, &dir);
                }
            }
        }
        if let Some(dir) = self
            .smoke
            .clone()
            .filter(|_| std::env::var_os("MPMB_UI_SMOKE_CONSOLE").is_none())
        {
            if self.texture.is_some() && self.smoke_phase == 0 {
                ctx.send_viewport_cmd(egui::ViewportCommand::Screenshot(Default::default()));
                self.smoke_phase = 1;
            }
            if self.smoke_phase == 1 && capture(ctx, &dir.join("reader.png")) {
                self.smoke_phase = 2;
            }
            if self.smoke_phase == 2 {
                let print_smoke = std::env::var_os("MPMB_UI_SMOKE_PRINT").is_some();
                let r = self
                    .rt
                    .eval(if print_smoke {
                        "__host.command(\"Value('Print Remember','false!#TheListSeparator#!0,CSfront');PrintTheSheet()\")"
                    } else if std::env::var_os("MPMB_UI_SMOKE_BOOKMARK").is_some() {
                        "bookmarkRoot.children[0].execute();if(pageNum!==1||What('PC Name')!=='Native bookmark navigation')throw Error('Bookmark navigation failed')"
                    } else {
                        "__host.invokeMenu('ClassesButton')"
                    })
                    .map(|_| ());
                let diagnostics = self.rt.diagnostics().unwrap_or(Value::Null);
                let passed = r.is_ok()
                    && (!print_smoke
                        || diagnostics["printJobs"] == json!([{"status":"cancelled"}]));
                self.result(r);
                let _ = std::fs::write(
                    dir.join("desktop-result.json"),
                    json!({"passed":passed,"status":self.status,"diagnostics":diagnostics})
                        .to_string(),
                );
                self.smoke_phase = 3;
                if std::env::var_os("MPMB_UI_SMOKE_BOOKMARK").is_none() {
                    ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                }
            }
            if self.smoke_phase == 3
                && std::env::var_os("MPMB_UI_SMOKE_BOOKMARK").is_some()
                && self.texture.is_some()
            {
                ctx.send_viewport_cmd(egui::ViewportCommand::Screenshot(Default::default()));
                self.smoke_phase = 4;
            }
            if self.smoke_phase == 4 && capture(ctx, &dir.join("bookmark-navigation.png")) {
                self.smoke_phase = 5;
                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            }
        }
        let elapsed = self.last_tick.elapsed().as_millis() as u64;
        if elapsed > 100 {
            self.last_tick = std::time::Instant::now();
            if let Err(e) = self.rt.advance(elapsed) {
                self.status = format!("Timer failed: {e:#}");
                self.status_is_error = true;
            }
        }
        if let Ok(value) = self.rt.eval("__host.revision") {
            let revision = value.as_u64().unwrap_or(0);
            if revision != self.render_revision {
                self.render_revision = revision;
                if !self.editor.dirty {
                    let _ = self.refresh_editor();
                }
                self.texture = None;
            }
        }
        self.cache
            .ensure_metadata(&self.rt, &self.pdf, self.render_revision);
        let page_count = self.cache.page_count;
        self.page = self
            .rt
            .eval("pageNum")
            .ok()
            .and_then(|v| v.as_i64())
            .unwrap_or(self.page as i64)
            .clamp(0, (page_count - 1).max(0) as i64) as i32;

        self.handle_shortcuts(ctx, page_count);
        self.draw_toolbar(ctx, &palette, page_count);
        self.draw_status_bar(ctx, &palette, page_count);
        self.draw_sidebar(ctx, &palette);
        self.draw_canvas(ctx, &palette);
        self.draw_save_modal(ctx, &palette);
        self.draw_console(ctx);
        // Process this after text input so a close request in the same frame
        // as the final typed character cannot discard an uncommitted edit.
        if self.smoke.is_none()
            && !self.allow_close
            && ctx.input(|i| i.viewport().close_requested())
            && self.unsaved
        {
            ctx.send_viewport_cmd(egui::ViewportCommand::CancelClose);
            self.confirm_close = true;
        }
        ctx.request_repaint_after(std::time::Duration::from_millis(100));
    }
}

// A separate native window handles synchronous Acrobat dialogs while the original JS
// call remains on its stack. Every control event returns to the original handler.
pub fn modal(request: &Value) -> Result<Value> {
    let mut child = std::process::Command::new(std::env::current_exe()?)
        .arg("--dialog")
        .env("MPMB_THEME", active_theme_env())
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .spawn()?;
    child
        .stdin
        .take()
        .unwrap()
        .write_all(serde_json::to_string(request)?.as_bytes())?;
    let out = child.wait_with_output()?;
    if !out.status.success() {
        bail!("native dialog process failed")
    };
    Ok(serde_json::from_slice(&out.stdout)?)
}
fn dialog_process() -> Result<()> {
    let mut input = String::new();
    std::io::stdin().read_to_string(&mut input)?;
    let data: Value = serde_json::from_str(&input)?;
    let result = Arc::new(Mutex::new(json!({"result":"cancel"})));
    let values: BTreeMap<String, Value> = data["values"]
        .as_object()
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .collect();
    let popup_options: BTreeMap<String, Value> = values
        .iter()
        .filter(|(_, v)| v.is_object())
        .map(|(k, v)| (k.clone(), v.clone()))
        .collect();
    let app = Dialog {
        description: data["description"].clone(),
        values,
        popup_options,
        enabled: data["enabled"].clone(),
        visible: data["visible"].clone(),
        red: data["red"].clone(),
        result: result.clone(),
        images: BTreeMap::new(),
        capture_requested: false,
        focus: data["focus"].as_str().map(str::to_owned),
        focus_requested: false,
        edited_controls: BTreeSet::new(),
        alert_type: data["alert_type"].as_i64(),
        theme_mode: ThemeMode::from_env(),
        theme_applied: false,
    };
    let title = data["description"]["name"]
        .as_str()
        .unwrap_or("MPMB dialog")
        .to_owned();
    eframe::run_native(&title, dialog_options(), Box::new(|_| Ok(Box::new(app))))
        .map_err(|e| anyhow::anyhow!(e.to_string()))?;
    println!("{}", result.lock().unwrap());
    Ok(())
}
struct Dialog {
    description: Value,
    values: BTreeMap<String, Value>,
    popup_options: BTreeMap<String, Value>,
    enabled: Value,
    visible: Value,
    red: Value,
    result: Arc<Mutex<Value>>,
    images: BTreeMap<String, egui::TextureHandle>,
    capture_requested: bool,
    focus: Option<String>,
    focus_requested: bool,
    edited_controls: BTreeSet<String>,
    alert_type: Option<i64>,
    theme_mode: ThemeMode,
    theme_applied: bool,
}
fn argb_image(value: &Value) -> Option<ColorImage> {
    let argb = value["argb"].as_str()?;
    let w = value["width"].as_u64()? as usize;
    let h = value["height"].as_u64()? as usize;
    if w == 0 || h == 0 || w > 1024 || h > 1024 || argb.len() != w * h * 8 {
        return None;
    }
    let mut rgba = Vec::with_capacity(w * h * 4);
    for pixel in argb.as_bytes().chunks_exact(8) {
        let n = u32::from_str_radix(std::str::from_utf8(pixel).ok()?, 16).ok()?;
        rgba.extend_from_slice(&[
            ((n >> 16) & 255) as u8,
            ((n >> 8) & 255) as u8,
            (n & 255) as u8,
            (n >> 24) as u8,
        ]);
    }
    Some(ColorImage::from_rgba_unmultiplied([w, h], &rgba))
}
fn option_min_order(value: &Value) -> i64 {
    if let Some(n) = value.as_i64() {
        return n.saturating_abs();
    }
    value
        .as_object()
        .and_then(|map| map.values().map(option_min_order).min())
        .unwrap_or(i64::MAX)
}
fn option_leaves(value: &Value, path: &mut Vec<String>, out: &mut Vec<(Vec<String>, i64)>) {
    if let Some(object) = value.as_object() {
        let mut entries: Vec<_> = object.iter().collect();
        entries.sort_by(|(ka, va), (kb, vb)| {
            option_min_order(va)
                .cmp(&option_min_order(vb))
                .then_with(|| ka.cmp(kb))
        });
        for (name, v) in entries {
            path.push(name.clone());
            if let Some(n) = v.as_i64() {
                out.push((path.clone(), n))
            } else {
                option_leaves(v, path, out)
            }
            path.pop();
        }
    }
}
fn select_option(value: &mut Value, path: &[String], multiple: bool) {
    fn clear(value: &mut Value) {
        if let Some(object) = value.as_object_mut() {
            for v in object.values_mut() {
                if let Some(n) = v.as_i64() {
                    *v = json!(-n.abs().max(1));
                } else {
                    clear(v)
                }
            }
        }
    }
    if !multiple {
        clear(value)
    }
    let mut current = value;
    for key in path {
        current = &mut current[key];
    }
    let old = current.as_i64().unwrap_or(-1);
    *current = json!(if multiple && old > 0 {
        -old
    } else {
        old.abs().max(1)
    });
}
impl Dialog {
    fn dismiss_alert(&mut self, ctx: &egui::Context) -> bool {
        let Some(kind) = self.alert_type else {
            return false;
        };
        if self.result.lock().unwrap().get("event").is_some() {
            return false;
        }
        // Reader ignores Escape when the alert offers no Cancel button. Its
        // window-close result is resolved separately by alert() below.
        let escape = matches!(kind, 1 | 3)
            && ctx.input_mut(|i| i.consume_key(egui::Modifiers::NONE, egui::Key::Escape));
        if escape || ctx.input(|i| i.viewport().close_requested()) {
            *self.result.lock().unwrap() = json!({"result":"cancel","values":self.values});
            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            return true;
        }
        false
    }

    fn element(&mut self, ui: &mut egui::Ui, e: &Value) -> Option<Value> {
        let id = e["item_id"].as_str().unwrap_or("");
        let kind = e["type"].as_str().unwrap_or("view");
        if self.visible[id] == false || e["height"].as_i64().unwrap_or(0) < 0 {
            return None;
        }
        let mut reply = None;
        ui.add_enabled_ui(self.enabled[id] != false, |ui| {
            if let Some(children) = e["elements"].as_array() {
                // Keep source order and source labels; sizing can be refined without changing dialog semantics.
                if kind == "cluster" {
                    egui::CollapsingHeader::new(e["name"].as_str().unwrap_or("Options"))
                        .default_open(true)
                        .id_salt((id, e["name"].as_str().unwrap_or("")))
                        .show(ui, |ui| {
                            for (i, c) in children.iter().enumerate() {
                                ui.push_id(i, |ui| {
                                    if let Some(r) = self.element(ui, c) {
                                        reply = Some(r)
                                    }
                                });
                            }
                        });
                } else if matches!(
                    e["align_children"].as_str(),
                    Some("align_row" | "align_distribute")
                ) {
                    ui.horizontal_top(|ui| {
                        for (i, c) in children.iter().enumerate() {
                            ui.push_id(i, |ui| {
                                ui.vertical(|ui| {
                                    if let Some(r) = self.element(ui, c) {
                                        reply = Some(r)
                                    }
                                });
                            });
                        }
                    });
                } else {
                    for (i, c) in children.iter().enumerate() {
                        ui.push_id(i, |ui| {
                            if let Some(r) = self.element(ui, c) {
                                reply = Some(r)
                            }
                        });
                    }
                }
                return;
            }
            let name = e["name"].as_str().unwrap_or("");
            let focus_requested = &mut self.focus_requested;
            let wants_focus = self.focus.as_deref() == Some(id) && !*focus_requested;
            // Rendering a button must not invent a value in dialog.store().
            // Explicit dialog.load() captions remain available for display.
            let mut unstored = Value::Null;
            let value = if id.is_empty()
                || matches!(kind, "button" | "ok" | "ok_cancel" | "ok_cancel_other")
            {
                self.values.get_mut(id).unwrap_or(&mut unstored)
            } else {
                self.values.entry(id.into()).or_insert(json!(""))
            };
            let is_red = self.red[id] == true;
            let is_bold = e["bold"].as_bool().unwrap_or(false);
            let styled_text = |s: &str| {
                let mut text = egui::RichText::new(s);
                if is_bold {
                    text = text.strong();
                }
                if is_red {
                    text = text.color(egui::Color32::from_rgb(200, 32, 32));
                }
                text
            };
            match kind {
                "static_text" => {
                    let s = value.as_str().filter(|s| !s.is_empty()).unwrap_or(name);
                    ui.label(styled_text(s));
                }
                "link_text" => {
                    let s = value.as_str().filter(|s| !s.is_empty()).unwrap_or(name);
                    let response = ui.link(styled_text(s));
                    if wants_focus {
                        response.request_focus();
                        *focus_requested = true;
                    }
                    if response.clicked() {
                        reply = Some(json!({"event":id}));
                    }
                }
                "edit_text"
                    if e["PopupEdit"].as_bool().unwrap_or(false)
                        && (value.is_object() || self.popup_options.contains_key(id)) =>
                {
                    if value.is_object() {
                        self.popup_options.insert(id.to_owned(), value.clone());
                    }
                    let mut opts = self
                        .popup_options
                        .get(id)
                        .cloned()
                        .unwrap_or_else(|| json!({}));
                    let mut leaves = Vec::new();
                    option_leaves(&opts, &mut Vec::new(), &mut leaves);
                    let mut text = if let Some(typed) = value.as_str() {
                        typed.to_owned()
                    } else {
                        leaves
                            .iter()
                            .find(|(_, v)| *v > 0)
                            .map(|(p, _)| p.last().cloned().unwrap_or_default())
                            .unwrap_or_default()
                    };
                    let width =
                        (e["char_width"].as_f64().unwrap_or(20.) as f32 * 7.).clamp(40., 600.);
                    ui.horizontal(|ui| {
                        let response = ui.add(
                            egui::TextEdit::singleline(&mut text)
                                .desired_width((width - 28.).max(32.))
                                .interactive(!e["readonly"].as_bool().unwrap_or(false)),
                        );
                        if wants_focus {
                            response.request_focus();
                            *focus_requested = true;
                        }
                        if response.changed() {
                            *value = json!(text);
                            self.edited_controls.insert(id.to_owned());
                        }
                        if response.lost_focus() && self.edited_controls.remove(id) {
                            reply = Some(json!({"event":id}));
                        }
                        if !leaves.is_empty() {
                            egui::ComboBox::from_id_salt(("popup-edit", id))
                                .width(24.)
                                .selected_text("")
                                .show_ui(ui, |ui| {
                                    for (path, selection) in &leaves {
                                        if ui
                                            .selectable_label(*selection > 0, path.join(" › "))
                                            .clicked()
                                        {
                                            select_option(&mut opts, path, false);
                                            self.popup_options.insert(id.to_owned(), opts.clone());
                                            *value = opts.clone();
                                            reply = Some(json!({"event":id}));
                                        }
                                    }
                                });
                        }
                    });
                }
                "edit_text" | "popup" | "list_box" | "hier_list_box" if value.is_object() => {
                    let mut leaves = Vec::new();
                    option_leaves(value, &mut Vec::new(), &mut leaves);
                    if matches!(kind, "list_box" | "hier_list_box") {
                        egui::ScrollArea::vertical()
                            .id_salt(id)
                            .max_height(180.)
                            .show(ui, |ui| {
                                for (path, selection) in &leaves {
                                    let label = path.join(" › ");
                                    if ui.selectable_label(*selection > 0, label).clicked() {
                                        select_option(value, path, ui.input(|i| i.modifiers.ctrl));
                                        reply = Some(json!({"event":id}));
                                    }
                                }
                            });
                    } else {
                        let selected = leaves
                            .iter()
                            .find(|(_, v)| *v > 0)
                            .map(|(p, _)| p.last().cloned().unwrap_or_default())
                            .unwrap_or_default();
                        egui::ComboBox::from_id_salt(id)
                            .width((e["char_width"].as_f64().unwrap_or(18.) as f32 * 7.).max(100.))
                            .selected_text(selected)
                            .show_ui(ui, |ui| {
                                for (path, selection) in &leaves {
                                    if ui
                                        .selectable_label(*selection > 0, path.join(" › "))
                                        .clicked()
                                    {
                                        select_option(value, path, false);
                                        reply = Some(json!({"event":id}));
                                    }
                                }
                            });
                    }
                }
                "edit_text" => {
                    let mut text = value
                        .as_str()
                        .map(str::to_owned)
                        .unwrap_or_else(|| value.to_string());
                    let width =
                        (e["char_width"].as_f64().unwrap_or(25.) as f32 * 7.).clamp(25., 600.);
                    let readonly = e["readonly"].as_bool().unwrap_or(false);
                    let spin = e["SpinEdit"].as_bool().unwrap_or(false)
                        && !e["PopupEdit"].as_bool().unwrap_or(false)
                        && !readonly;
                    ui.horizontal(|ui| {
                        let edit = if e["multiline"].as_bool().unwrap_or(false)
                            || e["char_height"].as_i64().unwrap_or(1) > 1
                        {
                            egui::TextEdit::multiline(&mut text).desired_width(width)
                        } else {
                            egui::TextEdit::singleline(&mut text)
                                .password(e["password"].as_bool().unwrap_or(false))
                                .desired_width(width)
                        };
                        let response = ui.add(edit.interactive(!readonly));
                        if wants_focus {
                            response.request_focus();
                            *focus_requested = true;
                        }
                        if response.changed() {
                            *value = json!(text);
                            self.edited_controls.insert(id.to_owned());
                        }
                        if response.lost_focus() && self.edited_controls.remove(id) {
                            reply = Some(json!({"event":id}));
                        }
                        if spin {
                            let current = value
                                .as_str()
                                .and_then(|s| s.trim().parse::<i64>().ok())
                                .unwrap_or(0);
                            if ui.small_button("−").clicked() {
                                *value = json!(current.saturating_sub(1).to_string());
                                reply = Some(json!({"event":id}));
                            }
                            if ui.small_button("+").clicked() {
                                *value = json!(current.saturating_add(1).to_string());
                                reply = Some(json!({"event":id}));
                            }
                        }
                    });
                }
                "radio" => {
                    if ui
                        .radio(value.as_bool().unwrap_or(false), styled_text(name))
                        .clicked()
                    {
                        *value = json!(true);
                        reply = Some(json!({"event":id}));
                    }
                }
                "check_box" => {
                    let mut selected = value.as_bool().unwrap_or(false);
                    if ui.checkbox(&mut selected, styled_text(name)).changed() {
                        *value = json!(selected);
                        reply = Some(json!({"event":id}));
                    }
                }
                "popup" | "list_box" | "hier_list_box" => {
                    ui.label("No choices available");
                }
                "button" => {
                    let caption = value.as_str().filter(|s| !s.is_empty()).unwrap_or(name);
                    let response = ui.button(caption);
                    if self.focus.as_deref() == Some(id) && !self.focus_requested {
                        response.request_focus();
                        self.focus_requested = true;
                    }
                    if response.clicked() {
                        reply = Some(json!({"event":id}))
                    }
                }
                "ok" | "ok_cancel" | "ok_cancel_other" => {
                    ui.horizontal(|ui| {
                        if ui.button(e["ok_name"].as_str().unwrap_or("OK")).clicked() {
                            reply = Some(json!({"result":"ok"}))
                        }
                        if kind == "ok_cancel_other"
                            && ui
                                .button(e["other_name"].as_str().unwrap_or("Other"))
                                .clicked()
                        {
                            reply = Some(json!({"result":"other"}));
                        }
                        if kind != "ok"
                            && ui
                                .button(e["cancel_name"].as_str().unwrap_or("Cancel"))
                                .clicked()
                        {
                            reply = Some(json!({"result":"cancel"}))
                        }
                    });
                }
                "image" => {
                    if !self.images.contains_key(id) {
                        if let (Some(argb), Some(w), Some(h)) = (
                            value["argb"].as_str(),
                            value["width"].as_u64(),
                            value["height"].as_u64(),
                        ) {
                            if w > 0
                                && h > 0
                                && w <= 1024
                                && h <= 1024
                                && argb.len() == w as usize * h as usize * 8
                            {
                                let mut rgba = Vec::new();
                                let mut valid = true;
                                for pixel in argb.as_bytes().chunks_exact(8) {
                                    if let Ok(hex) = std::str::from_utf8(pixel) {
                                        if let Ok(n) = u32::from_str_radix(hex, 16) {
                                            rgba.extend_from_slice(&[
                                                ((n >> 16) & 255) as u8,
                                                ((n >> 8) & 255) as u8,
                                                (n & 255) as u8,
                                                (n >> 24) as u8,
                                            ]);
                                        } else {
                                            valid = false;
                                            break;
                                        }
                                    } else {
                                        valid = false;
                                        break;
                                    }
                                }
                                if valid {
                                    self.images.insert(
                                        id.into(),
                                        ui.ctx().load_texture(
                                            id,
                                            ColorImage::from_rgba_unmultiplied(
                                                [w as usize, h as usize],
                                                &rgba,
                                            ),
                                            Default::default(),
                                        ),
                                    );
                                }
                            }
                        }
                    }
                    if let Some(texture) = self.images.get(id) {
                        ui.image(texture);
                    }
                }
                "gap" => {
                    ui.add_space(5.);
                }
                _ => {
                    ui.colored_label(
                        egui::Color32::RED,
                        format!("Unsupported dialog control: {kind} ({id})"),
                    );
                }
            }
        });
        reply
    }
}
fn capture(ctx: &egui::Context, path: &std::path::Path) -> bool {
    ctx.input(|input| {
        for event in &input.events {
            if let egui::Event::Screenshot { image, .. } = event {
                let bytes: Vec<u8> = image.pixels.iter().flat_map(|p| p.to_array()).collect();
                if let Err(e) = image::save_buffer(
                    path,
                    &bytes,
                    image.size[0] as u32,
                    image.size[1] as u32,
                    image::ColorType::Rgba8,
                ) {
                    eprintln!("screenshot: {e}");
                    return false;
                }
                return true;
            }
        }
        false
    })
}
impl eframe::App for Dialog {
    fn update(&mut self, ctx: &egui::Context, _: &mut eframe::Frame) {
        if !self.theme_applied {
            theme::apply(ctx, self.theme_mode);
            self.theme_applied = true;
        }
        if self.dismiss_alert(ctx) {
            return;
        }
        if self.alert_type.is_none()
            && ctx.input_mut(|i| i.consume_key(egui::Modifiers::NONE, egui::Key::Escape))
        {
            *self.result.lock().unwrap() = json!({"result":"cancel","values":self.values});
            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            return;
        }
        if let Ok(dir) = std::env::var("MPMB_UI_SMOKE_DIR") {
            if !self.capture_requested {
                ctx.send_viewport_cmd(egui::ViewportCommand::Screenshot(Default::default()));
                self.capture_requested = true;
            }
            if capture(
                ctx,
                &PathBuf::from(dir).join(
                    if self.description["name"]
                        .as_str()
                        .unwrap_or("")
                        .contains("CLASS SELECTION")
                    {
                        "class-dialog.png"
                    } else {
                        "dialog.png"
                    },
                ),
            ) {
                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            }
        }
        egui::CentralPanel::default().show(ctx, |ui| {
            egui::ScrollArea::both().show(ui, |ui| {
                let description = self.description.clone();
                if let Some(mut r) = self.element(ui, &description) {
                    r["values"] = json!(self.values);
                    *self.result.lock().unwrap() = r;
                    ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                }
            });
        });
    }
}

pub fn alert(value: &Value) -> Result<Value> {
    let mut elements = vec![json!({"type":"static_text","name":value["cMsg"],"item_id":"body"})];
    let mut values = json!({});
    if !value["oCheckbox"].is_null() {
        elements.push(json!({"type":"check_box","name":value["oCheckbox"]["cMsg"].as_str().unwrap_or("Do not show this message again"),"item_id":"ckbx"}));
        values["ckbx"] = json!(value["oCheckbox"]["bInitialValue"]
            .as_bool()
            .unwrap_or(false));
    }
    let kind = value["nType"].as_i64().unwrap_or(0);
    let buttons: Vec<(&str, i32)> = match kind {
        1 => vec![("OK", 1), ("Cancel", 2)],
        2 => vec![("Yes", 4), ("No", 3)],
        3 => vec![("Yes", 4), ("No", 3), ("Cancel", 2)],
        _ => vec![("OK", 1)],
    };
    elements.push(json!({"type":"view","align_children":"align_row","elements":buttons.iter().map(|(label,number)|json!({"type":"button","name":label,"item_id":format!("btn{number}")})).collect::<Vec<_>>()}));
    loop {
        let reply = modal(
            &json!({"description":{"name":value["cTitle"].as_str().unwrap_or("MPMB"),"elements":elements},"values":values,"enabled":{},"visible":{},"alert_type":kind,"focus":format!("btn{}",buttons[0].1)}),
        )?;
        if let Some(v) = reply.get("values") {
            values = v.clone()
        }
        let event = reply["event"].as_str().unwrap_or("");
        if let Some(n) = event
            .strip_prefix("btn")
            .and_then(|s| s.parse::<i32>().ok())
        {
            return Ok(json!({"button":n,"checked":values["ckbx"]}));
        }
        if reply["result"] == "cancel" {
            // Actual Reader window-close codes: OK-only -> OK, Yes/No -> Yes,
            // and alerts offering Cancel -> Cancel. Escape only closes the
            // latter; the native dialog retains that distinction.
            let button = match kind {
                1 | 3 => 2,
                2 => 4,
                _ => 1,
            };
            return Ok(json!({"button":button,"checked":values["ckbx"]}));
        }
    }
}

#[cfg(test)]
mod dialog_tests {
    use super::*;

    #[test]
    fn page_artwork_does_not_intercept_the_editable_score_beneath_it() {
        let widgets = vec![
            json!({"name":"Con","type":"text","readonly":false,"rect":[40,440,66,458]}),
            json!({"name":"Image.calc_boxes.CSfront","type":"button","readonly":true,"rect":[30,24,566,668]}),
        ];
        assert_eq!(page_widget_hit(&widgets, 53., 449.).unwrap()["name"], "Con");
        assert_eq!(page_widget_hit(&widgets, 100., 100.), None);
        assert_eq!(page_widget_hit(&widgets, 600., 700.), None);
    }

    #[test]
    fn active_buttons_and_readonly_text_keep_their_page_hit_targets() {
        let mut widgets = vec![
            json!({"name":"Con","type":"text","readonly":false,"rect":[40,440,66,458]}),
            json!({"name":"Action","type":"button","readonly":false,"rect":[40,440,66,458]}),
        ];
        assert_eq!(
            page_widget_hit(&widgets, 53., 449.).unwrap()["name"],
            "Action"
        );
        widgets[1]["readonly"] = json!(true);
        assert_eq!(page_widget_hit(&widgets, 53., 449.).unwrap()["name"], "Con");
        widgets[1]["type"] = json!("text");
        assert_eq!(
            page_widget_hit(&widgets, 53., 449.).unwrap()["name"],
            "Action"
        );
    }

    fn alert_dialog(kind: Option<i64>) -> Dialog {
        Dialog {
            description: json!({}),
            values: BTreeMap::from([("ckbx".into(), json!(true))]),
            popup_options: BTreeMap::new(),
            enabled: json!({}),
            visible: json!({}),
            red: json!({}),
            result: Arc::new(Mutex::new(json!({"result":"pending"}))),
            images: BTreeMap::new(),
            capture_requested: false,
            focus: None,
            focus_requested: false,
            edited_controls: BTreeSet::new(),
            alert_type: kind,
            theme_mode: ThemeMode::Dark,
            theme_applied: true,
        }
    }

    #[test]
    fn alert_escape_and_window_close_preserve_distinct_reader_policies() {
        for kind in [None, Some(0), Some(1), Some(2), Some(3)] {
            for window_close in [false, true] {
                let ctx = egui::Context::default();
                let mut dialog = alert_dialog(kind);
                let mut input = egui::RawInput::default();
                if window_close {
                    input
                        .viewports
                        .entry(egui::ViewportId::ROOT)
                        .or_default()
                        .events
                        .push(egui::ViewportEvent::Close);
                } else {
                    input.events.push(egui::Event::Key {
                        key: egui::Key::Escape,
                        physical_key: None,
                        pressed: true,
                        repeat: false,
                        modifiers: egui::Modifiers::NONE,
                    });
                }
                let expected = kind.is_some() && (window_close || matches!(kind, Some(1 | 3)));
                let _ = ctx.run(input, |ctx| {
                    assert_eq!(
                        dialog.dismiss_alert(ctx),
                        expected,
                        "{kind:?}/{window_close}"
                    );
                });
                let actual = dialog.result.lock().unwrap().clone();
                assert_eq!(
                    actual,
                    if expected {
                        json!({"result":"cancel","values":{"ckbx":true}})
                    } else {
                        json!({"result":"pending"})
                    }
                );
            }
        }
    }

    #[test]
    fn alert_close_does_not_replace_an_already_selected_no_button() {
        let ctx = egui::Context::default();
        let mut dialog = alert_dialog(Some(2));
        let selected = json!({"event":"btn3","values":{"ckbx":false}});
        *dialog.result.lock().unwrap() = selected.clone();
        let mut input = egui::RawInput::default();
        input
            .viewports
            .entry(egui::ViewportId::ROOT)
            .or_default()
            .events
            .push(egui::ViewportEvent::Close);
        let _ = ctx.run(input, |ctx| assert!(!dialog.dismiss_alert(ctx)));
        assert_eq!(*dialog.result.lock().unwrap(), selected);
    }

    fn button_frame(
        ctx: &egui::Context,
        dialog: &mut Dialog,
        buttons: &Value,
        key: Option<egui::Key>,
    ) -> Option<Value> {
        let events = key
            .into_iter()
            .flat_map(|key| {
                [true, false].map(|pressed| egui::Event::Key {
                    key,
                    physical_key: None,
                    pressed,
                    repeat: false,
                    modifiers: egui::Modifiers::NONE,
                })
            })
            .collect();
        let mut reply = None;
        let _ = ctx.run(
            egui::RawInput {
                events,
                ..Default::default()
            },
            |ctx| {
                egui::CentralPanel::default().show(ctx, |ui| {
                    reply = dialog.element(ui, buttons);
                });
            },
        );
        reply
    }

    #[test]
    fn alert_default_buttons_accept_enter_without_inventing_stored_values() {
        for (kind, first, caption) in [(0, 1, "OK"), (1, 1, "OK"), (2, 4, "Yes"), (3, 4, "Yes")] {
            let ctx = egui::Context::default();
            let mut dialog = alert_dialog(Some(kind));
            dialog.focus = Some(format!("btn{first}"));
            let buttons = json!({"type":"button","name":caption,"item_id":format!("btn{first}")});
            assert_eq!(button_frame(&ctx, &mut dialog, &buttons, None), None);
            assert!(dialog.focus_requested);
            assert_eq!(
                button_frame(&ctx, &mut dialog, &buttons, Some(egui::Key::Enter)),
                Some(json!({"event":format!("btn{first}")}))
            );
            assert_eq!(
                dialog.values,
                BTreeMap::from([("ckbx".into(), json!(true))])
            );
        }
    }

    #[test]
    fn initial_button_focus_does_not_steal_a_later_tab_selection() {
        for (first, second) in [(1, 2), (4, 3)] {
            let ctx = egui::Context::default();
            let mut dialog = alert_dialog(None);
            dialog.focus = Some(format!("btn{first}"));
            let buttons = json!({"type":"view","elements":[
                {"type":"button","name":"First","item_id":format!("btn{first}")},
                {"type":"button","name":"Second","item_id":format!("btn{second}")}
            ]});
            assert_eq!(button_frame(&ctx, &mut dialog, &buttons, None), None);
            assert_eq!(
                button_frame(&ctx, &mut dialog, &buttons, Some(egui::Key::Tab)),
                None
            );
            assert_eq!(
                button_frame(&ctx, &mut dialog, &buttons, Some(egui::Key::Enter)),
                Some(json!({"event":format!("btn{second}")}))
            );
        }
    }

    #[test]
    fn dialog_readonly_edits_and_unstored_buttons_preserve_values() {
        let ctx = egui::Context::default();
        let mut dialog = Dialog {
            description: json!({}),
            values: BTreeMap::from([("read".into(), json!("locked"))]),
            popup_options: BTreeMap::new(),
            enabled: json!({}),
            visible: json!({}),
            red: json!({}),
            result: Arc::new(Mutex::new(json!({}))),
            images: BTreeMap::new(),
            capture_requested: false,
            focus: Some("read".into()),
            focus_requested: false,
            edited_controls: BTreeSet::new(),
            alert_type: None,
            theme_mode: ThemeMode::Dark,
            theme_applied: true,
        };
        for events in [vec![], vec![egui::Event::Text("changed".into())]] {
            let _ = ctx.run(
                egui::RawInput {
                    events,
                    ..Default::default()
                },
                |ctx| {
                    egui::CentralPanel::default().show(ctx, |ui| {
                        dialog.element(
                            ui,
                            &json!({"type":"edit_text","item_id":"read","readonly":true}),
                        );
                        dialog.element(
                            ui,
                            &json!({"type":"button","item_id":"butn","name":"Unused"}),
                        );
                        dialog.element(ui, &json!({"type":"ok"}));
                    });
                },
            );
        }
        assert_eq!(
            dialog.values,
            BTreeMap::from([("read".into(), json!("locked"))])
        );
        assert!(dialog.edited_controls.is_empty());
    }

    #[test]
    fn page_activation_uses_release_position_and_keys_despite_later_input() {
        let pos = egui::pos2(10., 20.);
        let rect = egui::Rect::from_min_size(egui::Pos2::ZERO, egui::vec2(100., 100.));
        let release = |button, modifiers| egui::Event::PointerButton {
            pos,
            button,
            pressed: false,
            modifiers,
        };
        let events = vec![
            release(
                egui::PointerButton::Primary,
                egui::Modifiers {
                    shift: true,
                    ctrl: true,
                    ..Default::default()
                },
            ),
            egui::Event::PointerMoved(egui::pos2(30., 40.)),
            egui::Event::Key {
                key: egui::Key::A,
                physical_key: None,
                pressed: false,
                repeat: false,
                modifiers: egui::Modifiers::NONE,
            },
        ];
        assert_eq!(
            activation_input(&events, rect),
            Some((pos, json!({"shift":true,"modifier":true})))
        );
        assert_eq!(activation_input(&events, egui::Rect::NOTHING), None);
        assert_eq!(activation_input(&[], rect), None);
        for (modifiers, expected) in [
            (
                egui::Modifiers {
                    alt: true,
                    ..Default::default()
                },
                false,
            ),
            (
                egui::Modifiers {
                    mac_cmd: true,
                    ..Default::default()
                },
                true,
            ),
        ] {
            assert_eq!(
                activation_input(&[release(egui::PointerButton::Primary, modifiers)], rect),
                Some((pos, json!({"shift":false,"modifier":expected})))
            );
            assert_eq!(
                activation_input(&[release(egui::PointerButton::Secondary, modifiers)], rect),
                None
            );
        }
    }

    #[test]
    fn dialog_typing_survives_frames_and_dispatches_after_focus_leaves() {
        let ctx = egui::Context::default();
        let mut dialog = Dialog {
            description: json!({}),
            values: BTreeMap::from([("text".into(), json!(""))]),
            popup_options: BTreeMap::new(),
            enabled: json!({}),
            visible: json!({}),
            red: json!({}),
            result: Arc::new(Mutex::new(json!({}))),
            images: BTreeMap::new(),
            capture_requested: false,
            focus: Some("text".into()),
            focus_requested: false,
            edited_controls: BTreeSet::new(),
            alert_type: None,
            theme_mode: ThemeMode::Dark,
            theme_applied: true,
        };
        let control = json!({"type":"edit_text","item_id":"text"});
        let mut frame = |events: Vec<egui::Event>| {
            let mut reply = None;
            let _ = ctx.run(
                egui::RawInput {
                    events,
                    ..Default::default()
                },
                |ctx| {
                    egui::CentralPanel::default().show(ctx, |ui| {
                        reply = dialog.element(ui, &control);
                        ui.button("Next").clicked();
                    });
                },
            );
            (dialog.values["text"].clone(), reply)
        };
        frame(vec![]);
        let (text, event) = frame(vec![egui::Event::Text("A".into())]);
        assert_eq!(text, "A");
        assert!(
            event.is_none(),
            "Typing must not invoke handlers on every character"
        );
        let (text, event) = frame(vec![egui::Event::Text("B".into())]);
        assert_eq!(text, "AB");
        assert!(event.is_none());
        let (text, event) = frame(vec![egui::Event::Key {
            key: egui::Key::Tab,
            physical_key: None,
            pressed: true,
            repeat: false,
            modifiers: egui::Modifiers::NONE,
        }]);
        assert_eq!(text, "AB");
        assert_eq!(event, Some(json!({"event":"text"})));
        assert!(
            frame(vec![]).1.is_none(),
            "A committed edit must not repeat its event"
        );
    }

    #[test]
    fn link_text_control_accepts_focus_enter_and_red_styling() {
        let ctx = egui::Context::default();
        let mut dialog = alert_dialog(None);
        dialog.values.insert("bLin".into(), json!("Source Link"));
        dialog.red = json!({"bLin": true});
        dialog.focus = Some("bLin".into());
        let link = json!({"type":"link_text","item_id":"bLin","name":"Fallback"});
        assert_eq!(button_frame(&ctx, &mut dialog, &link, None), None);
        assert!(dialog.focus_requested);
        assert_eq!(
            button_frame(&ctx, &mut dialog, &link, Some(egui::Key::Enter)),
            Some(json!({"event":"bLin"}))
        );
        assert_eq!(dialog.values["bLin"], json!("Source Link"));
    }

    #[test]
    fn option_leaves_follow_acrobat_numeric_entry_order() {
        let map = json!({
            "Zebra": -1,
            "Alpha": -3,
            "Middle": 2,
            "GroupB": {"Second": -4, "First": -2}
        });
        let mut leaves = Vec::new();
        option_leaves(&map, &mut Vec::new(), &mut leaves);
        let labels: Vec<String> = leaves.into_iter().map(|(p, _)| p.join("/")).collect();
        assert_eq!(
            labels,
            vec!["Zebra", "GroupB/First", "GroupB/Second", "Middle", "Alpha"]
        );
    }

    #[test]
    fn popup_edit_accepts_typed_text_and_dispatches_on_focus_loss() {
        let ctx = egui::Context::default();
        let mut dialog = alert_dialog(None);
        dialog
            .values
            .insert("sp01".into(), json!({"Fireball": -1, "Shield": 2}));
        dialog.focus = Some("sp01".into());
        let control = json!({"type":"edit_text","item_id":"sp01","PopupEdit":true});
        let mut frame = |events: Vec<egui::Event>| {
            let mut reply = None;
            let _ = ctx.run(
                egui::RawInput {
                    events,
                    ..Default::default()
                },
                |ctx| {
                    egui::CentralPanel::default().show(ctx, |ui| {
                        reply = dialog.element(ui, &control);
                        ui.button("Next").clicked();
                    });
                },
            );
            (dialog.values["sp01"].clone(), reply)
        };
        frame(vec![]);
        let (val, ev) = frame(vec![egui::Event::Text("!".into())]);
        assert_eq!(val, json!("Shield!"));
        assert!(ev.is_none());
        let (_, ev) = frame(vec![egui::Event::Key {
            key: egui::Key::Tab,
            physical_key: None,
            pressed: true,
            repeat: false,
            modifiers: egui::Modifiers::NONE,
        }]);
        assert_eq!(ev, Some(json!({"event":"sp01"})));
        assert_eq!(
            dialog.popup_options.get("sp01"),
            Some(&json!({"Fireball": -1, "Shield": 2}))
        );
    }

    #[test]
    fn toolbar_import_script_skips_rerun_when_import_is_cancelled() {
        let mut doc = lopdf::Document::new();
        let pages = doc.add_object(lopdf::dictionary! {"Type"=>"Pages","Kids"=>vec![],"Count"=>0});
        let root = doc.add_object(lopdf::dictionary! {"Type"=>"Catalog","Pages"=>pages});
        doc.trailer.set("Root", root);
        let pdf = Pdf {
            doc,
            fields: BTreeMap::new(),
            scripts: vec![(
                "ImportHarness".into(),
                "var runs=0; var nextImport=false; function ImportUserScriptFile(){return nextImport;} function RunUserScript(a,b){runs++;}".into(),
            )],
            order: Vec::new(),
            info: json!({}),
            bookmarks: json!({"name":"Root","children":[]}),
            path: PathBuf::from("Cargo.toml"),
            templates: BTreeMap::new(),
        };
        let rt = Runtime::new(&Arc::new(pdf), vec![], vec![], false, None, None).unwrap();
        rt.eval(TOOLBAR_IMPORT_SCRIPT_ACTION).unwrap();
        assert_eq!(rt.eval("runs").unwrap(), json!(0));
        rt.eval("nextImport = true").unwrap();
        rt.eval(TOOLBAR_IMPORT_SCRIPT_ACTION).unwrap();
        assert_eq!(rt.eval("runs").unwrap(), json!(1));
    }

    #[test]
    fn readonly_sidebar_selection_and_discard_do_not_strand_earlier_edits() {
        let mut doc = lopdf::Document::new();
        let page = doc.add_object(lopdf::dictionary! {"Type"=>"Page","MediaBox"=>vec![0.into(),0.into(),612.into(),792.into()]});
        let pages = doc
            .add_object(lopdf::dictionary! {"Type"=>"Pages","Kids"=>vec![page.into()],"Count"=>1});
        doc.get_dictionary_mut(page).unwrap().set("Parent", pages);
        let name_field = doc.add_object(lopdf::dictionary! {
            "FT"=>"Tx","T"=>lopdf::Object::string_literal("PC Name"),"V"=>lopdf::Object::string_literal(""),
            "Subtype"=>"Widget","Rect"=>vec![10.into(),700.into(),150.into(),720.into()],"P"=>page,"F"=>4
        });
        let ro_field = doc.add_object(lopdf::dictionary! {
            "FT"=>"Tx","T"=>lopdf::Object::string_literal("Str Mod"),"V"=>lopdf::Object::string_literal("+2"),
            "Ff"=>1,"Subtype"=>"Widget","Rect"=>vec![10.into(),660.into(),60.into(),680.into()],"P"=>page,"F"=>4
        });
        doc.get_dictionary_mut(page)
            .unwrap()
            .set("Annots", vec![name_field.into(), ro_field.into()]);
        let form = doc.add_object(lopdf::dictionary! {
            "Fields"=>vec![name_field.into(), ro_field.into()],
            "NeedAppearances"=>true
        });
        let root =
            doc.add_object(lopdf::dictionary! {"Type"=>"Catalog","Pages"=>pages,"AcroForm"=>form});
        doc.trailer.set("Root", root);

        let dir = std::env::temp_dir().join(format!("mpmb-sidebar-ro-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let src_path = dir.join("input.pdf");
        doc.save(&src_path).unwrap();

        let pdf = Arc::new(Pdf::open(&src_path).unwrap());
        let rt = Runtime::new(&pdf, vec![], vec![], false, None, None).unwrap();
        let mut editor = SidebarEditor::new("PC Name");
        editor.refresh(&rt).unwrap();
        assert!(!editor.readonly);
        assert!(editor.can_edit());

        // Make a valid character edit first.
        editor.value = "Saved Hero".into();
        editor.dirty = true;
        editor.select(&rt, "Str Mod").unwrap();
        assert_eq!(
            rt.eval("getField('PC Name').valueAsString").unwrap(),
            json!("Saved Hero")
        );

        // Read-only field disables editing in the sidebar model.
        assert!(editor.readonly);
        assert!(!editor.can_edit());
        assert!(!editor.dirty);
        assert_eq!(editor.value, "+2");

        // Even if a draft becomes dirty on a field whose commit fails (e.g. turned read-only),
        // discarding clears ONLY the pending draft without losing earlier committed edits.
        editor.value = "+9".into();
        editor.dirty = true;
        assert!(editor.commit_pending(&rt).is_err());
        assert!(editor.dirty);
        editor.discard(&rt).unwrap();
        assert!(!editor.dirty);
        assert_eq!(editor.value, "+2");

        // Navigation and saving now succeed and preserve the earlier character edit.
        editor.commit_pending(&rt).unwrap();
        rt.ready().unwrap();
        let out_path = dir.join("saved.pdf");
        pdf.save_new(&rt.snapshot().unwrap(), &out_path).unwrap();
        let reopened = Pdf::open(&out_path).unwrap();
        assert_eq!(reopened.fields["PC Name"].value, json!("Saved Hero"));
        assert_eq!(reopened.fields["Str Mod"].value, json!("+2"));
        let _ = std::fs::remove_dir_all(&dir);
    }
}
