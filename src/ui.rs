use crate::{pdf::Pdf, render::Renderer, runtime::Runtime};
use anyhow::{bail, Result};
use eframe::egui::{self, ColorImage};
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    io::{Read, Write},
    path::PathBuf,
    sync::{Arc, Mutex},
};

pub fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.first().map(String::as_str) == Some("--dialog") {
        return dialog_process();
    }
    if args.is_empty() {
        println!("mpmb-reader <sheet.pdf> [--probe <scenario.json> <report.json>]\nPDFium: MPMB_PDFIUM or output/deps/lib/libpdfium.so\nNative UI: edit fields, class selection, page navigation and save a new copy.");
        return Ok(());
    }
    if args.iter().any(|a| a == "--strict-original-scripts") {
        std::env::set_var("MPMB_STRICT_ORIGINAL_SCRIPTS", "1");
    }
    let pdf = Pdf::open(std::path::Path::new(&args[0]))?;
    if args.get(1).map(String::as_str) == Some("--probe") {
        let scenario: Value = serde_json::from_slice(&std::fs::read(
            args.get(2)
                .ok_or_else(|| anyhow::anyhow!("missing scenario"))?,
        )?)?;
        let report_path = args
            .get(3)
            .ok_or_else(|| anyhow::anyhow!("missing report"))?;
        let mut report = json!({"passed":false,"stages":[],"script_count":pdf.scripts.len(),"field_count":pdf.fields.len(),"calculation_count":pdf.order.len()});
        let result = (|| -> Result<()> {
            let runtime = Runtime::new(
                &pdf,
                scenario["dialogs"].as_array().cloned().unwrap_or_default(),
                scenario["alerts"]
                    .as_array()
                    .unwrap_or(&vec![])
                    .iter()
                    .filter_map(|v| v.as_i64().map(|v| v as i32))
                    .collect(),
                false,
            )?;
            report["loaded_scripts"] = json!(runtime.loaded);
            if let Some(steps) = scenario["steps"].as_array() {
                for step in steps {
                    let result = match step["op"].as_str().unwrap_or("") {
                        "edit" => runtime
                            .edit(step["field"].as_str().unwrap_or(""), &step["value"])
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
    let rt = Runtime::new(
        &pdf,
        if smoke.is_some() {
            vec![json!({"result":"ok"})]
        } else {
            vec![]
        },
        if smoke.is_some() { vec![1, 1] } else { vec![] },
        true,
    )?;
    if smoke.is_some() {
        rt.advance(4100)?;
        rt.edit("PC Name", &json!("Native Vertical Slice"))?;
        rt.edit("Str", &json!("18"))?;
    }
    let edit_value = rt
        .eval("getField('PC Name').valueAsString")?
        .as_str()
        .unwrap_or("")
        .to_owned();
    let app = Reader {
        field_names: pdf.fields.keys().cloned().collect(),
        menu_images: BTreeMap::new(),
        render_revision: 0,
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
        edit_name: "PC Name".into(),
        edit_value,
        status: String::new(),
        last_tick: std::time::Instant::now(),
        save_path: format!(
            "output/testing/native-{}.pdf",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)?
                .as_millis()
        ),
    };
    eframe::run_native(
        "MPMB Linux Reader — experimental",
        options(),
        Box::new(|_| Ok(Box::new(app))),
    )
    .map_err(|e| anyhow::anyhow!(e.to_string()))
}
fn options() -> eframe::NativeOptions {
    eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default().with_inner_size([1200., 850.]),
        ..Default::default()
    }
}
struct Reader {
    field_names: Vec<String>,
    menu_images: BTreeMap<String, egui::TextureHandle>,
    render_revision: u64,
    unsaved: bool,
    confirm_close: bool,
    allow_close: bool,
    smoke: Option<PathBuf>,
    smoke_phase: u8,
    pdf: Pdf,
    rt: Runtime,
    renderer: Renderer,
    page: i32,
    texture: Option<egui::TextureHandle>,
    filter: String,
    edit_name: String,
    edit_value: String,
    status: String,
    last_tick: std::time::Instant,
    save_path: String,
}
impl Reader {
    fn result(&mut self, r: Result<()>) {
        if r.is_ok() {
            self.unsaved = true;
        }
        self.status = match r {
            Ok(_) => "Completed".into(),
            Err(e) => format!("{e:#}"),
        };
        self.texture = None;
    }
}
impl eframe::App for Reader {
    fn update(&mut self, ctx: &egui::Context, _: &mut eframe::Frame) {
        if self.smoke.is_none()
            && !self.allow_close
            && ctx.input(|i| i.viewport().close_requested())
            && self.unsaved
        {
            ctx.send_viewport_cmd(egui::ViewportCommand::CancelClose);
            self.confirm_close = true;
        }
        if self.confirm_close {
            egui::Window::new("Save your changes?")
                .collapsible(false)
                .resizable(false)
                .show(ctx, |ui| {
                    ui.label("The current document has changes. Save a new copy before closing.");
                    ui.text_edit_singleline(&mut self.save_path);
                    ui.horizontal(|ui| {
                        if ui.button("Save and close").clicked() {
                            let r =
                                self.rt
                                    .ready()
                                    .and_then(|_| self.rt.snapshot())
                                    .and_then(|s| {
                                        self.pdf.save_new(&s, std::path::Path::new(&self.save_path))
                                    });
                            let saved = r.is_ok();
                            self.result(r);
                            if saved {
                                self.unsaved = false;
                                self.allow_close = true;
                                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                            }
                        }
                        if ui.button("Discard changes").clicked() {
                            self.allow_close = true;
                            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                        }
                        if ui.button("Cancel").clicked() {
                            self.confirm_close = false;
                        }
                    });
                    ui.label(&self.status);
                });
        }
        if let Some(dir) = self.smoke.clone() {
            if self.texture.is_some() && self.smoke_phase == 0 {
                ctx.send_viewport_cmd(egui::ViewportCommand::Screenshot(Default::default()));
                self.smoke_phase = 1;
            }
            if capture(ctx, &dir.join("reader.png")) {
                self.smoke_phase = 2;
            }
            if self.smoke_phase == 2 {
                let r = self
                    .rt
                    .eval("__host.invokeMenu('ClassesButton')")
                    .map(|_| ());
                let passed = r.is_ok();
                self.result(r);
                let _ = std::fs::write(
                    dir.join("desktop-result.json"),
                    json!({"passed":passed,"status":self.status}).to_string(),
                );
                self.smoke_phase = 3;
                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            }
        }
        let elapsed = self.last_tick.elapsed().as_millis() as u64;
        if elapsed > 100 {
            self.last_tick = std::time::Instant::now();
            if let Err(e) = self.rt.advance(elapsed) {
                self.status = format!("Timer failed: {e:#}");
            }
        }
        if let Ok(value) = self.rt.eval("__host.revision") {
            let revision = value.as_u64().unwrap_or(0);
            if revision != self.render_revision {
                self.render_revision = revision;
                if let Ok(names) = self.rt.eval("__host.names") {
                    if let Some(names) = names.as_array() {
                        self.field_names = names
                            .iter()
                            .filter_map(|v| v.as_str().map(str::to_owned))
                            .collect();
                    }
                }
                self.texture = None;
            }
        }
        let page_count = self
            .rt
            .eval("numPages")
            .ok()
            .and_then(|v| v.as_u64())
            .unwrap_or(self.pdf.doc.get_pages().len() as u64) as i32;
        self.page = self.page.min(page_count - 1);
        egui::TopBottomPanel::top("toolbar").show(ctx, |ui| {
            ui.horizontal(|ui| {
                if ui.button("Previous").clicked() {
                    self.page = (self.page - 1).max(0);
                    self.texture = None
                }
                ui.label(format!("Page {} / {}", self.page + 1, page_count));
                if ui.button("Next").clicked() {
                    self.page = (self.page + 1).min(page_count - 1);
                    self.texture = None
                }
                if ui.button("Select class…").clicked() {
                    let r = self
                        .rt
                        .eval("__host.invokeMenu('ClassesButton')")
                        .map(|_| ());
                    self.result(r)
                }
                if ui.button("Import script…").clicked() {
                    let r = self
                        .rt
                        .eval("ImportUserScriptFile();RunUserScript(false,false)")
                        .map(|_| ());
                    self.result(r)
                }
                for (label, code) in [
                    ("Add companion", "DoTemplate('AScomp','Add',null,true)"),
                    (
                        "Add wild-shape page",
                        "DoTemplate('WSfront','Add',null,true)",
                    ),
                    ("Generate spells", "GenerateSpellSheet()"),
                ] {
                    if ui.button(label).clicked() {
                        let r = self.rt.command(code);
                        self.result(r)
                    }
                }
                if ui.button("Calculate").clicked() {
                    let r = self.rt.eval("calculateNow()").map(|_| ());
                    self.result(r)
                }
            });
            ui.horizontal(|ui| {
                ui.label("New copy:");
                ui.text_edit_singleline(&mut self.save_path);
                if ui.button("Save").clicked() {
                    let r = self
                        .rt
                        .ready()
                        .and_then(|_| self.rt.snapshot())
                        .and_then(|s| self.pdf.save_new(&s, std::path::Path::new(&self.save_path)));
                    let saved=r.is_ok();self.result(r);if saved{self.unsaved=false;}
                }
            });
            ui.menu_button("MPMB tools",|ui|{match self.rt.eval("__host.menuItems()"){
                Ok(items)=>if let Some(items)=items.as_array(){for item in items{let name=item["name"].as_str().unwrap_or("");if !self.menu_images.contains_key(name){if let Some(image)=argb_image(&item["icon"]){self.menu_images.insert(name.into(),ctx.load_texture(name,image,Default::default()));}}
                    ui.horizontal(|ui|{if let Some(image)=self.menu_images.get(name){ui.image(image);}
                        if ui.add_enabled(item["enabled"]==true,egui::Button::new(format!("{}{}",if item["marked"]==true{"✓ "}else{""},item["label"].as_str().unwrap_or(name)))).on_hover_text(item["tooltip"].as_str().unwrap_or("")).clicked(){let r=self.rt.eval(&format!("__host.invokeMenu({})",serde_json::to_string(name).unwrap())).map(|_|());self.result(r);ui.close();}
                    });
                }},Err(e)=>{ui.label(format!("Menu error: {e:#}"));}
            }});
            if let Ok(d)=self.rt.diagnostics(){if d["repairs"].as_array().is_some_and(|v|!v.is_empty()){ui.colored_label(egui::Color32::YELLOW,"Known sheet repair active: 2024 wild-shape typo. Original PDF scripts are preserved.");}}
            ui.label(&self.status);
        });
        egui::SidePanel::left("fields")
            .default_width(310.)
            .show(ctx, |ui| {
                ui.heading("Form fields");
                ui.text_edit_singleline(&mut self.filter);
                egui::ScrollArea::vertical()
                    .max_height(350.)
                    .show(ui, |ui| {
                        for name in &self.field_names {
                            if name.to_lowercase().contains(&self.filter.to_lowercase())
                                && ui.selectable_label(self.edit_name == *name, name).clicked()
                            {
                                self.edit_name = name.clone();
                                if let Ok(value)=self.rt.eval(&format!("getField({}).valueAsString",serde_json::to_string(name).unwrap())){self.edit_value=value.as_str().unwrap_or("").to_owned();}
                            }
                        }
                    });
                ui.separator();
                ui.label(&self.edit_name);
                ui.text_edit_multiline(&mut self.edit_value);
                if ui.button("Commit field edit").clicked() {
                    let r = self.rt.edit(&self.edit_name, &json!(self.edit_value));
                    self.result(r)
                }
                if let Ok(values)=self.rt.eval("['Str','Str Mod','Character Level','Proficiency Bonus'].map(n=>[n,getField(n).valueAsString])"){
                    if let Some(values)=values.as_array(){for item in values{ui.label(format!("{}: {}",item[0].as_str().unwrap_or(""),item[1].as_str().unwrap_or("")));}}
                }
                if let Ok(d) = self.rt.diagnostics() {
                    egui::CollapsingHeader::new("Compatibility diagnostics").show(ui, |ui| {
                        ui.label(d.to_string());
                    });
                }
            });
        egui::CentralPanel::default().show(ctx, |ui| {
            if self.texture.is_none() {
                match self
                    .rt
                    .snapshot()
                    .and_then(|s| self.pdf.project(&s))
                    .and_then(|b| self.renderer.render(&b, self.page, 1000))
                {
                    Ok((w, h, p)) => {
                        self.texture = Some(ctx.load_texture(
                            "PDF page",
                            ColorImage::from_rgba_unmultiplied([w, h], &p),
                            Default::default(),
                        ))
                    }
                    Err(e) => self.status = format!("Render failed: {e:#}"),
                }
            }
            egui::ScrollArea::both().show(ui, |ui| {
                if let Some(t) = &self.texture {
                    let response = ui.add(egui::Image::new(t).sense(egui::Sense::click()));
                    if response.clicked() {
                        if let Some(pos) = response.interact_pointer_pos() {
                            let (width, height) = self.renderer.page_size.get();
                            let x = (pos.x - response.rect.left()) / response.rect.width() * width;
                            let y = height
                                - (pos.y - response.rect.top()) / response.rect.height() * height;
                            let hit = (|| -> Result<Option<Value>> {
                                let widgets = self
                                    .rt
                                    .eval(&format!("__host.pageWidgets({})", self.page))?;
                                Ok(widgets
                                    .as_array()
                                    .and_then(|widgets| {
                                        widgets.iter().rev().find(|w| {
                                            let r = &w["rect"];
                                            x >= r[0].as_f64().unwrap_or(0.) as f32
                                                && x <= r[2].as_f64().unwrap_or(0.) as f32
                                                && y >= r[1].as_f64().unwrap_or(0.) as f32
                                                && y <= r[3].as_f64().unwrap_or(0.) as f32
                                        })
                                    })
                                    .cloned())
                            })();
                            match hit {
                                Ok(Some(w)) => {
                                    self.edit_name = w["name"].as_str().unwrap_or("").into();
                                    let name = serde_json::to_string(&self.edit_name).unwrap();
                                    let r = self
                                        .rt
                                        .eval(&format!("__host.activate({name},{})", w["index"]))
                                        .map(|_| ());
                                    self.result(r);
                                    if let Ok(value) =
                                        self.rt.eval(&format!("getField({name}).valueAsString"))
                                    {
                                        self.edit_value = value.as_str().unwrap_or("").into();
                                    }
                                }
                                Err(e) => self.status = format!("Field interaction failed: {e:#}"),
                                _ => {}
                            }
                        }
                    }
                }
            });
        });
        ctx.request_repaint_after(std::time::Duration::from_millis(100));
    }
}

// A separate native window handles synchronous Acrobat dialogs while the original JS
// call remains on its stack. Every control event returns to the original handler.
pub fn modal(request: &Value) -> Result<Value> {
    let mut child = std::process::Command::new(std::env::current_exe()?)
        .arg("--dialog")
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
    let app = Dialog {
        description: data["description"].clone(),
        values: data["values"]
            .as_object()
            .cloned()
            .unwrap_or_default()
            .into_iter()
            .collect(),
        enabled: data["enabled"].clone(),
        visible: data["visible"].clone(),
        result: result.clone(),
        images: BTreeMap::new(),
        capture_requested: false,
        focus: data["focus"].as_str().map(str::to_owned),
        focus_requested: false,
    };
    let title = data["description"]["name"]
        .as_str()
        .unwrap_or("MPMB dialog")
        .to_owned();
    eframe::run_native(&title, options(), Box::new(|_| Ok(Box::new(app))))
        .map_err(|e| anyhow::anyhow!(e.to_string()))?;
    println!("{}", result.lock().unwrap());
    Ok(())
}
struct Dialog {
    description: Value,
    values: BTreeMap<String, Value>,
    enabled: Value,
    visible: Value,
    result: Arc<Mutex<Value>>,
    images: BTreeMap<String, egui::TextureHandle>,
    capture_requested: bool,
    focus: Option<String>,
    focus_requested: bool,
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
fn option_leaves(value: &Value, path: &mut Vec<String>, out: &mut Vec<(Vec<String>, i64)>) {
    if let Some(object) = value.as_object() {
        for (name, v) in object {
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
            let value = self.values.entry(id.into()).or_insert(json!(""));
            match kind {
                "static_text" => {
                    let s = value.as_str().filter(|s| !s.is_empty()).unwrap_or(name);
                    ui.label(s);
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
                    let edit = if e["multiline"].as_bool().unwrap_or(false)
                        || e["char_height"].as_i64().unwrap_or(1) > 1
                    {
                        egui::TextEdit::multiline(&mut text).desired_width(width)
                    } else {
                        egui::TextEdit::singleline(&mut text)
                            .password(e["password"].as_bool().unwrap_or(false))
                            .desired_width(width)
                    };
                    let response = ui.add(edit);
                    if wants_focus {
                        response.request_focus();
                        *focus_requested = true;
                    }
                    if response.lost_focus() && text != value.as_str().unwrap_or("") {
                        *value = json!(text);
                        reply = Some(json!({"event":id}));
                    }
                }
                "radio" => {
                    if ui.radio(value.as_bool().unwrap_or(false), name).clicked() {
                        *value = json!(true);
                        reply = Some(json!({"event":id}));
                    }
                }
                "check_box" => {
                    let mut selected = value.as_bool().unwrap_or(false);
                    if ui.checkbox(&mut selected, name).changed() {
                        *value = json!(selected);
                        reply = Some(json!({"event":id}));
                    }
                }
                "popup" | "list_box" | "hier_list_box" => {
                    ui.label("No choices available");
                }
                "button" => {
                    let caption = value.as_str().filter(|s| !s.is_empty()).unwrap_or(name);
                    if ui.button(caption).clicked() {
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
                        if kind != "ok" && ui.button("Cancel").clicked() {
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
    let buttons: Vec<(&str, i32)> = match value["nType"].as_i64().unwrap_or(0) {
        1 => vec![("OK", 1), ("Cancel", 2)],
        2 => vec![("Yes", 4), ("No", 3)],
        3 => vec![("Yes", 4), ("No", 3), ("Cancel", 2)],
        _ => vec![("OK", 1)],
    };
    elements.push(json!({"type":"view","align_children":"align_row","elements":buttons.iter().map(|(label,number)|json!({"type":"button","name":label,"item_id":format!("btn{number}")})).collect::<Vec<_>>()}));
    loop {
        let reply = modal(
            &json!({"description":{"name":value["cTitle"].as_str().unwrap_or("MPMB"),"elements":elements},"values":values,"enabled":{},"visible":{}}),
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
            return Ok(json!({"button":2,"checked":values["ckbx"]}));
        }
    }
}
