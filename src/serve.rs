use crate::{
    pdf::Pdf,
    render::Renderer,
    runtime::{InteractionHandler, Runtime},
    storage::{GitConfig, GitStatus, SaveResult, SheetStore, StoreConfig},
};
use anyhow::{anyhow, bail, Context, Result};
use axum::{
    body::Bytes,
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        DefaultBodyLimit, Path as AxumPath, Query, State,
    },
    http::{header, HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use futures_util::{SinkExt, StreamExt};
use image::{codecs::png::PngEncoder, ExtendedColorType, ImageEncoder};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    net::SocketAddr,
    path::PathBuf,
    sync::{
        atomic::{AtomicU64, Ordering},
        mpsc, Arc, Mutex,
    },
    time::{Duration, Instant},
};
use tokio::sync::{broadcast, watch};

const PWA_INDEX_HTML: &str = include_str!("serve/pwa/index.html");
const PWA_STYLE_CSS: &str = include_str!("serve/pwa/style.css");
const PWA_APP_JS: &str = include_str!("serve/pwa/app.js");
const PWA_MANIFEST: &str = include_str!("serve/pwa/manifest.webmanifest");
const PWA_SW_JS: &str = include_str!("serve/pwa/sw.js");
const PWA_ICON_SVG: &str = include_str!("serve/pwa/icon.svg");

const EXTRACT_STATE_JS: &str = r#"(function(){
  function gv(n){var f=getField(n);return f?String(f.valueAsString||''):'';}
  function gb(n){var f=getField(n);if(!f)return false;var v=String(f.valueAsString||'');return v!==''&&v!=='Off'&&v!=='false';}
  var abilitiesSpec=[
    ['STR','Str','Str Mod','Str ST Mod','Str ST Prof'],
    ['DEX','Dex','Dex Mod','Dex ST Mod','Dex ST Prof'],
    ['CON','Con','Con Mod','Con ST Mod','Con ST Prof'],
    ['INT','Int','Int Mod','Int ST Mod','Int ST Prof'],
    ['WIS','Wis','Wis Mod','Wis ST Mod','Wis ST Prof'],
    ['CHA','Cha','Cha Mod','Cha ST Mod','Cha ST Prof']
  ];
  var abilities=[];
  for(var i=0;i<abilitiesSpec.length;i++){
    var a=abilitiesSpec[i];
    abilities.push({
      label:a[0],scoreField:a[1],score:gv(a[1]),modifier:gv(a[2]),
      saveMod:gv(a[3]),saveProf:gb(a[4])
    });
  }
  var skillsSpec=[
    ['Acrobatics','Acr'],['Animal Handling','Ani'],['Arcana','Arc'],['Athletics','Ath'],
    ['Deception','Dec'],['History','His'],['Insight','Ins'],['Intimidation','Inti'],
    ['Investigation','Inv'],['Medicine','Med'],['Nature','Nat'],['Perception','Perc'],
    ['Performance','Perf'],['Persuasion','Pers'],['Religion','Rel'],['Sleight of Hand','Sle'],
    ['Stealth','Ste'],['Survival','Sur']
  ];
  var skills=[];
  for(var si=0;si<skillsSpec.length;si++){
    var sk=skillsSpec[si];
    if(getField(sk[1]+' Mod')||getField(sk[1])){
      skills.push({
        label:sk[0],
        mod:gv(sk[1]+' Mod')||gv(sk[1]),
        proficient:gb(sk[1]+' Prof'),
        expertise:gb(sk[1]+' Exp')
      });
    }
  }
  var attacks=[];
  for(var ai=1;ai<=5;ai++){
    var wName=gv('BlueText.Attack.'+ai)||gv('Attack.'+ai+'.Weapon Selection');
    var toHit=gv('Attack.'+ai+'.To Hit');
    var dmg=gv('Attack.'+ai+'.Damage');
    if(wName||toHit||dmg){
      attacks.push({
        index:ai,
        name:wName||('Attack '+ai),
        toHit:toHit,
        damage:dmg,
        damageType:gv('Attack.'+ai+'.Damage Type'),
        range:gv('Attack.'+ai+'.Range'),
        description:gv('Attack.'+ai+'.Description')
      });
    }
  }
  var resources=[];
  var seenRes={};
  for(var ni=0;ni<__host.names.length;ni++){
    var fn=__host.names[ni];
    if(fn.indexOf('Limited Feature ')===0 && fn.indexOf('Limited Feature Max Usages ')!==0 && fn.indexOf('Limited Feature Used ')!==0 && fn.indexOf('Limited Feature Recovery ')!==0){
      var suffix=fn.slice('Limited Feature '.length);
      if(!seenRes[suffix]){
        seenRes[suffix]=true;
        var rName=gv(fn);
        var rMax=gv('Limited Feature Max Usages '+suffix);
        var rUsed=gv('Limited Feature Used '+suffix);
        var rRec=gv('Limited Feature Recovery '+suffix);
        if(rName||rMax){
          resources.push({
            id:suffix,name:rName||('Feature '+suffix),
            max:rMax,used:rUsed,recovery:rRec,
            usedField:'Limited Feature Used '+suffix
          });
        }
      }
    }
  }
  var spellSlots=[];
  var slotOrder=['mid','top1','top2.1','top2.2','bottom1','bottom2.1','bottom2.2'];
  for(var lvl=1;lvl<=9;lvl++){
    var total=parseInt(gv('SpellSlots.CheckboxesSet.lvl'+lvl),10)||0;
    if(total>0){
      var boxes=[];
      var usedCount=0;
      for(var bi=0;bi<slotOrder.length;bi++){
        var bName='SpellSlots.Checkboxes.lvl'+lvl+'.'+slotOrder[bi];
        var bf=getField(bName);
        if(bf && bf.display!==display.hidden && bf.display!==display.noView){
          var ch=gb(bName);
          if(ch)usedCount++;
          boxes.push({field:bName,checked:ch});
        }
      }
      if(boxes.length===0){
        for(var bj=0;bj<Math.min(total,slotOrder.length);bj++){
          var fb='SpellSlots.Checkboxes.lvl'+lvl+'.'+slotOrder[bj];
          if(getField(fb)){
            var ch2=gb(fb);
            if(ch2)usedCount++;
            boxes.push({field:fb,checked:ch2});
          }
        }
      }
      spellSlots.push({level:lvl,label:'Level '+lvl,total:total,used:usedCount,boxes:boxes});
    }
  }
  var pactTotal=parseInt(gv('Pact Magic Slots'),10)||0;
  if(pactTotal>0){
    var pBoxes=[];
    var pUsed=0;
    for(var pi=0;pi<slotOrder.length;pi++){
      var pb='SpellSlots.Checkboxes.lvl0.'+slotOrder[pi];
      var pf=getField(pb);
      if(pf && pf.display!==display.hidden && pf.display!==display.noView){
        var pc=gb(pb);
        if(pc)pUsed++;
        pBoxes.push({field:pb,checked:pc});
      }
    }
    spellSlots.unshift({level:0,label:'Pact Magic',total:pactTotal,used:pUsed,boxes:pBoxes});
  }
  var notesSpec=[
    ['Class Features','Class Features'],
    ['Racial Traits','Racial Traits'],
    ['Features','Features'],
    ['Notes','Extra.Notes']
  ];
  var notes=[];
  for(var nti=0;nti<notesSpec.length;nti++){
    var nv=gv(notesSpec[nti][1]);
    if(nv)notes.push({label:notesSpec[nti][0],field:notesSpec[nti][1],value:nv});
  }
  var fieldCatalog=[];
  for(var fi=0;fi<__host.names.length;fi++){
    var fname=__host.names[fi];
    var fo=__host.fields[fname];
    fieldCatalog.push({name:fname,type:fo?fo.type:'text',readonly:!!(fo&&fo.readonly)});
  }
  var menus=[];
  var rawMenus=__host.menuItems();
  for(var mi=0;mi<rawMenus.length;mi++){
    var rm=rawMenus[mi];
    menus.push({name:rm.name,label:rm.label,tooltip:rm.tooltip,enabled:!!rm.enabled,marked:!!rm.marked});
  }
  return {
    character:{
      name:gv('PC Name'),
      player:gv('Player Name'),
      race:gv('Race'),
      background:gv('Background'),
      classAndLevels:gv('Class and Levels'),
      level:gv('Character Level'),
      xp:gv('Experience Points')
    },
    vitals:{
      ac:gv('AC'),
      init:gv('Init'),
      speed:gv('Speed'),
      proficiency:gv('Proficiency Bonus'),
      hpCurrent:gv('HP Current'),
      hpMax:gv('HP Max'),
      hpTemp:gv('HP Temp'),
      inspiration:gb('Inspiration')
    },
    abilities:abilities,
    skills:skills,
    attacks:attacks,
    resources:resources,
    spellSlots:spellSlots,
    notes:notes,
    fields:fieldCatalog,
    menus:menus,
    bookmarks:JSON.parse(JSON.stringify(bookmarkRoot)),
    console:__host.consoleView(),
    pageCount:numPages||1,
    revision:__host.revision
  };
})()"#;

#[derive(Clone, Debug)]
pub struct ServeConfig {
    pub bind: SocketAddr,
    pub store: StoreConfig,
    pub default_sheet: Option<String>,
    pub auth_token: Option<String>,
    pub autosave: bool,
    pub git_auto_sync_secs: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PublicInteraction {
    pub id: String,
    pub kind: String,
    pub request: Value,
}

#[derive(Clone, Debug)]
enum WorkerPhase {
    Idle {
        job_id: u64,
        result: Option<std::result::Result<Value, String>>,
    },
    Running,
    WaitingInteraction {
        job_id: u64,
        interaction: PublicInteraction,
    },
}

struct PendingInteraction {
    public: PublicInteraction,
    tx: mpsc::SyncSender<Value>,
}

struct InteractionBridge {
    seq: AtomicU64,
    current_job: AtomicU64,
    active: Mutex<Option<PendingInteraction>>,
    phase_tx: watch::Sender<WorkerPhase>,
    events_tx: broadcast::Sender<Value>,
}

impl InteractionBridge {
    fn new(phase_tx: watch::Sender<WorkerPhase>, events_tx: broadcast::Sender<Value>) -> Arc<Self> {
        Arc::new(Self {
            seq: AtomicU64::new(1),
            current_job: AtomicU64::new(0),
            active: Mutex::new(None),
            phase_tx,
            events_tx,
        })
    }

    fn set_current_job(&self, job_id: u64) {
        self.current_job.store(job_id, Ordering::SeqCst);
    }

    fn active_public(&self) -> Option<PublicInteraction> {
        self.active
            .lock()
            .unwrap()
            .as_ref()
            .map(|p| p.public.clone())
    }

    fn cancel_active(&self) {
        if let Some(pending) = self.active.lock().unwrap().take() {
            let cancel_reply = if pending.public.kind == "alert" {
                let kind = pending.public.request["nType"].as_i64().unwrap_or(0);
                let button = match kind {
                    1 | 3 => 2,
                    2 => 4,
                    _ => 1,
                };
                json!({"button": button, "checked": false})
            } else {
                json!({"result": "cancel"})
            };
            let _ = pending.tx.send(cancel_reply);
            let _ = self.events_tx.send(json!({"type": "interaction_cleared"}));
        }
    }

    fn respond(&self, id: &str, reply: Value) -> Result<u64> {
        let mut active = self.active.lock().unwrap();
        let Some(pending) = active.as_ref() else {
            bail!("no active dialog or alert");
        };
        if pending.public.id != id {
            bail!("interaction id mismatch (dialog already changed)");
        }
        let pending = active.take().unwrap();
        let job_id = self.current_job.load(Ordering::SeqCst);
        let _ = self.phase_tx.send(WorkerPhase::Running);
        pending
            .tx
            .send(reply)
            .map_err(|_| anyhow!("dialog worker is no longer waiting"))?;
        let _ = self.events_tx.send(json!({"type": "interaction_cleared"}));
        Ok(job_id)
    }

    fn wait_for_user(&self, kind: &str, request: &Value) -> Result<Value> {
        let id = format!("int-{}", self.seq.fetch_add(1, Ordering::SeqCst));
        let public = PublicInteraction {
            id,
            kind: kind.to_owned(),
            request: request.clone(),
        };
        let (tx, rx) = mpsc::sync_channel(1);
        let job_id = self.current_job.load(Ordering::SeqCst);
        {
            let mut active = self.active.lock().unwrap();
            *active = Some(PendingInteraction {
                public: public.clone(),
                tx,
            });
        }
        let _ = self.phase_tx.send(WorkerPhase::WaitingInteraction {
            job_id,
            interaction: public.clone(),
        });
        let _ = self.events_tx.send(json!({
            "type": "interaction_requested",
            "interaction": public,
        }));
        let reply = rx
            .recv()
            .map_err(|_| anyhow!("interaction channel closed before reply"))?;
        Ok(reply)
    }
}

impl InteractionHandler for InteractionBridge {
    fn modal(&self, request: &Value) -> Result<Value> {
        self.wait_for_user("dialog", request)
    }

    fn alert(&self, request: &Value) -> Result<Value> {
        self.wait_for_user("alert", request)
    }

    fn launch_url(&self, url: &str, new_frame: bool) -> Result<bool> {
        let _ = self.events_tx.send(json!({
            "type": "launch_url",
            "url": url,
            "new_frame": new_frame,
        }));
        Ok(true)
    }
}

enum WorkerCommand {
    Open {
        job_id: u64,
        rel_path: String,
    },
    GetState {
        reply: mpsc::SyncSender<Result<Value>>,
    },
    GetField {
        name: String,
        reply: mpsc::SyncSender<Result<Value>>,
    },
    GetPageWidgets {
        page: i32,
        reply: mpsc::SyncSender<Result<Value>>,
    },
    RenderPagePng {
        page: i32,
        width: usize,
        reply: mpsc::SyncSender<Result<Vec<u8>>>,
    },
    Edit {
        job_id: u64,
        field: String,
        value: Value,
        mode: String,
    },
    Activate {
        job_id: u64,
        field: String,
        index: i64,
        shift: bool,
        modifier: bool,
    },
    InvokeMenu {
        job_id: u64,
        name: String,
    },
    RunCommand {
        job_id: u64,
        action: String,
    },
    RunBookmark {
        job_id: u64,
        path: String,
    },
    SaveNow {
        job_id: u64,
        force: bool,
    },
    GitSync {
        job_id: u64,
        message: String,
    },
    GitPull {
        job_id: u64,
    },
    CheckIdleAutoSync {
        idle_secs: u64,
    },
}

struct ActiveSheet {
    rel_path: String,
    pdf: Arc<Pdf>,
    rt: Runtime,
    disk_sha256: String,
    revision: u64,
    dirty_since_save: bool,
    dirty_since_sync: bool,
    last_edit_at: Option<Instant>,
    projected: Option<(u64, Vec<u8>)>,
    page_pngs: BTreeMap<(i32, u64, usize), Vec<u8>>,
    page_sizes: BTreeMap<(i32, u64), (f32, f32)>,
}

struct SheetWorker {
    store: Arc<SheetStore>,
    bridge: Arc<InteractionBridge>,
    renderer: Option<Renderer>,
    autosave: bool,
    active: Option<ActiveSheet>,
    last_save_conflict: Option<SaveResult>,
}

impl SheetWorker {
    fn run(mut self, rx: mpsc::Receiver<WorkerCommand>) {
        while let Ok(cmd) = rx.recv() {
            match cmd {
                WorkerCommand::GetState { reply } => {
                    let _ = reply.send(self.build_state_payload());
                }
                WorkerCommand::GetField { name, reply } => {
                    let _ = reply.send(self.inspect_field(&name));
                }
                WorkerCommand::GetPageWidgets { page, reply } => {
                    let _ = reply.send(self.page_widgets(page));
                }
                WorkerCommand::RenderPagePng { page, width, reply } => {
                    let _ = reply.send(self.render_page_png(page, width));
                }
                WorkerCommand::CheckIdleAutoSync { idle_secs } => {
                    if idle_secs > 0 && self.store.git_enabled() {
                        let should_sync = self.active.as_ref().is_some_and(|sh| {
                            sh.dirty_since_sync
                                && sh
                                    .last_edit_at
                                    .is_some_and(|t| t.elapsed() >= Duration::from_secs(idle_secs))
                        });
                        if should_sync {
                            if let Ok(payload) = self.do_git_sync("Auto-sync MPMB session") {
                                if let Some(git) = payload.get("git") {
                                    let _ = self.bridge.events_tx.send(json!({
                                        "type": "git_status",
                                        "git": git,
                                    }));
                                }
                                if let Some(state) = payload.get("state") {
                                    let _ = self.bridge.events_tx.send(json!({
                                        "type": "state_updated",
                                        "state": state,
                                    }));
                                }
                            }
                        }
                    }
                }
                WorkerCommand::Open { job_id, rel_path } => {
                    self.run_job(job_id, |w| w.open_sheet(&rel_path));
                }
                WorkerCommand::Edit {
                    job_id,
                    field,
                    value,
                    mode,
                } => {
                    self.run_job(job_id, |w| w.edit_field(&field, &value, &mode));
                }
                WorkerCommand::Activate {
                    job_id,
                    field,
                    index,
                    shift,
                    modifier,
                } => {
                    self.run_job(job_id, |w| w.activate_field(&field, index, shift, modifier));
                }
                WorkerCommand::InvokeMenu { job_id, name } => {
                    self.run_job(job_id, |w| w.invoke_menu(&name));
                }
                WorkerCommand::RunCommand { job_id, action } => {
                    self.run_job(job_id, |w| w.run_command(&action));
                }
                WorkerCommand::RunBookmark { job_id, path } => {
                    self.run_job(job_id, |w| w.run_bookmark(&path));
                }
                WorkerCommand::SaveNow { job_id, force } => {
                    self.run_job(job_id, |w| w.save_active(force));
                }
                WorkerCommand::GitSync { job_id, message } => {
                    self.run_job(job_id, |w| w.do_git_sync(&message));
                }
                WorkerCommand::GitPull { job_id } => {
                    self.run_job(job_id, |w| w.do_git_pull());
                }
            }
        }
    }

    fn run_job<F>(&mut self, job_id: u64, f: F)
    where
        F: FnOnce(&mut Self) -> Result<Value>,
    {
        self.bridge.set_current_job(job_id);
        let _ = self.bridge.phase_tx.send(WorkerPhase::Running);
        let outcome = f(self);
        match &outcome {
            Ok(val) => {
                if let Some(state) = val.get("state") {
                    let _ = self.bridge.events_tx.send(json!({
                        "type": "state_updated",
                        "state": state,
                    }));
                }
                if let Some(git) = val.get("git") {
                    let _ = self.bridge.events_tx.send(json!({
                        "type": "git_status",
                        "git": git,
                    }));
                }
            }
            Err(err) => {
                let _ = self.bridge.events_tx.send(json!({
                    "type": "error",
                    "message": format!("{err:#}"),
                }));
            }
        }
        let result = outcome.map_err(|e| format!("{e:#}"));
        let _ = self.bridge.phase_tx.send(WorkerPhase::Idle {
            job_id,
            result: Some(result),
        });
    }

    fn open_sheet(&mut self, rel_path: &str) -> Result<Value> {
        // Pull latest changes opportunistically if Git is enabled and clean.
        if self.store.git_enabled() {
            let _ = self.store.git_pull();
        }
        let (norm, abs, _bytes, sha) = self.store.read_sheet_bytes(rel_path)?;
        let pdf = Arc::new(Pdf::open(&abs)?);
        let rt = Runtime::new_with_interaction(
            &pdf,
            vec![],
            vec![],
            true,
            None,
            None,
            Some(self.bridge.clone()),
        )?;
        let _ = rt.ready();
        let revision = rt
            .eval("__host.revision")
            .ok()
            .and_then(|v| v.as_u64())
            .unwrap_or(0);
        self.active = Some(ActiveSheet {
            rel_path: norm,
            pdf,
            rt,
            disk_sha256: sha,
            revision,
            dirty_since_save: false,
            dirty_since_sync: false,
            last_edit_at: None,
            projected: None,
            page_pngs: BTreeMap::new(),
            page_sizes: BTreeMap::new(),
        });
        self.last_save_conflict = None;
        let state = self.build_state_payload()?;
        Ok(json!({"status": "ok", "state": state}))
    }

    fn build_state_payload(&self) -> Result<Value> {
        let git = self.store.git_status()?;
        let active_interaction = self.bridge.active_public();
        let Some(sh) = &self.active else {
            return Ok(json!({
                "open": false,
                "git": git,
                "pdfium": self.renderer.is_some(),
                "activeInteraction": active_interaction,
            }));
        };
        let mut extracted = sh.rt.eval(EXTRACT_STATE_JS)?;
        let diagnostics = sh.rt.diagnostics().unwrap_or(Value::Null);
        let obj = extracted
            .as_object_mut()
            .ok_or_else(|| anyhow!("state extraction did not return an object"))?;
        obj.insert("open".into(), json!(true));
        obj.insert("path".into(), json!(sh.rel_path));
        obj.insert("diskSha256".into(), json!(sh.disk_sha256));
        obj.insert("dirtySinceSave".into(), json!(sh.dirty_since_save));
        obj.insert("dirtySinceSync".into(), json!(sh.dirty_since_sync));
        obj.insert("diagnostics".into(), diagnostics);
        obj.insert("git".into(), serde_json::to_value(&git)?);
        obj.insert("pdfium".into(), json!(self.renderer.is_some()));
        obj.insert(
            "activeInteraction".into(),
            serde_json::to_value(&active_interaction)?,
        );
        if let Some(conflict) = &self.last_save_conflict {
            obj.insert("saveConflict".into(), serde_json::to_value(conflict)?);
        }
        Ok(extracted)
    }

    fn inspect_field(&self, name: &str) -> Result<Value> {
        let sh = self.active.as_ref().context("no sheet is open")?;
        let code = format!(
            "(function(){{var f=getField({});if(!f)return null;return {{name:f.name,value:String(f.valueAsString||''),type:f.type,editable:!!f.editable,readonly:!!f.readonly,multiline:!!f.multiline,items:(f.items||[]).map(function(it){{return Array.isArray(it)?[String(it[0]),String(it.length>1?it[1]:it[0])]:[String(it),String(it)]}})}}}})()",
            serde_json::to_string(name)?
        );
        let info = sh.rt.eval(&code)?;
        if info.is_null() {
            bail!("field not found: {name}");
        }
        Ok(info)
    }

    fn ensure_projected(&mut self) -> Result<(u64, Vec<u8>)> {
        let sh = self.active.as_mut().context("no sheet is open")?;
        let rev = sh
            .rt
            .eval("__host.revision")
            .ok()
            .and_then(|v| v.as_u64())
            .unwrap_or(sh.revision);
        sh.revision = rev;
        if let Some((cached_rev, bytes)) = &sh.projected {
            if *cached_rev == rev {
                return Ok((rev, bytes.clone()));
            }
        }
        let snap = sh.rt.snapshot()?;
        let bytes = sh.pdf.project(&snap)?;
        sh.projected = Some((rev, bytes.clone()));
        Ok((rev, bytes))
    }

    fn page_widgets(&mut self, page: i32) -> Result<Value> {
        let (rev, projected) = self.ensure_projected()?;
        let sh = self.active.as_mut().context("no sheet is open")?;
        let widgets = sh
            .rt
            .eval(&format!("__host.pageWidgets({page})"))
            .unwrap_or_else(|_| json!([]));
        let size = if let Some(&sz) = sh.page_sizes.get(&(page, rev)) {
            sz
        } else if let Some(renderer) = &self.renderer {
            let _ = renderer.render(&projected, page, 320);
            let sz = renderer.page_size.get();
            if sz.0 > 0.0 && sz.1 > 0.0 {
                sh.page_sizes.insert((page, rev), sz);
                sz
            } else {
                (612.0, 792.0)
            }
        } else {
            (612.0, 792.0)
        };
        Ok(json!({
            "page": page,
            "revision": rev,
            "pageSize": [size.0, size.1],
            "widgets": widgets,
        }))
    }

    fn render_page_png(&mut self, page: i32, width: usize) -> Result<Vec<u8>> {
        let width = width.clamp(320, 2200);
        let quantized_w = ((width as f32 / 64.0).round() as usize * 64).clamp(320, 2200);
        let (rev, projected) = self.ensure_projected()?;
        let sh = self.active.as_mut().context("no sheet is open")?;
        if let Some(png) = sh.page_pngs.get(&(page, rev, quantized_w)) {
            return Ok(png.clone());
        }
        let renderer = self
            .renderer
            .as_ref()
            .context("PDFium renderer is unavailable on this server")?;
        let (w, h, rgba) = renderer.render(&projected, page, quantized_w)?;
        let sz = renderer.page_size.get();
        if sz.0 > 0.0 && sz.1 > 0.0 {
            sh.page_sizes.insert((page, rev), sz);
        }
        let mut png_bytes = Vec::new();
        let encoder = PngEncoder::new(&mut png_bytes);
        encoder.write_image(&rgba, w as u32, h as u32, ExtendedColorType::Rgba8)?;
        if sh.page_pngs.len() >= 16 {
            sh.page_pngs.clear();
        }
        sh.page_pngs
            .insert((page, rev, quantized_w), png_bytes.clone());
        Ok(png_bytes)
    }

    fn after_mutation(&mut self) -> Result<Value> {
        {
            let sh = self.active.as_mut().context("no sheet is open")?;
            let _ = sh.rt.ready();
            let next_rev = sh
                .rt
                .eval("__host.revision")
                .ok()
                .and_then(|v| v.as_u64())
                .unwrap_or(sh.revision);
            if next_rev != sh.revision {
                sh.revision = next_rev;
                sh.projected = None;
                sh.page_pngs.clear();
                sh.dirty_since_save = true;
                sh.dirty_since_sync = true;
                sh.last_edit_at = Some(Instant::now());
            }
        }
        if self.autosave && self.active.as_ref().is_some_and(|s| s.dirty_since_save) {
            let _ = self.persist_active(false)?;
        }
        let state = self.build_state_payload()?;
        Ok(json!({"status": "ok", "state": state}))
    }

    fn edit_field(&mut self, field: &str, value: &Value, mode: &str) -> Result<Value> {
        {
            let sh = self.active.as_ref().context("no sheet is open")?;
            match mode {
                "choice" => sh.rt.select_choice(field, value)?,
                "direct" => sh.rt.edit(field, value)?,
                _ => sh.rt.user_edit(field, value)?,
            }
        }
        self.after_mutation()
    }

    fn activate_field(
        &mut self,
        field: &str,
        index: i64,
        shift: bool,
        modifier: bool,
    ) -> Result<Value> {
        {
            let sh = self.active.as_ref().context("no sheet is open")?;
            let qname = serde_json::to_string(field)?;
            let mods = json!({"shift": shift, "modifier": modifier});
            sh.rt
                .eval(&format!("__host.activate({qname},{index},{mods})"))?;
        }
        self.after_mutation()
    }

    fn invoke_menu(&mut self, name: &str) -> Result<Value> {
        {
            let sh = self.active.as_ref().context("no sheet is open")?;
            let qname = serde_json::to_string(name)?;
            sh.rt.eval(&format!("__host.invokeMenu({qname})"))?;
        }
        self.after_mutation()
    }

    fn run_command(&mut self, action: &str) -> Result<Value> {
        {
            let sh = self.active.as_ref().context("no sheet is open")?;
            match action {
                "short_rest" => {
                    sh.rt.command(
                        "if(typeof resetLimFeaUsed==='function')resetLimFeaUsed('short rest');calculateNow();",
                    )?;
                }
                "long_rest" => {
                    sh.rt.command(
                        "if(typeof resetLimFeaUsed==='function')resetLimFeaUsed('long rest');var hm=getField('HP Max'),hc=getField('HP Current');if(hm&&hc&&hm.valueAsString)hc.value=hm.valueAsString;calculateNow();",
                    )?;
                }
                "spell_sheet" => {
                    sh.rt.command("GenerateSpellSheet()")?;
                }
                "add_companion" => {
                    sh.rt.command("DoTemplate('AScomp','Add',null,true)")?;
                }
                "add_wildshape" => {
                    sh.rt.command("DoTemplate('WSfront','Add',null,true)")?;
                }
                "recalculate" => {
                    sh.rt.eval("calculateNow()")?;
                }
                other => bail!("unsupported command action: {other}"),
            }
        }
        self.after_mutation()
    }

    fn run_bookmark(&mut self, path: &str) -> Result<Value> {
        if !is_safe_bookmark_path(path) {
            bail!("invalid bookmark path");
        }
        {
            let sh = self.active.as_ref().context("no sheet is open")?;
            sh.rt.eval(&format!("{path}.execute()"))?;
        }
        self.after_mutation()
    }

    fn persist_active(&mut self, force: bool) -> Result<SaveResult> {
        let sh = self.active.as_mut().context("no sheet is open")?;
        sh.rt.ready()?;
        let snap = sh.rt.snapshot()?;
        let pdf_bytes = sh.pdf.project(&snap)?;
        let rev = sh
            .rt
            .eval("__host.revision")
            .ok()
            .and_then(|v| v.as_u64())
            .unwrap_or(sh.revision);
        sh.revision = rev;
        sh.projected = Some((rev, pdf_bytes.clone()));

        let extracted = sh.rt.eval(EXTRACT_STATE_JS).unwrap_or(Value::Null);
        let sidecar = build_state_sidecar(
            &sh.rel_path,
            &extracted,
            &crate::storage::sha256_hex(&pdf_bytes),
        );
        let save_res = self.store.save_sheet_atomic(
            &sh.rel_path,
            &pdf_bytes,
            Some(&sh.disk_sha256),
            Some(&sidecar),
            force,
        )?;
        match &save_res {
            SaveResult::Saved { sha256, .. } => {
                sh.disk_sha256 = sha256.clone();
                sh.dirty_since_save = false;
                sh.dirty_since_sync = true;
                self.last_save_conflict = None;
            }
            SaveResult::Conflict { .. } => {
                self.last_save_conflict = Some(save_res.clone());
            }
        }
        Ok(save_res)
    }

    fn save_active(&mut self, force: bool) -> Result<Value> {
        let res = self.persist_active(force)?;
        let state = self.build_state_payload()?;
        let message = match &res {
            SaveResult::Saved { .. } => "Saved PDF & state sidecar to disk",
            SaveResult::Conflict { .. } => {
                "File changed externally on disk; pass force=true or pull before overwriting"
            }
        };
        Ok(json!({
            "status": "ok",
            "save": res,
            "message": message,
            "state": state,
        }))
    }

    fn do_git_sync(&mut self, message: &str) -> Result<Value> {
        if self.active.is_some() {
            let save = self.persist_active(false)?;
            if let SaveResult::Conflict { .. } = save {
                bail!("PDF changed externally on disk; resolve conflict before syncing");
            }
        }
        let commit_msg = if message.trim().is_empty() {
            if let Some(sh) = &self.active {
                let name = sh
                    .rt
                    .eval("getField('PC Name')?getField('PC Name').valueAsString:''")
                    .ok()
                    .and_then(|v| v.as_str().map(str::trim).map(str::to_owned))
                    .filter(|s| !s.is_empty())
                    .unwrap_or_else(|| sh.rel_path.clone());
                format!("Update {name} (rev {})", sh.revision)
            } else {
                "Sync MPMB character sheets".into()
            }
        } else {
            message.trim().to_owned()
        };
        let sync = self.store.git_sync(&commit_msg)?;
        if let Some(sh) = &mut self.active {
            if sync.pushed {
                sh.dirty_since_sync = false;
            }
        }
        let git = self.store.git_status()?;
        let state = self.build_state_payload()?;
        Ok(json!({
            "status": "ok",
            "sync": sync,
            "git": git,
            "state": state,
        }))
    }

    fn do_git_pull(&mut self) -> Result<Value> {
        let pull = self.store.git_pull()?;
        if pull.updated {
            if let Some(rel) = self.active.as_ref().map(|s| s.rel_path.clone()) {
                if self.store.read_sheet_bytes(&rel).is_ok() {
                    let _ = self.open_sheet(&rel)?;
                }
            }
        }
        let git = self.store.git_status()?;
        let state = self.build_state_payload()?;
        Ok(json!({
            "status": "ok",
            "pull": pull,
            "git": git,
            "state": state,
        }))
    }
}

fn build_state_sidecar(rel_path: &str, extracted: &Value, pdf_sha256: &str) -> Value {
    json!({
        "schema": "mpmb-sheet-state/v1",
        "sheet": rel_path,
        "pdfSha256": pdf_sha256,
        "revision": extracted["revision"],
        "pageCount": extracted["pageCount"],
        "character": extracted["character"],
        "vitals": extracted["vitals"],
        "abilities": extracted["abilities"],
        "resources": extracted["resources"],
        "spellSlots": extracted["spellSlots"].as_array().map(|arr| {
            arr.iter().map(|s| json!({
                "label": s["label"],
                "used": s["used"],
                "total": s["total"],
            })).collect::<Vec<_>>()
        }).unwrap_or_default(),
    })
}

fn is_safe_bookmark_path(path: &str) -> bool {
    let Some(mut rest) = path.strip_prefix("bookmarkRoot") else {
        return false;
    };
    if rest.is_empty() {
        return false;
    }
    while !rest.is_empty() {
        let Some(after_prefix) = rest.strip_prefix(".children[") else {
            return false;
        };
        let Some(close) = after_prefix.find(']') else {
            return false;
        };
        let idx = &after_prefix[..close];
        if idx.is_empty() || !idx.bytes().all(|b| b.is_ascii_digit()) {
            return false;
        }
        rest = &after_prefix[close + 1..];
    }
    true
}

#[derive(Clone)]
struct AppState {
    store: Arc<SheetStore>,
    bridge: Arc<InteractionBridge>,
    cmd_tx: mpsc::Sender<WorkerCommand>,
    job_seq: Arc<AtomicU64>,
    phase_rx: watch::Receiver<WorkerPhase>,
    auth_token: Option<String>,
    pdfium_available: bool,
}

impl AppState {
    fn start(config: &ServeConfig) -> Result<Self> {
        let store = Arc::new(SheetStore::open(config.store.clone())?);
        let (phase_tx, phase_rx) = watch::channel(WorkerPhase::Idle {
            job_id: 0,
            result: None,
        });
        let (events_tx, _) = broadcast::channel(64);
        let bridge = InteractionBridge::new(phase_tx, events_tx);
        let (cmd_tx, cmd_rx) = mpsc::channel();

        let (ready_tx, ready_rx) = mpsc::sync_channel::<bool>(1);
        let worker_store = Arc::clone(&store);
        let worker_bridge = Arc::clone(&bridge);
        let autosave = config.autosave;
        std::thread::Builder::new()
            .name("mpmb-sheet-worker".into())
            .spawn(move || {
                let renderer = match Renderer::new() {
                    Ok(r) => Some(r),
                    Err(err) => {
                        eprintln!(
                            "WARN: PDFium unavailable ({err:#}); page rendering will return 503"
                        );
                        None
                    }
                };
                let _ = ready_tx.send(renderer.is_some());
                let worker = SheetWorker {
                    store: worker_store,
                    bridge: worker_bridge,
                    renderer,
                    autosave,
                    active: None,
                    last_save_conflict: None,
                };
                worker.run(cmd_rx);
            })
            .context("failed to spawn sheet worker thread")?;
        let pdfium_available = ready_rx.recv().unwrap_or(false);

        let state = Self {
            store,
            bridge,
            cmd_tx,
            job_seq: Arc::new(AtomicU64::new(1)),
            phase_rx,
            auth_token: config.auth_token.clone().filter(|t| !t.is_empty()),
            pdfium_available,
        };

        if let Some(default_sheet) = &config.default_sheet {
            let job_id = state.job_seq.fetch_add(1, Ordering::SeqCst);
            let _ = state.cmd_tx.send(WorkerCommand::Open {
                job_id,
                rel_path: default_sheet.clone(),
            });
        }
        Ok(state)
    }

    fn check_auth(&self, headers: &HeaderMap, query_token: Option<&str>) -> bool {
        let Some(expected) = &self.auth_token else {
            return true;
        };
        if let Some(q) = query_token {
            if constant_time_eq(q.as_bytes(), expected.as_bytes()) {
                return true;
            }
        }
        if let Some(auth) = headers
            .get(header::AUTHORIZATION)
            .and_then(|v| v.to_str().ok())
        {
            if let Some(tok) = auth.strip_prefix("Bearer ") {
                if constant_time_eq(tok.trim().as_bytes(), expected.as_bytes()) {
                    return true;
                }
            }
        }
        false
    }

    async fn dispatch_job(&self, make_cmd: impl FnOnce(u64) -> WorkerCommand) -> Response {
        if let Some(active) = self.bridge.active_public() {
            return (
                StatusCode::CONFLICT,
                Json(json!({
                    "status": "interaction_required",
                    "error": "A dialog or alert is currently waiting for a response",
                    "interaction": active,
                })),
            )
                .into_response();
        }
        let mut rx = self.phase_rx.clone();
        let job_id = self.job_seq.fetch_add(1, Ordering::SeqCst);
        if self.cmd_tx.send(make_cmd(job_id)).is_err() {
            return err_response(StatusCode::INTERNAL_SERVER_ERROR, "sheet worker stopped");
        }
        self.await_job_or_interaction(&mut rx, job_id, None).await
    }

    async fn await_job_or_interaction(
        &self,
        rx: &mut watch::Receiver<WorkerPhase>,
        target_job_id: u64,
        previous_interaction_id: Option<&str>,
    ) -> Response {
        loop {
            let snapshot = rx.borrow().clone();
            match snapshot {
                WorkerPhase::Idle { job_id, result } if job_id >= target_job_id => {
                    return match result {
                        Some(Ok(val)) => (StatusCode::OK, Json(val)).into_response(),
                        Some(Err(msg)) => err_response(StatusCode::BAD_REQUEST, msg),
                        None => err_response(StatusCode::INTERNAL_SERVER_ERROR, "empty job result"),
                    };
                }
                WorkerPhase::WaitingInteraction {
                    job_id,
                    interaction,
                } if job_id == target_job_id
                    && previous_interaction_id != Some(interaction.id.as_str()) =>
                {
                    return (
                        StatusCode::ACCEPTED,
                        Json(json!({
                            "status": "interaction_required",
                            "interaction": interaction,
                        })),
                    )
                        .into_response();
                }
                _ => {
                    if rx.changed().await.is_err() {
                        return err_response(
                            StatusCode::INTERNAL_SERVER_ERROR,
                            "sheet worker terminated",
                        );
                    }
                }
            }
        }
    }
}

fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    if a.len() != b.len() {
        return false;
    }
    let mut diff = 0u8;
    for (&x, &y) in a.iter().zip(b.iter()) {
        diff |= x ^ y;
    }
    diff == 0
}

fn err_response(status: StatusCode, msg: impl Into<String>) -> Response {
    (status, Json(json!({"error": msg.into()}))).into_response()
}

#[derive(Deserialize, Default)]
struct TokenQuery {
    token: Option<String>,
}

#[derive(Deserialize)]
struct UploadQuery {
    name: String,
    #[serde(default)]
    overwrite: bool,
    token: Option<String>,
}

#[derive(Deserialize)]
struct OpenRequest {
    path: String,
}

#[derive(Deserialize)]
struct FieldQuery {
    name: String,
    token: Option<String>,
}

#[derive(Deserialize)]
struct PageImageQuery {
    w: Option<usize>,
    token: Option<String>,
}

#[derive(Deserialize)]
struct EditRequest {
    field: String,
    value: Value,
    #[serde(default = "default_edit_mode")]
    mode: String,
}

fn default_edit_mode() -> String {
    "user".into()
}

#[derive(Deserialize)]
struct ActivateRequest {
    field: String,
    #[serde(default)]
    index: i64,
    #[serde(default)]
    shift: bool,
    #[serde(default)]
    modifier: bool,
}

#[derive(Deserialize)]
struct MenuRequest {
    name: String,
}

#[derive(Deserialize)]
struct CommandRequest {
    action: String,
}

#[derive(Deserialize)]
struct BookmarkRequest {
    path: String,
}

#[derive(Deserialize, Default)]
struct SaveRequest {
    #[serde(default)]
    force: bool,
}

#[derive(Deserialize, Default)]
struct SyncRequest {
    #[serde(default)]
    message: String,
}

#[derive(Deserialize, Default)]
struct HistoryQuery {
    path: Option<String>,
    limit: Option<usize>,
    token: Option<String>,
}

fn build_router(state: AppState) -> Router {
    Router::new()
        .route("/healthz", get(handle_healthz))
        .route("/", get(handle_index))
        .route("/style.css", get(handle_css))
        .route("/app.js", get(handle_js))
        .route("/manifest.webmanifest", get(handle_manifest))
        .route("/sw.js", get(handle_sw))
        .route("/icon.svg", get(handle_icon))
        .route("/ws", get(handle_ws))
        .route("/api/sheets", get(handle_list_sheets))
        .route(
            "/api/sheets/upload",
            post(handle_upload_sheet).layer(DefaultBodyLimit::max(crate::storage::MAX_PDF_BYTES)),
        )
        .route("/api/sheets/{*path}", get(handle_download_sheet))
        .route("/api/session/open", post(handle_open_session))
        .route("/api/session/state", get(handle_session_state))
        .route("/api/session/field", get(handle_get_field))
        .route("/api/session/edit", post(handle_edit_field))
        .route("/api/session/activate", post(handle_activate_field))
        .route("/api/session/menu", post(handle_invoke_menu))
        .route("/api/session/command", post(handle_run_command))
        .route("/api/session/bookmark", post(handle_run_bookmark))
        .route("/api/session/save", post(handle_save_session))
        .route("/api/session/page/{page}/image", get(handle_page_image))
        .route("/api/session/page/{page}/widgets", get(handle_page_widgets))
        .route(
            "/api/session/interaction/{id}",
            post(handle_interaction_reply),
        )
        .route("/api/git/status", get(handle_git_status))
        .route("/api/git/sync", post(handle_git_sync))
        .route("/api/git/pull", post(handle_git_pull))
        .route("/api/git/history", get(handle_git_history))
        .with_state(state)
}

async fn handle_healthz(State(state): State<AppState>) -> impl IntoResponse {
    let git: Option<GitStatus> = state.store.git_status().ok();
    Json(json!({
        "ok": true,
        "version": env!("CARGO_PKG_VERSION"),
        "pdfium": state.pdfium_available,
        "gitEnabled": state.store.git_enabled(),
        "gitBranch": git.and_then(|g| g.branch),
    }))
}

async fn handle_index() -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, "text/html; charset=utf-8")],
        PWA_INDEX_HTML,
    )
}
async fn handle_css() -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, "text/css; charset=utf-8")],
        PWA_STYLE_CSS,
    )
}
async fn handle_js() -> impl IntoResponse {
    (
        [(
            header::CONTENT_TYPE,
            "application/javascript; charset=utf-8",
        )],
        PWA_APP_JS,
    )
}
async fn handle_manifest() -> impl IntoResponse {
    (
        [(
            header::CONTENT_TYPE,
            "application/manifest+json; charset=utf-8",
        )],
        PWA_MANIFEST,
    )
}
async fn handle_sw() -> impl IntoResponse {
    (
        [
            (
                header::CONTENT_TYPE,
                "application/javascript; charset=utf-8",
            ),
            (header::CACHE_CONTROL, "no-cache"),
        ],
        PWA_SW_JS,
    )
}
async fn handle_icon() -> impl IntoResponse {
    ([(header::CONTENT_TYPE, "image/svg+xml")], PWA_ICON_SVG)
}

async fn handle_ws(
    ws: WebSocketUpgrade,
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<TokenQuery>,
) -> Response {
    if !state.check_auth(&headers, q.token.as_deref()) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    ws.on_upgrade(move |socket| ws_loop(socket, state))
}

async fn ws_loop(socket: WebSocket, state: AppState) {
    let mut rx = state.bridge.events_tx.subscribe();
    let (mut sender, mut receiver) = socket.split();
    if let Some(inter) = state.bridge.active_public() {
        let _ = sender
            .send(Message::Text(
                json!({"type": "interaction_requested", "interaction": inter})
                    .to_string()
                    .into(),
            ))
            .await;
    }
    let send_task = tokio::spawn(async move {
        while let Ok(ev) = rx.recv().await {
            if sender
                .send(Message::Text(ev.to_string().into()))
                .await
                .is_err()
            {
                break;
            }
        }
    });
    while let Some(Ok(msg)) = receiver.next().await {
        if matches!(msg, Message::Close(_)) {
            break;
        }
    }
    send_task.abort();
}

async fn handle_list_sheets(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<TokenQuery>,
) -> Response {
    if !state.check_auth(&headers, q.token.as_deref()) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    let store = Arc::clone(&state.store);
    match tokio::task::spawn_blocking(move || -> Result<Value> {
        let sheets = store.list_sheets()?;
        let git = store.git_status()?;
        Ok(json!({"sheets": sheets, "git": git}))
    })
    .await
    {
        Ok(Ok(v)) => Json(v).into_response(),
        Ok(Err(e)) => err_response(StatusCode::INTERNAL_SERVER_ERROR, format!("{e:#}")),
        Err(e) => err_response(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()),
    }
}

async fn handle_upload_sheet(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<UploadQuery>,
    body: Bytes,
) -> Response {
    if !state.check_auth(&headers, q.token.as_deref()) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    let store = Arc::clone(&state.store);
    match tokio::task::spawn_blocking(move || store.upload_sheet(&q.name, &body, q.overwrite)).await
    {
        Ok(Ok(entry)) => (StatusCode::CREATED, Json(json!({"sheet": entry}))).into_response(),
        Ok(Err(e)) => err_response(StatusCode::BAD_REQUEST, format!("{e:#}")),
        Err(e) => err_response(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()),
    }
}

async fn handle_download_sheet(
    State(state): State<AppState>,
    headers: HeaderMap,
    AxumPath(raw_path): AxumPath<String>,
    Query(q): Query<TokenQuery>,
) -> Response {
    if !state.check_auth(&headers, q.token.as_deref()) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    let rel = raw_path
        .strip_suffix("/download")
        .unwrap_or(&raw_path)
        .to_owned();
    let store = Arc::clone(&state.store);
    match tokio::task::spawn_blocking(move || store.read_sheet_bytes(&rel)).await {
        Ok(Ok((norm, _, bytes, _))) => {
            let fname = norm.rsplit('/').next().unwrap_or("sheet.pdf");
            (
                [
                    (header::CONTENT_TYPE, "application/pdf".to_owned()),
                    (
                        header::CONTENT_DISPOSITION,
                        format!("attachment; filename=\"{}\"", fname.replace('"', "")),
                    ),
                ],
                bytes,
            )
                .into_response()
        }
        Ok(Err(e)) => err_response(StatusCode::NOT_FOUND, format!("{e:#}")),
        Err(e) => err_response(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()),
    }
}

async fn handle_open_session(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<OpenRequest>,
) -> Response {
    if !state.check_auth(&headers, None) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    // Switching sheets cancels any lingering modal on the previous sheet.
    state.bridge.cancel_active();
    state
        .dispatch_job(|job_id| WorkerCommand::Open {
            job_id,
            rel_path: req.path,
        })
        .await
}

async fn handle_session_state(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<TokenQuery>,
) -> Response {
    if !state.check_auth(&headers, q.token.as_deref()) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    if let Some(inter) = state.bridge.active_public() {
        let git = state.store.git_status().ok();
        return Json(json!({
            "open": true,
            "busy": true,
            "activeInteraction": inter,
            "git": git,
        }))
        .into_response();
    }
    let (tx, rx) = mpsc::sync_channel(1);
    if state
        .cmd_tx
        .send(WorkerCommand::GetState { reply: tx })
        .is_err()
    {
        return err_response(StatusCode::INTERNAL_SERVER_ERROR, "sheet worker stopped");
    }
    match tokio::task::spawn_blocking(move || rx.recv()).await {
        Ok(Ok(Ok(v))) => Json(v).into_response(),
        Ok(Ok(Err(e))) => err_response(StatusCode::INTERNAL_SERVER_ERROR, format!("{e:#}")),
        _ => err_response(StatusCode::INTERNAL_SERVER_ERROR, "failed reading session"),
    }
}

async fn handle_get_field(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<FieldQuery>,
) -> Response {
    if !state.check_auth(&headers, q.token.as_deref()) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    let (tx, rx) = mpsc::sync_channel(1);
    if state
        .cmd_tx
        .send(WorkerCommand::GetField {
            name: q.name,
            reply: tx,
        })
        .is_err()
    {
        return err_response(StatusCode::INTERNAL_SERVER_ERROR, "sheet worker stopped");
    }
    match tokio::task::spawn_blocking(move || rx.recv()).await {
        Ok(Ok(Ok(v))) => Json(v).into_response(),
        Ok(Ok(Err(e))) => err_response(StatusCode::NOT_FOUND, format!("{e:#}")),
        _ => err_response(StatusCode::INTERNAL_SERVER_ERROR, "failed inspecting field"),
    }
}

async fn handle_edit_field(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<EditRequest>,
) -> Response {
    if !state.check_auth(&headers, None) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    state
        .dispatch_job(|job_id| WorkerCommand::Edit {
            job_id,
            field: req.field,
            value: req.value,
            mode: req.mode,
        })
        .await
}

async fn handle_activate_field(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<ActivateRequest>,
) -> Response {
    if !state.check_auth(&headers, None) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    state
        .dispatch_job(|job_id| WorkerCommand::Activate {
            job_id,
            field: req.field,
            index: req.index,
            shift: req.shift,
            modifier: req.modifier,
        })
        .await
}

async fn handle_invoke_menu(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<MenuRequest>,
) -> Response {
    if !state.check_auth(&headers, None) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    state
        .dispatch_job(|job_id| WorkerCommand::InvokeMenu {
            job_id,
            name: req.name,
        })
        .await
}

async fn handle_run_command(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<CommandRequest>,
) -> Response {
    if !state.check_auth(&headers, None) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    state
        .dispatch_job(|job_id| WorkerCommand::RunCommand {
            job_id,
            action: req.action,
        })
        .await
}

async fn handle_run_bookmark(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<BookmarkRequest>,
) -> Response {
    if !state.check_auth(&headers, None) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    state
        .dispatch_job(|job_id| WorkerCommand::RunBookmark {
            job_id,
            path: req.path,
        })
        .await
}

async fn handle_save_session(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<SaveRequest>,
) -> Response {
    if !state.check_auth(&headers, None) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    state
        .dispatch_job(|job_id| WorkerCommand::SaveNow {
            job_id,
            force: req.force,
        })
        .await
}

async fn handle_page_image(
    State(state): State<AppState>,
    headers: HeaderMap,
    AxumPath(page): AxumPath<i32>,
    Query(q): Query<PageImageQuery>,
) -> Response {
    if !state.check_auth(&headers, q.token.as_deref()) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    let width = q.w.unwrap_or(1024);
    let (tx, rx) = mpsc::sync_channel(1);
    if state
        .cmd_tx
        .send(WorkerCommand::RenderPagePng {
            page,
            width,
            reply: tx,
        })
        .is_err()
    {
        return err_response(StatusCode::INTERNAL_SERVER_ERROR, "sheet worker stopped");
    }
    match tokio::task::spawn_blocking(move || rx.recv()).await {
        Ok(Ok(Ok(png))) => (
            [
                (header::CONTENT_TYPE, "image/png"),
                (header::CACHE_CONTROL, "private, max-age=30"),
            ],
            png,
        )
            .into_response(),
        Ok(Ok(Err(e))) => {
            let msg = format!("{e:#}");
            let status = if msg.contains("PDFium") {
                StatusCode::SERVICE_UNAVAILABLE
            } else {
                StatusCode::BAD_REQUEST
            };
            err_response(status, msg)
        }
        _ => err_response(StatusCode::INTERNAL_SERVER_ERROR, "failed rendering page"),
    }
}

async fn handle_page_widgets(
    State(state): State<AppState>,
    headers: HeaderMap,
    AxumPath(page): AxumPath<i32>,
    Query(q): Query<TokenQuery>,
) -> Response {
    if !state.check_auth(&headers, q.token.as_deref()) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    let (tx, rx) = mpsc::sync_channel(1);
    if state
        .cmd_tx
        .send(WorkerCommand::GetPageWidgets { page, reply: tx })
        .is_err()
    {
        return err_response(StatusCode::INTERNAL_SERVER_ERROR, "sheet worker stopped");
    }
    match tokio::task::spawn_blocking(move || rx.recv()).await {
        Ok(Ok(Ok(v))) => Json(v).into_response(),
        Ok(Ok(Err(e))) => err_response(StatusCode::BAD_REQUEST, format!("{e:#}")),
        _ => err_response(StatusCode::INTERNAL_SERVER_ERROR, "failed reading widgets"),
    }
}

async fn handle_interaction_reply(
    State(state): State<AppState>,
    headers: HeaderMap,
    AxumPath(id): AxumPath<String>,
    Json(reply): Json<Value>,
) -> Response {
    if !state.check_auth(&headers, None) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    let mut rx = state.phase_rx.clone();
    let job_id = match state.bridge.respond(&id, reply) {
        Ok(jid) => jid,
        Err(e) => return err_response(StatusCode::CONFLICT, format!("{e:#}")),
    };
    state
        .await_job_or_interaction(&mut rx, job_id, Some(&id))
        .await
}

async fn handle_git_status(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<TokenQuery>,
) -> Response {
    if !state.check_auth(&headers, q.token.as_deref()) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    match state.store.git_status() {
        Ok(git) => Json(git).into_response(),
        Err(e) => err_response(StatusCode::INTERNAL_SERVER_ERROR, format!("{e:#}")),
    }
}

async fn handle_git_sync(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<SyncRequest>,
) -> Response {
    if !state.check_auth(&headers, None) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    state
        .dispatch_job(|job_id| WorkerCommand::GitSync {
            job_id,
            message: req.message,
        })
        .await
}

async fn handle_git_pull(State(state): State<AppState>, headers: HeaderMap) -> Response {
    if !state.check_auth(&headers, None) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    state
        .dispatch_job(|job_id| WorkerCommand::GitPull { job_id })
        .await
}

async fn handle_git_history(
    State(state): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<HistoryQuery>,
) -> Response {
    if !state.check_auth(&headers, q.token.as_deref()) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    let store = Arc::clone(&state.store);
    match tokio::task::spawn_blocking(move || {
        store.git_history(q.path.as_deref(), q.limit.unwrap_or(20))
    })
    .await
    {
        Ok(Ok(commits)) => Json(json!({"commits": commits})).into_response(),
        Ok(Err(e)) => err_response(StatusCode::BAD_REQUEST, format!("{e:#}")),
        Err(e) => err_response(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()),
    }
}

pub fn parse_args(args: &[String]) -> Result<Option<ServeConfig>> {
    let mut bind_str =
        std::env::var("MPMB_SERVE_BIND").unwrap_or_else(|_| "0.0.0.0:8080".to_owned());
    let mut dir =
        PathBuf::from(std::env::var("MPMB_DATA_DIR").unwrap_or_else(|_| "./sheets".to_owned()));
    let mut default_sheet = std::env::var("MPMB_DEFAULT_SHEET")
        .ok()
        .filter(|s| !s.trim().is_empty());
    let mut git_repo = std::env::var("MPMB_GIT_REPO")
        .ok()
        .filter(|s| !s.trim().is_empty());
    let mut git_branch = std::env::var("MPMB_GIT_BRANCH").unwrap_or_else(|_| "main".to_owned());
    let mut git_ssh_key = std::env::var("MPMB_GIT_SSH_KEY")
        .ok()
        .filter(|s| !s.trim().is_empty())
        .map(PathBuf::from);
    let mut git_known_hosts = std::env::var("MPMB_GIT_KNOWN_HOSTS")
        .ok()
        .filter(|s| !s.trim().is_empty())
        .map(PathBuf::from);
    let mut git_token = std::env::var("MPMB_GIT_TOKEN")
        .ok()
        .filter(|s| !s.trim().is_empty());
    let mut git_author_name =
        std::env::var("MPMB_GIT_AUTHOR_NAME").unwrap_or_else(|_| "MPMB Reader".to_owned());
    let mut git_author_email =
        std::env::var("MPMB_GIT_AUTHOR_EMAIL").unwrap_or_else(|_| "mpmb-reader@local".to_owned());
    let mut auth_token = std::env::var("MPMB_AUTH_TOKEN")
        .ok()
        .filter(|s| !s.trim().is_empty());
    let mut autosave = std::env::var("MPMB_NO_AUTOSAVE").is_err();
    let mut git_auto_sync_secs: u64 = std::env::var("MPMB_GIT_AUTO_SYNC_SECS")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(300);

    let mut i = 0;
    while i < args.len() {
        let flag = args[i].as_str();
        let next = |i: &mut usize, name: &str| -> Result<String> {
            *i += 1;
            args.get(*i)
                .cloned()
                .ok_or_else(|| anyhow!("missing value for {name}"))
        };
        match flag {
            "-h" | "--help" => {
                println!(
                    "mpmb-reader serve — self-hosted iOS/web PWA server for MPMB Character Sheets\n\
                     Options (env vars in parentheses):\n\
                       --bind <addr:port>          Listen address (MPMB_SERVE_BIND, default 0.0.0.0:8080)\n\
                       --dir <path>                Sheet storage directory (MPMB_DATA_DIR, default ./sheets)\n\
                       --sheet <rel.pdf>           Auto-open sheet on startup (MPMB_DEFAULT_SHEET)\n\
                       --git-repo <url>            Private Git/GitHub repo URL (MPMB_GIT_REPO)\n\
                       --git-branch <name>         Git branch (MPMB_GIT_BRANCH, default main)\n\
                       --git-ssh-key <path>        SSH deploy key path (MPMB_GIT_SSH_KEY)\n\
                       --git-known-hosts <path>    Pinned known_hosts file (MPMB_GIT_KNOWN_HOSTS)\n\
                       --git-token <token>         HTTPS token via GIT_ASKPASS (MPMB_GIT_TOKEN)\n\
                       --git-author-name <name>    Commit author name (MPMB_GIT_AUTHOR_NAME)\n\
                       --git-author-email <email>  Commit author email (MPMB_GIT_AUTHOR_EMAIL)\n\
                       --git-auto-sync-secs <sec>  Idle Git auto-sync delay, 0 disables (MPMB_GIT_AUTO_SYNC_SECS, default 300)\n\
                       --auth-token <token>        Optional bearer/query token (MPMB_AUTH_TOKEN)\n\
                       --no-autosave               Disable automatic local disk save after edits (MPMB_NO_AUTOSAVE)"
                );
                return Ok(None);
            }
            "--bind" => bind_str = next(&mut i, "--bind")?,
            "--dir" => dir = PathBuf::from(next(&mut i, "--dir")?),
            "--sheet" => default_sheet = Some(next(&mut i, "--sheet")?),
            "--git-repo" => git_repo = Some(next(&mut i, "--git-repo")?),
            "--git-branch" => git_branch = next(&mut i, "--git-branch")?,
            "--git-ssh-key" => git_ssh_key = Some(PathBuf::from(next(&mut i, "--git-ssh-key")?)),
            "--git-known-hosts" => {
                git_known_hosts = Some(PathBuf::from(next(&mut i, "--git-known-hosts")?))
            }
            "--git-token" => git_token = Some(next(&mut i, "--git-token")?),
            "--git-author-name" => git_author_name = next(&mut i, "--git-author-name")?,
            "--git-author-email" => git_author_email = next(&mut i, "--git-author-email")?,
            "--git-auto-sync-secs" => {
                git_auto_sync_secs = next(&mut i, "--git-auto-sync-secs")?
                    .parse()
                    .context("--git-auto-sync-secs must be an integer")?;
            }
            "--auth-token" => auth_token = Some(next(&mut i, "--auth-token")?),
            "--no-autosave" => autosave = false,
            other => bail!("unknown serve option: {other}"),
        }
        i += 1;
    }

    let bind: SocketAddr = bind_str
        .parse()
        .with_context(|| format!("invalid --bind address: {bind_str}"))?;
    let git = git_repo.map(|repo_url| {
        let mut cfg = GitConfig::new(repo_url);
        cfg.branch = git_branch;
        cfg.ssh_key = git_ssh_key;
        cfg.ssh_known_hosts = git_known_hosts;
        cfg.https_token = git_token;
        cfg.author_name = git_author_name;
        cfg.author_email = git_author_email;
        cfg
    });
    Ok(Some(ServeConfig {
        bind,
        store: StoreConfig { root: dir, git },
        default_sheet,
        auth_token,
        autosave,
        git_auto_sync_secs,
    }))
}

pub fn main(args: Vec<String>) -> Result<()> {
    let Some(config) = parse_args(&args)? else {
        return Ok(());
    };
    let rt = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()?;
    rt.block_on(run_server(config))
}

async fn run_server(config: ServeConfig) -> Result<()> {
    let state = AppState::start(&config)?;
    if config.git_auto_sync_secs > 0 && state.store.git_enabled() {
        let tx = state.cmd_tx.clone();
        let idle = config.git_auto_sync_secs;
        tokio::spawn(async move {
            let mut ticker = tokio::time::interval(Duration::from_secs(15));
            loop {
                ticker.tick().await;
                if tx
                    .send(WorkerCommand::CheckIdleAutoSync { idle_secs: idle })
                    .is_err()
                {
                    break;
                }
            }
        });
    }

    let store_root = state.store.root().display().to_string();
    let app = build_router(state);
    let listener = tokio::net::TcpListener::bind(config.bind).await?;
    eprintln!(
        "mpmb-reader serve listening on http://{} (dir={store_root}, git={})",
        listener.local_addr()?,
        config.store.git.is_some()
    );
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;
    Ok(())
}

async fn shutdown_signal() {
    let ctrl_c = async {
        let _ = tokio::signal::ctrl_c().await;
    };
    #[cfg(unix)]
    let terminate = async {
        if let Ok(mut sig) =
            tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
        {
            sig.recv().await;
        }
    };
    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();
    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;
    use axum::http::Request;
    use lopdf::{dictionary, Object, StringFormat};
    use std::process::Command;
    use tower::ServiceExt;

    fn make_interactive_test_pdf(path: &std::path::Path) {
        let mut doc = lopdf::Document::with_version("1.7");
        let pages_id = doc.new_object_id();
        let page_id = doc.new_object_id();

        // Text fields: PC Name, Str, Str Mod (calculated from Str), plus interactive button triggering app.execDialog!
        let f_name = doc.add_object(dictionary! {
            "Type" => "Annot",
            "Subtype" => "Widget",
            "FT" => "Tx",
            "T" => Object::String(b"PC Name".to_vec(), StringFormat::Literal),
            "V" => Object::String(b"Initial Hero".to_vec(), StringFormat::Literal),
            "Rect" => vec![40.into(), 700.into(), 240.into(), 724.into()],
            "P" => page_id,
        });
        let f_str = doc.add_object(dictionary! {
            "Type" => "Annot",
            "Subtype" => "Widget",
            "FT" => "Tx",
            "T" => Object::String(b"Str".to_vec(), StringFormat::Literal),
            "V" => Object::String(b"10".to_vec(), StringFormat::Literal),
            "Rect" => vec![40.into(), 650.into(), 100.into(), 674.into()],
            "P" => page_id,
        });
        let calc_action = doc.add_object(dictionary! {
            "S" => "JavaScript",
            "JS" => Object::String(
                b"var s=Number(getField('Str').value)||10;var m=Math.floor((s-10)/2);event.value=(m>=0?'+':'')+m;".to_vec(),
                StringFormat::Literal,
            ),
        });
        let f_str_mod = doc.add_object(dictionary! {
            "Type" => "Annot",
            "Subtype" => "Widget",
            "FT" => "Tx",
            "T" => Object::String(b"Str Mod".to_vec(), StringFormat::Literal),
            "V" => Object::String(b"+0".to_vec(), StringFormat::Literal),
            "AA" => dictionary! { "C" => calc_action },
            "Rect" => vec![110.into(), 650.into(), 170.into(), 674.into()],
            "P" => page_id,
        });
        let btn_action = doc.add_object(dictionary! {
            "S" => "JavaScript",
            "JS" => Object::String(
                b"app.execDialog({description:{name:'Rename Hero',elements:[{type:'edit_text',item_id:'hero'},{type:'ok_cancel'}]},initialize(d){d.load({hero:getField('PC Name').valueAsString});},commit(d){getField('PC Name').value=d.store().hero;}});".to_vec(),
                StringFormat::Literal,
            ),
        });
        let f_btn = doc.add_object(dictionary! {
            "Type" => "Annot",
            "Subtype" => "Widget",
            "FT" => "Btn",
            "Ff" => 65536,
            "T" => Object::String(b"RenameButton".to_vec(), StringFormat::Literal),
            "AA" => dictionary! { "U" => btn_action },
            "Rect" => vec![260.into(), 700.into(), 360.into(), 724.into()],
            "P" => page_id,
        });

        doc.objects.insert(
            page_id,
            Object::Dictionary(dictionary! {
                "Type" => "Page",
                "Parent" => pages_id,
                "MediaBox" => vec![0.into(), 0.into(), 612.into(), 792.into()],
                "Annots" => vec![f_name.into(), f_str.into(), f_str_mod.into(), f_btn.into()],
            }),
        );
        doc.objects.insert(
            pages_id,
            Object::Dictionary(dictionary! {
                "Type" => "Pages",
                "Kids" => vec![page_id.into()],
                "Count" => 1,
            }),
        );
        let form_id = doc.add_object(dictionary! {
            "Fields" => vec![f_name.into(), f_str.into(), f_str_mod.into(), f_btn.into()],
            "CO" => vec![f_str_mod.into()],
        });
        let catalog_id = doc.add_object(dictionary! {
            "Type" => "Catalog",
            "Pages" => pages_id,
            "AcroForm" => form_id,
        });
        doc.trailer.set("Root", catalog_id);
        doc.save(path).unwrap();
    }

    async fn json_body(res: Response) -> Value {
        let bytes = axum::body::to_bytes(res.into_body(), 10 * 1024 * 1024)
            .await
            .unwrap();
        serde_json::from_slice(&bytes).unwrap()
    }

    #[tokio::test]
    async fn serve_end_to_end_edit_modal_dialog_and_git_sync() {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let base =
            std::env::temp_dir().join(format!("mpmb-serve-e2e-{}-{nanos}", std::process::id()));
        let bare = base.join("remote.git");
        let data_dir = base.join("sheets");
        std::fs::create_dir_all(&bare).unwrap();
        assert!(Command::new("git")
            .args(["init", "--bare", "-b", "main"])
            .arg(&bare)
            .status()
            .unwrap()
            .success());

        let seed_pdf = base.join("seed.pdf");
        make_interactive_test_pdf(&seed_pdf);
        let seed_bytes = std::fs::read(&seed_pdf).unwrap();

        let cfg = ServeConfig {
            bind: "127.0.0.1:0".parse().unwrap(),
            store: StoreConfig {
                root: data_dir.clone(),
                git: Some(GitConfig::new(bare.to_string_lossy().into_owned())),
            },
            default_sheet: None,
            auth_token: Some("secret-token".into()),
            autosave: true,
            git_auto_sync_secs: 0,
        };
        let state = AppState::start(&cfg).unwrap();
        let app = build_router(state);

        // 1. Health endpoint works without auth; protected endpoints reject missing token.
        let health = app
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/healthz")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(health.status(), StatusCode::OK);
        let unauth = app
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/api/sheets")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(unauth.status(), StatusCode::UNAUTHORIZED);

        // 2. Upload PDF with bearer auth.
        let up = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/sheets/upload?name=aelar.pdf")
                    .header(header::AUTHORIZATION, "Bearer secret-token")
                    .body(Body::from(seed_bytes))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(up.status(), StatusCode::CREATED);

        // 3. Open sheet and verify initial state.
        let opened = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/session/open")
                    .header(header::AUTHORIZATION, "Bearer secret-token")
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(json!({"path": "aelar.pdf"}).to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(opened.status(), StatusCode::OK);
        let opened_json = json_body(opened).await;
        assert_eq!(opened_json["state"]["character"]["name"], "Initial Hero");

        // 4. Edit Str -> 18 and verify QuickJS recalculates Str Mod -> +4!
        let edited = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/session/edit")
                    .header(header::AUTHORIZATION, "Bearer secret-token")
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(
                        json!({"field": "Str", "value": "18", "mode": "user"}).to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(edited.status(), StatusCode::OK);
        let edited_json = json_body(edited).await;
        assert_eq!(edited_json["state"]["abilities"][0]["score"], "18");
        assert_eq!(edited_json["state"]["abilities"][0]["modifier"], "+4");

        // 5. Activate RenameButton -> QuickJS blocks on app.execDialog and returns 202 with modal payload!
        let modal_res = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/session/activate")
                    .header(header::AUTHORIZATION, "Bearer secret-token")
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(
                        json!({"field": "RenameButton", "index": 0}).to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(modal_res.status(), StatusCode::ACCEPTED);
        let modal_json = json_body(modal_res).await;
        assert_eq!(modal_json["status"], "interaction_required");
        assert_eq!(modal_json["interaction"]["kind"], "dialog");
        assert_eq!(
            modal_json["interaction"]["request"]["description"]["name"],
            "Rename Hero"
        );
        let int_id = modal_json["interaction"]["id"].as_str().unwrap().to_owned();

        // 6. Reply to the live dialog -> QuickJS resumes, commits PC Name, autosaves!
        let reply_res = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri(format!("/api/session/interaction/{int_id}"))
                    .header(header::AUTHORIZATION, "Bearer secret-token")
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(
                        json!({"result": "ok", "values": {"hero": "Aelar Stormwind"}}).to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(reply_res.status(), StatusCode::OK);
        let reply_json = json_body(reply_res).await;
        assert_eq!(reply_json["state"]["character"]["name"], "Aelar Stormwind");

        // 7. Sync to Git bare remote and verify both PDF & readable state.json land in Git!
        let sync_res = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/git/sync")
                    .header(header::AUTHORIZATION, "Bearer secret-token")
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(
                        json!({"message": "Session 1 checkpoint"}).to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(sync_res.status(), StatusCode::OK);
        let sync_json = json_body(sync_res).await;
        assert_eq!(sync_json["sync"]["status"], "synced");
        assert_eq!(sync_json["sync"]["pushed"], true);

        // Verify sidecar JSON persisted in Git remote contains the updated hero name & +4 Str mod!
        let show_out = Command::new("git")
            .current_dir(&bare)
            .args(["show", "main:aelar.state.json"])
            .output()
            .unwrap();
        assert!(show_out.status.success());
        let sidecar: Value = serde_json::from_slice(&show_out.stdout).unwrap();
        assert_eq!(sidecar["character"]["name"], "Aelar Stormwind");
        assert_eq!(sidecar["abilities"][0]["modifier"], "+4");

        // 8. PWA shell assets serve cleanly.
        for path in [
            "/",
            "/style.css",
            "/app.js",
            "/manifest.webmanifest",
            "/sw.js",
            "/icon.svg",
        ] {
            let r = app
                .clone()
                .oneshot(Request::builder().uri(path).body(Body::empty()).unwrap())
                .await
                .unwrap();
            assert_eq!(r.status(), StatusCode::OK, "PWA asset failed: {path}");
        }

        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn safe_bookmark_path_rejects_injection() {
        assert!(is_safe_bookmark_path("bookmarkRoot.children[0]"));
        assert!(is_safe_bookmark_path(
            "bookmarkRoot.children[0].children[12]"
        ));
        assert!(!is_safe_bookmark_path("bookmarkRoot"));
        assert!(!is_safe_bookmark_path("bookmarkRoot.children[0];alert(1)"));
        assert!(!is_safe_bookmark_path("evil.children[0]"));
    }
}
