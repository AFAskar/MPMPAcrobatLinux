use crate::{
    pdf::Pdf,
    render::Renderer,
    runtime::{HostCapabilities, InteractionHandler, Runtime},
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
  function gd(n){var f=getField(n);if(!f)return '';return f._formatted!==undefined&&f._formatted!==''?String(f._formatted):String(f.valueAsString||'');}
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
      label:a[0],scoreField:a[1],score:gv(a[1]),modifier:gd(a[2]),
      saveMod:gd(a[3]),saveProf:gb(a[4])
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
        mod:gd(sk[1]+' Mod')||gd(sk[1]),
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
      init:gd('Init'),
      speed:gv('Speed'),
      proficiency:gd('Proficiency Bonus'),
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

type JobOutcome = std::result::Result<Value, (StatusCode, Value)>;

struct PendingInteraction {
    job_id: u64,
    public: PublicInteraction,
    tx: mpsc::SyncSender<Value>,
}

struct InteractionBridge {
    seq: AtomicU64,
    current_job: AtomicU64,
    cancelling_job: AtomicU64,
    active: Mutex<Option<PendingInteraction>>,
    in_flight_jobs: Mutex<BTreeMap<u64, watch::Receiver<Option<JobOutcome>>>>,
    interaction_tx: watch::Sender<Option<(u64, PublicInteraction)>>,
    events_tx: broadcast::Sender<Value>,
}

impl InteractionBridge {
    fn new(
        interaction_tx: watch::Sender<Option<(u64, PublicInteraction)>>,
        events_tx: broadcast::Sender<Value>,
    ) -> Arc<Self> {
        Arc::new(Self {
            seq: AtomicU64::new(1),
            current_job: AtomicU64::new(0),
            cancelling_job: AtomicU64::new(0),
            active: Mutex::new(None),
            in_flight_jobs: Mutex::new(BTreeMap::new()),
            interaction_tx,
            events_tx,
        })
    }

    fn register_job(&self, job_id: u64, rx: watch::Receiver<Option<JobOutcome>>) {
        self.in_flight_jobs.lock().unwrap().insert(job_id, rx);
    }

    fn finish_job(&self, job_id: u64) {
        self.in_flight_jobs.lock().unwrap().remove(&job_id);
        let _ = self
            .cancelling_job
            .compare_exchange(job_id, 0, Ordering::SeqCst, Ordering::SeqCst);
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

    fn cancel_reply_for(kind: &str, request: &Value) -> Value {
        if kind == "alert" {
            let ntype = request["nType"].as_i64().unwrap_or(0);
            let button = match ntype {
                1 | 3 => 2,
                2 => 4,
                _ => 1,
            };
            json!({"button": button, "checked": false})
        } else {
            json!({"result": "cancel"})
        }
    }

    fn cancel_active(&self) {
        if let Some(pending) = self.active.lock().unwrap().take() {
            // Mark this job as cancelling so any cascading follow-up modal/alert
            // fired while unwinding auto-cancels instead of re-blocking the worker.
            self.cancelling_job.store(pending.job_id, Ordering::SeqCst);
            let _ = self.interaction_tx.send(None);
            let cancel_reply =
                Self::cancel_reply_for(&pending.public.kind, &pending.public.request);
            let _ = pending.tx.send(cancel_reply);
            let _ = self.events_tx.send(json!({"type": "interaction_cleared"}));
        }
    }

    fn respond(
        &self,
        id: &str,
        reply: Value,
    ) -> Result<(u64, watch::Receiver<Option<JobOutcome>>)> {
        let pending = {
            let mut active = self.active.lock().unwrap();
            let Some(cur) = active.as_ref() else {
                bail!("no active dialog or alert");
            };
            if cur.public.id != id {
                bail!("interaction id mismatch (dialog already changed)");
            }
            active.take().unwrap()
        };
        // Clear the interaction and broadcast `interaction_cleared` BEFORE checking
        // in-flight jobs or waking the worker so a rejected reply never strands a
        // prompt and WebSocket clients never see the next modal before this clear.
        let _ = self.interaction_tx.send(None);
        let _ = self.events_tx.send(json!({"type": "interaction_cleared"}));
        let done_rx = self
            .in_flight_jobs
            .lock()
            .unwrap()
            .get(&pending.job_id)
            .cloned()
            .ok_or_else(|| anyhow!("job {} is no longer in flight", pending.job_id))?;
        pending
            .tx
            .send(reply)
            .map_err(|_| anyhow!("dialog worker is no longer waiting"))?;
        Ok((pending.job_id, done_rx))
    }

    fn wait_for_user(&self, kind: &str, request: &Value) -> Result<Value> {
        let job_id = self.current_job.load(Ordering::SeqCst);
        if job_id != 0 && self.cancelling_job.load(Ordering::SeqCst) == job_id {
            return Ok(Self::cancel_reply_for(kind, request));
        }
        let id = format!("int-{}", self.seq.fetch_add(1, Ordering::SeqCst));
        let public = PublicInteraction {
            id,
            kind: kind.to_owned(),
            request: request.clone(),
        };
        let (tx, rx) = mpsc::sync_channel(1);
        {
            let mut active = self.active.lock().unwrap();
            *active = Some(PendingInteraction {
                job_id,
                public: public.clone(),
                tx,
            });
        }
        let _ = self.interaction_tx.send(Some((job_id, public.clone())));
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
        let dispatched = self
            .events_tx
            .send(json!({
                "type": "launch_url",
                "url": url,
                "new_frame": new_frame,
            }))
            .is_ok();
        Ok(dispatched)
    }
}

enum WorkerCommand {
    Open {
        job_id: u64,
        done: watch::Sender<Option<JobOutcome>>,
        rel_path: String,
        force: bool,
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
        done: watch::Sender<Option<JobOutcome>>,
        field: String,
        value: Value,
        mode: String,
        expected_sheet: Option<String>,
    },
    Activate {
        job_id: u64,
        done: watch::Sender<Option<JobOutcome>>,
        field: String,
        index: i64,
        shift: bool,
        modifier: bool,
        expected_sheet: Option<String>,
    },
    InvokeMenu {
        job_id: u64,
        done: watch::Sender<Option<JobOutcome>>,
        name: String,
        expected_sheet: Option<String>,
    },
    RunCommand {
        job_id: u64,
        done: watch::Sender<Option<JobOutcome>>,
        action: String,
        expected_sheet: Option<String>,
    },
    RunBookmark {
        job_id: u64,
        done: watch::Sender<Option<JobOutcome>>,
        path: String,
        expected_sheet: Option<String>,
    },
    SaveNow {
        job_id: u64,
        done: watch::Sender<Option<JobOutcome>>,
        force: bool,
        expected_sheet: Option<String>,
    },
    GitSync {
        job_id: u64,
        done: watch::Sender<Option<JobOutcome>>,
        message: String,
    },
    GitPull {
        job_id: u64,
        done: watch::Sender<Option<JobOutcome>>,
        force: bool,
    },
    CheckIdleAutoSync {
        job_id: u64,
        done: watch::Sender<Option<JobOutcome>>,
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
                WorkerCommand::CheckIdleAutoSync {
                    job_id,
                    done,
                    idle_secs,
                } => {
                    let should_sync = idle_secs > 0
                        && self.store.git_enabled()
                        && self.active.as_ref().is_some_and(|sh| {
                            sh.dirty_since_sync
                                && sh
                                    .last_edit_at
                                    .is_some_and(|t| t.elapsed() >= Duration::from_secs(idle_secs))
                        });
                    if should_sync {
                        self.run_job(job_id, done, |w| w.do_git_sync("Auto-sync MPMB session"));
                    } else {
                        let _ = done.send(Some(Ok(json!({"status": "skipped"}))));
                        self.bridge.finish_job(job_id);
                    }
                }
                WorkerCommand::Open {
                    job_id,
                    done,
                    rel_path,
                    force,
                } => {
                    self.run_job(job_id, done, |w| w.open_sheet(&rel_path, force));
                }
                WorkerCommand::Edit {
                    job_id,
                    done,
                    field,
                    value,
                    mode,
                    expected_sheet,
                } => {
                    self.run_job(job_id, done, |w| {
                        w.verify_expected_sheet(expected_sheet.as_deref())?;
                        w.edit_field(&field, &value, &mode)
                    });
                }
                WorkerCommand::Activate {
                    job_id,
                    done,
                    field,
                    index,
                    shift,
                    modifier,
                    expected_sheet,
                } => {
                    self.run_job(job_id, done, |w| {
                        w.verify_expected_sheet(expected_sheet.as_deref())?;
                        w.activate_field(&field, index, shift, modifier)
                    });
                }
                WorkerCommand::InvokeMenu {
                    job_id,
                    done,
                    name,
                    expected_sheet,
                } => {
                    self.run_job(job_id, done, |w| {
                        w.verify_expected_sheet(expected_sheet.as_deref())?;
                        w.invoke_menu(&name)
                    });
                }
                WorkerCommand::RunCommand {
                    job_id,
                    done,
                    action,
                    expected_sheet,
                } => {
                    self.run_job(job_id, done, |w| {
                        w.verify_expected_sheet(expected_sheet.as_deref())?;
                        w.run_command(&action)
                    });
                }
                WorkerCommand::RunBookmark {
                    job_id,
                    done,
                    path,
                    expected_sheet,
                } => {
                    self.run_job(job_id, done, |w| {
                        w.verify_expected_sheet(expected_sheet.as_deref())?;
                        w.run_bookmark(&path)
                    });
                }
                WorkerCommand::SaveNow {
                    job_id,
                    done,
                    force,
                    expected_sheet,
                } => {
                    self.run_job(job_id, done, |w| {
                        w.verify_expected_sheet(expected_sheet.as_deref())?;
                        w.save_active(force)
                    });
                }
                WorkerCommand::GitSync {
                    job_id,
                    done,
                    message,
                } => {
                    self.run_job(job_id, done, |w| w.do_git_sync(&message));
                }
                WorkerCommand::GitPull {
                    job_id,
                    done,
                    force,
                } => {
                    self.run_job(job_id, done, |w| w.do_git_pull(force));
                }
            }
        }
    }

    fn run_job<F>(&mut self, job_id: u64, done: watch::Sender<Option<JobOutcome>>, f: F)
    where
        F: FnOnce(&mut Self) -> Result<Value>,
    {
        self.bridge.set_current_job(job_id);
        let outcome = f(self);
        let job_result: JobOutcome = match outcome {
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
                if val.get("status").and_then(Value::as_str) == Some("conflict") {
                    Err((StatusCode::CONFLICT, val))
                } else {
                    Ok(val)
                }
            }
            Err(err) => {
                let msg = format!("{err:#}");
                let _ = self.bridge.events_tx.send(json!({
                    "type": "error",
                    "message": msg,
                }));
                let status = if msg.contains("conflict") || msg.contains("changed externally") {
                    StatusCode::CONFLICT
                } else {
                    StatusCode::BAD_REQUEST
                };
                Err((status, json!({"error": msg})))
            }
        };
        let _ = self.bridge.interaction_tx.send(None);
        let _ = done.send(Some(job_result));
        self.bridge.finish_job(job_id);
    }

    fn verify_expected_sheet(&self, expected: Option<&str>) -> Result<()> {
        let Some(exp) = expected.map(str::trim).filter(|s| !s.is_empty()) else {
            return Ok(());
        };
        let active_path = self
            .active
            .as_ref()
            .map(|s| s.rel_path.as_str())
            .unwrap_or("<none>");
        if active_path != exp {
            bail!(
                "conflict: active sheet changed (expected '{exp}', active is '{active_path}'); refresh before retrying"
            );
        }
        Ok(())
    }

    fn open_sheet(&mut self, rel_path: &str, force: bool) -> Result<Value> {
        if !force {
            if let Some(cur) = &self.active {
                if cur.dirty_since_save {
                    bail!(
                        "conflict: active sheet '{}' has unsaved edits; save first or pass force=true to discard",
                        cur.rel_path
                    );
                }
            }
        }
        // Pull latest changes opportunistically if Git is enabled and clean.
        if self.store.git_enabled() {
            let _ = self.store.git_pull();
        }
        let (norm, abs, bytes, sha) = self.store.read_sheet_bytes(rel_path)?;
        // Parse the exact bytes hashed above so disk_sha256 always matches the loaded PDF.
        let pdf = Arc::new(Pdf::open_bytes(abs, &bytes)?);
        let rt = Runtime::new_with_capabilities(
            &pdf,
            vec![],
            vec![],
            true,
            None,
            None,
            Some(self.bridge.clone()),
            HostCapabilities::server_restricted(),
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
            renderer.page_size.set((0.0, 0.0));
            let rendered_ok = renderer.render(&projected, page, 320).is_ok();
            let sz = renderer.page_size.get();
            if rendered_ok && sz.0 > 0.0 && sz.1 > 0.0 {
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
        let mut save_conflict: Option<SaveResult> = None;
        if self.autosave && self.active.as_ref().is_some_and(|s| s.dirty_since_save) {
            let res = self.persist_active(false)?;
            if matches!(res, SaveResult::Conflict { .. }) {
                save_conflict = Some(res);
            }
        }
        let state = self.build_state_payload()?;
        if let Some(conflict) = save_conflict {
            return Ok(json!({
                "status": "conflict",
                "error": "Sheet changed externally on disk; pull or force-save to resolve",
                "save": conflict,
                "state": state,
            }));
        }
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
        let (status, message) = match &res {
            SaveResult::Saved { .. } => ("ok", "Saved PDF & state sidecar to disk"),
            SaveResult::Conflict { .. } => (
                "conflict",
                "File changed externally on disk; pass force=true or pull before overwriting",
            ),
        };
        Ok(json!({
            "status": status,
            "error": if status == "conflict" { Value::String(message.into()) } else { Value::Null },
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

    fn do_git_pull(&mut self, force: bool) -> Result<Value> {
        if !force {
            if let Some(cur) = &self.active {
                if cur.dirty_since_save {
                    bail!(
                        "conflict: active sheet '{}' has unsaved edits; save before pulling or pass force=true to discard",
                        cur.rel_path
                    );
                }
            }
        }
        let pull = self.store.git_pull()?;
        if pull.updated {
            if let Some(rel) = self.active.as_ref().map(|s| s.rel_path.clone()) {
                if self.store.read_sheet_bytes(&rel).is_ok() {
                    let _ = self.open_sheet(&rel, true)?;
                } else {
                    self.active = None;
                    self.last_save_conflict = None;
                    let git = self.store.git_status()?;
                    let state = self.build_state_payload()?;
                    return Ok(json!({
                        "status": "conflict",
                        "error": format!("Active sheet '{rel}' was removed by upstream Git pull"),
                        "pull": pull,
                        "git": git,
                        "state": state,
                    }));
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
    interaction_rx: watch::Receiver<Option<(u64, PublicInteraction)>>,
    auth_token: Option<String>,
    pdfium_available: bool,
}

impl AppState {
    fn start(config: &ServeConfig) -> Result<Self> {
        let store = Arc::new(SheetStore::open(config.store.clone())?);
        let (interaction_tx, interaction_rx) = watch::channel(None);
        let (events_tx, _) = broadcast::channel(64);
        let bridge = InteractionBridge::new(interaction_tx, events_tx);
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
            interaction_rx,
            auth_token: config.auth_token.clone().filter(|t| !t.is_empty()),
            pdfium_available,
        };

        if let Some(default_sheet) = &config.default_sheet {
            let job_id = state.job_seq.fetch_add(1, Ordering::SeqCst);
            let (done_tx, done_rx) = watch::channel(None);
            state.bridge.register_job(job_id, done_rx);
            let _ = state.cmd_tx.send(WorkerCommand::Open {
                job_id,
                done: done_tx,
                rel_path: default_sheet.clone(),
                force: true,
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

    fn interaction_conflict_response(&self) -> Option<Response> {
        self.bridge.active_public().map(|active| {
            (
                StatusCode::CONFLICT,
                Json(json!({
                    "status": "interaction_required",
                    "error": "A dialog or alert is currently waiting for a response",
                    "interaction": active,
                })),
            )
                .into_response()
        })
    }

    async fn dispatch_job(
        &self,
        make_cmd: impl FnOnce(u64, watch::Sender<Option<JobOutcome>>) -> WorkerCommand,
    ) -> Response {
        if let Some(conflict) = self.interaction_conflict_response() {
            return conflict;
        }
        let job_id = self.job_seq.fetch_add(1, Ordering::SeqCst);
        let (done_tx, done_rx) = watch::channel(None);
        self.bridge.register_job(job_id, done_rx.clone());
        let mut int_rx = self.interaction_rx.clone();
        if self.cmd_tx.send(make_cmd(job_id, done_tx)).is_err() {
            self.bridge.finish_job(job_id);
            return err_response(StatusCode::INTERNAL_SERVER_ERROR, "sheet worker stopped");
        }
        self.await_job_or_interaction(done_rx, &mut int_rx, job_id, None)
            .await
    }

    async fn await_job_or_interaction(
        &self,
        mut done_rx: watch::Receiver<Option<JobOutcome>>,
        int_rx: &mut watch::Receiver<Option<(u64, PublicInteraction)>>,
        target_job_id: u64,
        previous_interaction_id: Option<&str>,
    ) -> Response {
        loop {
            if let Some(outcome) = done_rx.borrow().clone() {
                return match outcome {
                    Ok(val) => (StatusCode::OK, Json(val)).into_response(),
                    Err((status, body)) => (status, Json(body)).into_response(),
                };
            }
            if let Some((jid, interaction)) = int_rx.borrow().clone() {
                if jid == target_job_id && previous_interaction_id != Some(interaction.id.as_str())
                {
                    return (
                        StatusCode::ACCEPTED,
                        Json(json!({
                            "status": "interaction_required",
                            "interaction": interaction,
                        })),
                    )
                        .into_response();
                } else if jid != target_job_id {
                    return (
                        StatusCode::CONFLICT,
                        Json(json!({
                            "status": "interaction_required",
                            "error": "Another operation opened a dialog or alert waiting for a response",
                            "interaction": interaction,
                        })),
                    )
                        .into_response();
                }
            }
            tokio::select! {
                biased;
                res = done_rx.changed() => {
                    if res.is_err() {
                        return err_response(
                            StatusCode::INTERNAL_SERVER_ERROR,
                            "sheet worker dropped job",
                        );
                    }
                }
                res = int_rx.changed() => {
                    if res.is_err() {
                        return err_response(
                            StatusCode::INTERNAL_SERVER_ERROR,
                            "sheet worker terminated",
                        );
                    }
                }
            }
        }
    }

    async fn await_sync_read<T: Send + 'static>(
        &self,
        rx: mpsc::Receiver<Result<T>>,
        timeout_msg: &'static str,
    ) -> std::result::Result<Result<T>, Box<Response>> {
        let mut int_rx = self.interaction_rx.clone();
        if let Some((_, interaction)) = int_rx.borrow().clone() {
            return Err(Box::new(
                (
                    StatusCode::CONFLICT,
                    Json(json!({
                        "status": "interaction_required",
                        "error": "A dialog or alert is currently waiting for a response",
                        "interaction": interaction,
                    })),
                )
                    .into_response(),
            ));
        }
        let mut recv_fut = Box::pin(tokio::task::spawn_blocking(move || {
            rx.recv_timeout(Duration::from_secs(60))
        }));
        loop {
            tokio::select! {
                biased;
                res = &mut recv_fut => {
                    return match res {
                        Ok(Ok(inner)) => Ok(inner),
                        _ => Err(Box::new(err_response(StatusCode::GATEWAY_TIMEOUT, timeout_msg))),
                    };
                }
                changed = int_rx.changed() => {
                    if changed.is_err() {
                        return Err(Box::new(err_response(StatusCode::INTERNAL_SERVER_ERROR, "sheet worker terminated")));
                    }
                    if let Some((_, interaction)) = int_rx.borrow().clone() {
                        return Err(Box::new((
                            StatusCode::CONFLICT,
                            Json(json!({
                                "status": "interaction_required",
                                "error": "A dialog or alert is currently waiting for a response",
                                "interaction": interaction,
                            })),
                        )
                            .into_response()));
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
    #[serde(default)]
    force: bool,
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
    #[serde(default)]
    sheet: Option<String>,
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
    #[serde(default)]
    sheet: Option<String>,
}

#[derive(Deserialize)]
struct MenuRequest {
    name: String,
    #[serde(default)]
    sheet: Option<String>,
}

#[derive(Deserialize)]
struct CommandRequest {
    action: String,
    #[serde(default)]
    sheet: Option<String>,
}

#[derive(Deserialize)]
struct BookmarkRequest {
    path: String,
    #[serde(default)]
    sheet: Option<String>,
}

#[derive(Deserialize, Default)]
struct SaveRequest {
    #[serde(default)]
    force: bool,
    #[serde(default)]
    sheet: Option<String>,
}

#[derive(Deserialize, Default)]
struct PullRequest {
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
    let store = Arc::clone(&state.store);
    let git: Option<GitStatus> = tokio::task::spawn_blocking(move || store.git_status().ok())
        .await
        .ok()
        .flatten();
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
    let mut send_task = tokio::spawn(async move {
        loop {
            match rx.recv().await {
                Ok(ev) => {
                    if sender
                        .send(Message::Text(ev.to_string().into()))
                        .await
                        .is_err()
                    {
                        break;
                    }
                }
                Err(broadcast::error::RecvError::Lagged(skipped)) => {
                    if sender
                        .send(Message::Text(
                            json!({"type": "resync_required", "skipped": skipped})
                                .to_string()
                                .into(),
                        ))
                        .await
                        .is_err()
                    {
                        break;
                    }
                }
                Err(broadcast::error::RecvError::Closed) => break,
            }
        }
    });
    let mut recv_task = tokio::spawn(async move {
        while let Some(Ok(msg)) = receiver.next().await {
            if matches!(msg, Message::Close(_)) {
                break;
            }
        }
    });
    tokio::select! {
        _ = &mut send_task => { recv_task.abort(); }
        _ = &mut recv_task => { send_task.abort(); }
    }
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
        Ok(Ok(v)) => ([(header::VARY, "Authorization")], Json(v)).into_response(),
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
        Ok(Err(e)) => {
            let msg = format!("{e:#}");
            let status = if msg.contains("already exists") {
                StatusCode::CONFLICT
            } else {
                StatusCode::BAD_REQUEST
            };
            err_response(status, msg)
        }
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
    // Switching sheets cancels any lingering modal (including cascading dialogs) on the previous sheet.
    state.bridge.cancel_active();
    state
        .dispatch_job(|job_id, done| WorkerCommand::Open {
            job_id,
            done,
            rel_path: req.path,
            force: req.force,
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
        let store = Arc::clone(&state.store);
        let git = tokio::task::spawn_blocking(move || store.git_status().ok())
            .await
            .ok()
            .flatten();
        return (
            [(header::VARY, "Authorization")],
            Json(json!({
                "open": true,
                "busy": true,
                "activeInteraction": inter,
                "git": git,
            })),
        )
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
    match state.await_sync_read(rx, "timed out reading session").await {
        Ok(Ok(v)) => ([(header::VARY, "Authorization")], Json(v)).into_response(),
        Ok(Err(e)) => err_response(StatusCode::INTERNAL_SERVER_ERROR, format!("{e:#}")),
        Err(resp) => {
            if let Some(inter) = state.bridge.active_public() {
                let store = Arc::clone(&state.store);
                let git = tokio::task::spawn_blocking(move || store.git_status().ok())
                    .await
                    .ok()
                    .flatten();
                return (
                    [(header::VARY, "Authorization")],
                    Json(json!({
                        "open": true,
                        "busy": true,
                        "activeInteraction": inter,
                        "git": git,
                    })),
                )
                    .into_response();
            }
            *resp
        }
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
    if let Some(conflict) = state.interaction_conflict_response() {
        return conflict;
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
    match state
        .await_sync_read(rx, "timed out inspecting field")
        .await
    {
        Ok(Ok(v)) => Json(v).into_response(),
        Ok(Err(e)) => err_response(StatusCode::NOT_FOUND, format!("{e:#}")),
        Err(resp) => *resp,
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
        .dispatch_job(|job_id, done| WorkerCommand::Edit {
            job_id,
            done,
            field: req.field,
            value: req.value,
            mode: req.mode,
            expected_sheet: req.sheet,
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
        .dispatch_job(|job_id, done| WorkerCommand::Activate {
            job_id,
            done,
            field: req.field,
            index: req.index,
            shift: req.shift,
            modifier: req.modifier,
            expected_sheet: req.sheet,
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
        .dispatch_job(|job_id, done| WorkerCommand::InvokeMenu {
            job_id,
            done,
            name: req.name,
            expected_sheet: req.sheet,
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
        .dispatch_job(|job_id, done| WorkerCommand::RunCommand {
            job_id,
            done,
            action: req.action,
            expected_sheet: req.sheet,
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
        .dispatch_job(|job_id, done| WorkerCommand::RunBookmark {
            job_id,
            done,
            path: req.path,
            expected_sheet: req.sheet,
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
        .dispatch_job(|job_id, done| WorkerCommand::SaveNow {
            job_id,
            done,
            force: req.force,
            expected_sheet: req.sheet,
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
    if let Some(conflict) = state.interaction_conflict_response() {
        return conflict;
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
    match state.await_sync_read(rx, "timed out rendering page").await {
        Ok(Ok(png)) => (
            [
                (header::CONTENT_TYPE, "image/png"),
                (header::CACHE_CONTROL, "private, max-age=30"),
                (header::VARY, "Authorization"),
            ],
            png,
        )
            .into_response(),
        Ok(Err(e)) => {
            let msg = format!("{e:#}");
            let status = if msg.contains("PDFium") {
                StatusCode::SERVICE_UNAVAILABLE
            } else {
                StatusCode::BAD_REQUEST
            };
            err_response(status, msg)
        }
        Err(resp) => *resp,
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
    if let Some(conflict) = state.interaction_conflict_response() {
        return conflict;
    }
    let (tx, rx) = mpsc::sync_channel(1);
    if state
        .cmd_tx
        .send(WorkerCommand::GetPageWidgets { page, reply: tx })
        .is_err()
    {
        return err_response(StatusCode::INTERNAL_SERVER_ERROR, "sheet worker stopped");
    }
    match state.await_sync_read(rx, "timed out reading widgets").await {
        Ok(Ok(v)) => ([(header::VARY, "Authorization")], Json(v)).into_response(),
        Ok(Err(e)) => err_response(StatusCode::BAD_REQUEST, format!("{e:#}")),
        Err(resp) => *resp,
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
    let mut int_rx = state.interaction_rx.clone();
    let (job_id, done_rx) = match state.bridge.respond(&id, reply) {
        Ok(pair) => pair,
        Err(e) => return err_response(StatusCode::CONFLICT, format!("{e:#}")),
    };
    state
        .await_job_or_interaction(done_rx, &mut int_rx, job_id, Some(&id))
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
    let store = Arc::clone(&state.store);
    match tokio::task::spawn_blocking(move || store.git_status()).await {
        Ok(Ok(git)) => Json(git).into_response(),
        Ok(Err(e)) => err_response(StatusCode::INTERNAL_SERVER_ERROR, format!("{e:#}")),
        Err(e) => err_response(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()),
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
        .dispatch_job(|job_id, done| WorkerCommand::GitSync {
            job_id,
            done,
            message: req.message,
        })
        .await
}

async fn handle_git_pull(
    State(state): State<AppState>,
    headers: HeaderMap,
    req: Option<Json<PullRequest>>,
) -> Response {
    if !state.check_auth(&headers, None) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    let force = req.map(|Json(r)| r.force).unwrap_or(false);
    state
        .dispatch_job(|job_id, done| WorkerCommand::GitPull {
            job_id,
            done,
            force,
        })
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
        let bridge = Arc::clone(&state.bridge);
        let job_seq = Arc::clone(&state.job_seq);
        let idle = config.git_auto_sync_secs;
        tokio::spawn(async move {
            let mut ticker = tokio::time::interval(Duration::from_secs(15));
            loop {
                ticker.tick().await;
                if bridge.active_public().is_some() {
                    continue;
                }
                let job_id = job_seq.fetch_add(1, Ordering::SeqCst);
                let (done_tx, done_rx) = watch::channel(None);
                bridge.register_job(job_id, done_rx);
                if tx
                    .send(WorkerCommand::CheckIdleAutoSync {
                        job_id,
                        done: done_tx,
                        idle_secs: idle,
                    })
                    .is_err()
                {
                    bridge.finish_job(job_id);
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
        let mut git_show = Command::new("git");
        for key in [
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_INDEX_FILE",
            "GIT_COMMON_DIR",
            "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        ] {
            git_show.env_remove(key);
        }
        let show_out = git_show
            .current_dir(&bare)
            .args(["show", "main:aelar.pdf.state.json"])
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

    fn make_cascading_dialog_pdf(path: &std::path::Path) {
        let mut doc = lopdf::Document::with_version("1.7");
        let pages_id = doc.new_object_id();
        let page_id = doc.new_object_id();
        let f_name = doc.add_object(dictionary! {
            "Type" => "Annot",
            "Subtype" => "Widget",
            "FT" => "Tx",
            "T" => Object::String(b"PC Name".to_vec(), StringFormat::Literal),
            "V" => Object::String(b"Cascade Hero".to_vec(), StringFormat::Literal),
            "Rect" => vec![40.into(), 700.into(), 240.into(), 724.into()],
            "P" => page_id,
        });
        // Clicking CascadeButton opens Dialog 1; cancelling Dialog 1 triggers a follow-up alert!
        let btn_action = doc.add_object(dictionary! {
            "S" => "JavaScript",
            "JS" => Object::String(
                b"var r=app.execDialog({description:{name:'Step 1',elements:[{type:'ok_cancel'}]}});if(r==='cancel'){app.alert({cTitle:'Confirm Cancel',cMsg:'Really cancel?',nType:2});}".to_vec(),
                StringFormat::Literal,
            ),
        });
        let f_btn = doc.add_object(dictionary! {
            "Type" => "Annot",
            "Subtype" => "Widget",
            "FT" => "Btn",
            "Ff" => 65536,
            "T" => Object::String(b"CascadeButton".to_vec(), StringFormat::Literal),
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
                "Annots" => vec![f_name.into(), f_btn.into()],
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
            "Fields" => vec![f_name.into(), f_btn.into()],
        });
        let catalog_id = doc.add_object(dictionary! {
            "Type" => "Catalog",
            "Pages" => pages_id,
            "AcroForm" => form_id,
        });
        doc.trailer.set("Root", catalog_id);
        doc.save(path).unwrap();
    }

    fn setup_test_app(label: &str, with_git: bool) -> (PathBuf, Option<PathBuf>, Router) {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let base =
            std::env::temp_dir().join(format!("mpmb-serve-{label}-{}-{nanos}", std::process::id()));
        let data_dir = base.join("sheets");
        let git_cfg = if with_git {
            let bare = base.join("remote.git");
            std::fs::create_dir_all(&bare).unwrap();
            assert!(Command::new("git")
                .args(["init", "--bare", "-b", "main"])
                .arg(&bare)
                .status()
                .unwrap()
                .success());
            Some((
                bare.clone(),
                GitConfig::new(bare.to_string_lossy().into_owned()),
            ))
        } else {
            None
        };
        let cfg = ServeConfig {
            bind: "127.0.0.1:0".parse().unwrap(),
            store: StoreConfig {
                root: data_dir,
                git: git_cfg.as_ref().map(|(_, g)| g.clone()),
            },
            default_sheet: None,
            auth_token: None,
            autosave: true,
            git_auto_sync_secs: 0,
        };
        let state = AppState::start(&cfg).unwrap();
        (base, git_cfg.map(|(b, _)| b), build_router(state))
    }

    async fn post_json(app: &Router, uri: &str, body: Value) -> (StatusCode, Value) {
        let res = tokio::time::timeout(
            Duration::from_secs(15),
            app.clone().oneshot(
                Request::builder()
                    .method("POST")
                    .uri(uri)
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(body.to_string()))
                    .unwrap(),
            ),
        )
        .await
        .expect("HTTP POST timed out")
        .unwrap();
        let st = res.status();
        (st, json_body(res).await)
    }

    async fn get_json(app: &Router, uri: &str) -> (StatusCode, Value) {
        let res = tokio::time::timeout(
            Duration::from_secs(15),
            app.clone()
                .oneshot(Request::builder().uri(uri).body(Body::empty()).unwrap()),
        )
        .await
        .expect("HTTP GET timed out")
        .unwrap();
        let st = res.status();
        (st, json_body(res).await)
    }

    #[tokio::test]
    async fn concurrent_edits_never_mix_results_or_drop_updates() {
        let (base, _, app) = setup_test_app("concurrent-edits", false);
        let seed = base.join("seed.pdf");
        make_interactive_test_pdf(&seed);
        let bytes = std::fs::read(&seed).unwrap();

        let up = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/sheets/upload?name=hero.pdf")
                    .body(Body::from(bytes))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(up.status(), StatusCode::CREATED);
        assert_eq!(
            post_json(&app, "/api/session/open", json!({"path": "hero.pdf"}))
                .await
                .0,
            StatusCode::OK
        );

        // Fire 16 concurrent edits: even tasks edit valid fields (expect 200),
        // odd tasks target a non-existent field (expect 400).
        // Per-job channels must ensure ZERO cross-contamination of results!
        let mut tasks = Vec::new();
        for i in 0..16usize {
            let app_c = app.clone();
            tasks.push(tokio::spawn(async move {
                if i % 2 == 0 {
                    let score = 10 + (i % 10);
                    let (st, body) = post_json(
                        &app_c,
                        "/api/session/edit",
                        json!({"field": "Str", "value": score.to_string(), "mode": "user"}),
                    )
                    .await;
                    (i, true, st, body)
                } else {
                    let (st, body) = post_json(
                        &app_c,
                        "/api/session/edit",
                        json!({"field": format!("MissingField_{i}"), "value": "x", "mode": "user"}),
                    )
                    .await;
                    (i, false, st, body)
                }
            }));
        }

        for task in tasks {
            let (i, expect_ok, st, body) = task.await.unwrap();
            if expect_ok {
                assert_eq!(
                    st,
                    StatusCode::OK,
                    "valid concurrent edit {i} got wrong status: {body}"
                );
                assert_eq!(body["status"], "ok");
            } else {
                assert_eq!(
                    st,
                    StatusCode::BAD_REQUEST,
                    "invalid concurrent edit {i} got wrong status (cross-contaminated!): {body}"
                );
            }
        }

        // Verify saved PDF on disk is still valid and reopenable.
        let reopen = post_json(&app, "/api/session/open", json!({"path": "hero.pdf"})).await;
        assert_eq!(reopen.0, StatusCode::OK);
        let _ = std::fs::remove_dir_all(&base);
    }

    #[tokio::test]
    async fn concurrent_double_reply_to_modal_allows_exactly_one_winner() {
        let (base, _, app) = setup_test_app("double-reply", false);
        let seed = base.join("seed.pdf");
        make_interactive_test_pdf(&seed);
        let bytes = std::fs::read(&seed).unwrap();
        let _ = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/sheets/upload?name=hero.pdf")
                    .body(Body::from(bytes))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(
            post_json(&app, "/api/session/open", json!({"path": "hero.pdf"}))
                .await
                .0,
            StatusCode::OK
        );

        // Open RenameButton modal -> 202 Accepted
        let (st, modal) = post_json(
            &app,
            "/api/session/activate",
            json!({"field": "RenameButton", "index": 0}),
        )
        .await;
        assert_eq!(st, StatusCode::ACCEPTED);
        let int_id = modal["interaction"]["id"].as_str().unwrap().to_owned();

        // Fire 6 simultaneous replies to the exact same interaction id!
        let barrier = Arc::new(tokio::sync::Barrier::new(6));
        let mut tasks = Vec::new();
        for idx in 0..6usize {
            let app_c = app.clone();
            let id_c = int_id.clone();
            let bar = Arc::clone(&barrier);
            tasks.push(tokio::spawn(async move {
                bar.wait().await;
                post_json(
                    &app_c,
                    &format!("/api/session/interaction/{id_c}"),
                    json!({"result": "ok", "values": {"hero": format!("Winner-{idx}")}}),
                )
                .await
            }));
        }

        let mut ok_count = 0;
        let mut conflict_count = 0;
        let mut winner_name = String::new();
        for task in tasks {
            let (st, body) = task.await.unwrap();
            match st {
                StatusCode::OK => {
                    ok_count += 1;
                    winner_name = body["state"]["character"]["name"]
                        .as_str()
                        .unwrap()
                        .to_owned();
                }
                StatusCode::CONFLICT => conflict_count += 1,
                other => panic!("unexpected status {other}: {body}"),
            }
        }
        assert_eq!(ok_count, 1, "exactly one reply must win the modal");
        assert_eq!(conflict_count, 5, "all duplicate replies must get 409");
        assert!(winner_name.starts_with("Winner-"));

        let (st, state) = get_json(&app, "/api/session/state").await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(state["character"]["name"], winner_name);
        let _ = std::fs::remove_dir_all(&base);
    }

    #[tokio::test]
    async fn endpoints_do_not_hang_while_modal_is_open() {
        let (base, _, app) = setup_test_app("modal-nonblocking", false);
        let seed = base.join("seed.pdf");
        make_interactive_test_pdf(&seed);
        let bytes = std::fs::read(&seed).unwrap();
        let _ = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/sheets/upload?name=hero.pdf")
                    .body(Body::from(bytes))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(
            post_json(&app, "/api/session/open", json!({"path": "hero.pdf"}))
                .await
                .0,
            StatusCode::OK
        );

        let (st, modal) = post_json(
            &app,
            "/api/session/activate",
            json!({"field": "RenameButton", "index": 0}),
        )
        .await;
        assert_eq!(st, StatusCode::ACCEPTED);
        let int_id = modal["interaction"]["id"].as_str().unwrap().to_owned();

        // None of these calls may hang while QuickJS is blocked on the modal!
        let (edit_st, edit_body) = post_json(
            &app,
            "/api/session/edit",
            json!({"field": "Str", "value": "16", "mode": "user"}),
        )
        .await;
        assert_eq!(edit_st, StatusCode::CONFLICT);
        assert_eq!(edit_body["interaction"]["id"], int_id);

        assert_eq!(
            get_json(&app, "/api/session/field?name=Str").await.0,
            StatusCode::CONFLICT
        );
        assert_eq!(
            get_json(&app, "/api/session/page/0/widgets").await.0,
            StatusCode::CONFLICT
        );
        assert_eq!(
            get_json(&app, "/api/session/page/0/image?w=640").await.0,
            StatusCode::CONFLICT
        );

        let (state_st, state_body) = get_json(&app, "/api/session/state").await;
        assert_eq!(state_st, StatusCode::OK);
        assert_eq!(state_body["busy"], true);
        assert_eq!(state_body["activeInteraction"]["id"], int_id);

        // Cancel the modal and verify normal operations immediately resume.
        assert_eq!(
            post_json(
                &app,
                &format!("/api/session/interaction/{int_id}"),
                json!({"result": "cancel"}),
            )
            .await
            .0,
            StatusCode::OK
        );
        assert_eq!(
            get_json(&app, "/api/session/field?name=Str").await.0,
            StatusCode::OK
        );
        let _ = std::fs::remove_dir_all(&base);
    }

    #[tokio::test]
    async fn switching_sheets_mid_cascading_dialog_cancels_cleanly_without_deadlock() {
        let (base, _, app) = setup_test_app("cascade-cancel", false);
        let cascade_pdf = base.join("cascade.pdf");
        let second_pdf = base.join("second.pdf");
        make_cascading_dialog_pdf(&cascade_pdf);
        make_interactive_test_pdf(&second_pdf);

        for (name, path) in [("cascade.pdf", &cascade_pdf), ("second.pdf", &second_pdf)] {
            let up = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method("POST")
                        .uri(format!("/api/sheets/upload?name={name}"))
                        .body(Body::from(std::fs::read(path).unwrap()))
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(up.status(), StatusCode::CREATED);
        }

        assert_eq!(
            post_json(&app, "/api/session/open", json!({"path": "cascade.pdf"}))
                .await
                .0,
            StatusCode::OK
        );
        let (st, modal) = post_json(
            &app,
            "/api/session/activate",
            json!({"field": "CascadeButton", "index": 0}),
        )
        .await;
        assert_eq!(st, StatusCode::ACCEPTED);
        assert_eq!(
            modal["interaction"]["request"]["description"]["name"],
            "Step 1"
        );

        // Opening second.pdf while Step 1 is open must auto-cancel BOTH Step 1 AND
        // the cascading follow-up 'Confirm Cancel' alert without deadlocking!
        let (open2_st, open2_body) =
            post_json(&app, "/api/session/open", json!({"path": "second.pdf"})).await;
        assert_eq!(
            open2_st,
            StatusCode::OK,
            "sheet switch failed: {open2_body}"
        );
        assert_eq!(open2_body["state"]["character"]["name"], "Initial Hero");
        assert!(open2_body["state"]["activeInteraction"].is_null());

        let _ = std::fs::remove_dir_all(&base);
    }

    #[tokio::test]
    async fn external_file_conflict_surfaces_409_protects_disk_and_resolves_with_force() {
        let (base, _, app) = setup_test_app("external-conflict", true);
        let seed = base.join("seed.pdf");
        make_interactive_test_pdf(&seed);
        let seed_bytes = std::fs::read(&seed).unwrap();

        let _ = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/sheets/upload?name=hero.pdf")
                    .body(Body::from(seed_bytes.clone()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(
            post_json(&app, "/api/session/open", json!({"path": "hero.pdf"}))
                .await
                .0,
            StatusCode::OK
        );

        // Simulate external modification on disk (e.g. Syncthing/desktop overwrite or upload?overwrite=true).
        let external_bytes = [seed_bytes.as_slice(), b"\n%external-desktop-edit\n"].concat();
        let ov = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/sheets/upload?name=hero.pdf&overwrite=true")
                    .body(Body::from(external_bytes.clone()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(ov.status(), StatusCode::CREATED);

        // Editing in memory now hits the external-modification SHA-256 guard -> 409 Conflict!
        let (edit_st, edit_body) = post_json(
            &app,
            "/api/session/edit",
            json!({"field": "PC Name", "value": "Phone Edit", "mode": "user"}),
        )
        .await;
        assert_eq!(edit_st, StatusCode::CONFLICT, "expected 409: {edit_body}");
        assert_eq!(edit_body["save"]["status"], "conflict");
        // Verify the external file on disk was NOT overwritten!
        assert_eq!(
            std::fs::read(base.join("sheets/hero.pdf")).unwrap(),
            external_bytes
        );

        // Git sync must ALSO refuse while conflicted -> 409 Conflict!
        let (sync_st, _) =
            post_json(&app, "/api/git/sync", json!({"message": "should fail"})).await;
        assert_eq!(sync_st, StatusCode::CONFLICT);

        // Explicit force save overwrites cleanly and allows Git sync to succeed.
        let (force_st, force_body) =
            post_json(&app, "/api/session/save", json!({"force": true})).await;
        assert_eq!(force_st, StatusCode::OK, "force save failed: {force_body}");
        assert_eq!(force_body["save"]["status"], "saved");

        let (sync_ok_st, sync_ok_body) =
            post_json(&app, "/api/git/sync", json!({"message": "resolved"})).await;
        assert_eq!(
            sync_ok_st,
            StatusCode::OK,
            "sync after resolve failed: {sync_ok_body}"
        );
        assert_eq!(sync_ok_body["sync"]["status"], "synced");

        let _ = std::fs::remove_dir_all(&base);
    }

    #[tokio::test]
    async fn corrupted_pdf_and_invalid_requests_never_break_active_session() {
        let (base, _, app) = setup_test_app("bad-inputs", false);
        let seed = base.join("seed.pdf");
        make_interactive_test_pdf(&seed);

        let _ = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/sheets/upload?name=good.pdf")
                    .body(Body::from(std::fs::read(&seed).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();
        let _ = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/sheets/upload?name=corrupt.pdf")
                    .body(Body::from(b"%PDF-1.7\nthis-is-corrupt-garbage".to_vec()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(
            post_json(&app, "/api/session/open", json!({"path": "good.pdf"}))
                .await
                .0,
            StatusCode::OK
        );

        // Opening corrupted PDF returns 400 without crashing worker or losing good.pdf!
        assert_eq!(
            post_json(&app, "/api/session/open", json!({"path": "corrupt.pdf"}))
                .await
                .0,
            StatusCode::BAD_REQUEST
        );
        assert_eq!(
            post_json(&app, "/api/session/open", json!({"path": "missing.pdf"}))
                .await
                .0,
            StatusCode::BAD_REQUEST
        );
        assert_eq!(
            post_json(&app, "/api/session/command", json!({"action": "eval_evil"}))
                .await
                .0,
            StatusCode::BAD_REQUEST
        );
        assert_eq!(
            post_json(
                &app,
                "/api/session/bookmark",
                json!({"path": "bookmarkRoot.children[0];process.exit(1)"}),
            )
            .await
            .0,
            StatusCode::BAD_REQUEST
        );
        assert_eq!(
            post_json(
                &app,
                "/api/session/interaction/int-99999",
                json!({"result": "ok"}),
            )
            .await
            .0,
            StatusCode::CONFLICT
        );
        assert_eq!(
            get_json(&app, "/api/sheets/..%2F..%2Fetc%2Fpasswd.pdf/download")
                .await
                .0,
            StatusCode::NOT_FOUND
        );

        // Good session is still completely healthy and editable!
        let (st, edited) = post_json(
            &app,
            "/api/session/edit",
            json!({"field": "PC Name", "value": "Still Alive", "mode": "user"}),
        )
        .await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(edited["state"]["character"]["name"], "Still Alive");

        let _ = std::fs::remove_dir_all(&base);
    }

    #[tokio::test]
    async fn websocket_broadcasts_live_state_and_interaction_lifecycle() {
        let (base, _, app) = setup_test_app("ws-live", false);
        let seed = base.join("seed.pdf");
        make_interactive_test_pdf(&seed);

        let _ = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/sheets/upload?name=hero.pdf")
                    .body(Body::from(std::fs::read(&seed).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(
            post_json(&app, "/api/session/open", json!({"path": "hero.pdf"}))
                .await
                .0,
            StatusCode::OK
        );

        // Bind a real ephemeral TCP server so we exercise the real Axum WebSocket upgrade path.
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let app_srv = app.clone();
        let server_task = tokio::spawn(async move {
            let _ = axum::serve(listener, app_srv).await;
        });

        use tokio::io::{AsyncReadExt, AsyncWriteExt};
        let mut stream = tokio::net::TcpStream::connect(addr).await.unwrap();
        stream
            .write_all(
                format!(
                    "GET /ws HTTP/1.1\r\nHost: {addr}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n"
                )
                .as_bytes(),
            )
            .await
            .unwrap();
        // Read HTTP 101 Switching Protocols response header.
        let mut hdr = Vec::new();
        while !hdr.windows(4).any(|w| w == b"\r\n\r\n") {
            let b = stream.read_u8().await.unwrap();
            hdr.push(b);
        }
        assert!(String::from_utf8_lossy(&hdr).starts_with("HTTP/1.1 101"));

        async fn read_ws_json(stream: &mut tokio::net::TcpStream) -> Value {
            let mut h = [0u8; 2];
            stream.read_exact(&mut h).await.unwrap();
            let mut len = (h[1] & 0x7f) as usize;
            if len == 126 {
                let mut ext = [0u8; 2];
                stream.read_exact(&mut ext).await.unwrap();
                len = u16::from_be_bytes(ext) as usize;
            } else if len == 127 {
                let mut ext = [0u8; 8];
                stream.read_exact(&mut ext).await.unwrap();
                len = u64::from_be_bytes(ext) as usize;
            }
            let mut payload = vec![0u8; len];
            stream.read_exact(&mut payload).await.unwrap();
            serde_json::from_slice(&payload).unwrap()
        }

        // Trigger live modal and verify WS receives interaction_requested.
        let (st, modal) = post_json(
            &app,
            "/api/session/activate",
            json!({"field": "RenameButton", "index": 0}),
        )
        .await;
        assert_eq!(st, StatusCode::ACCEPTED);
        let int_id = modal["interaction"]["id"].as_str().unwrap().to_owned();

        let ev1 = tokio::time::timeout(Duration::from_secs(5), read_ws_json(&mut stream))
            .await
            .unwrap();
        assert_eq!(ev1["type"], "interaction_requested");
        assert_eq!(ev1["interaction"]["id"], int_id);

        // Reply to modal and verify WS receives interaction_cleared then state_updated!
        let (st, _) = post_json(
            &app,
            &format!("/api/session/interaction/{int_id}"),
            json!({"result": "ok", "values": {"hero": "WS Hero"}}),
        )
        .await;
        assert_eq!(st, StatusCode::OK);

        let ev2 = tokio::time::timeout(Duration::from_secs(5), read_ws_json(&mut stream))
            .await
            .unwrap();
        let ev3 = tokio::time::timeout(Duration::from_secs(5), read_ws_json(&mut stream))
            .await
            .unwrap();
        assert_eq!(ev2["type"], "interaction_cleared");
        assert_eq!(ev3["type"], "state_updated");
        assert_eq!(ev3["state"]["character"]["name"], "WS Hero");

        server_task.abort();
        let _ = std::fs::remove_dir_all(&base);
    }

    #[tokio::test]
    async fn server_blocks_host_file_reads_and_guards_dirty_switch_and_sheet_mismatch() {
        let base = std::env::temp_dir().join(format!(
            "mpmb-serve-security-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let store_dir = base.join("store");
        std::fs::create_dir_all(&store_dir).unwrap();
        let host_secret = base.join("host-secret.txt");
        std::fs::write(&host_secret, "HOST_SECRET_SHOULD_NEVER_LEAK").unwrap();

        // Build a PDF whose startup script tries to read a host file into PC Name.
        let secret_js = serde_json::to_string(host_secret.to_string_lossy().as_ref()).unwrap();
        let mut malicious_doc = lopdf::Document::with_version("1.7");
        let pages_id = malicious_doc.new_object_id();
        let pc_field = malicious_doc.add_object(lopdf::dictionary! {
            "Type" => "Annot",
            "Subtype" => "Widget",
            "FT" => "Tx",
            "T" => lopdf::Object::string_literal("PC Name"),
            "V" => lopdf::Object::string_literal("SafeDefault"),
            "Rect" => vec![10.into(), 700.into(), 200.into(), 724.into()],
            "F" => 4,
            "DA" => lopdf::Object::string_literal("/Helv 10 Tf 0 g"),
        });
        let page_id = malicious_doc.add_object(lopdf::dictionary! {
            "Type" => "Page",
            "Parent" => pages_id,
            "MediaBox" => vec![0.into(), 0.into(), 612.into(), 792.into()],
            "Annots" => vec![pc_field.into()],
        });
        malicious_doc.objects.insert(
            pages_id,
            lopdf::Object::Dictionary(lopdf::dictionary! {
                "Type" => "Pages",
                "Kids" => vec![page_id.into()],
                "Count" => 1,
            }),
        );
        let script_code = format!(
            "try {{ var s = util.readFileIntoStream({secret_js}); getField('PC Name').value = util.stringFromStream(s); }} catch (e) {{ getField('PC Name').value = 'BLOCKED'; }}"
        );
        let js_obj = malicious_doc.add_object(lopdf::dictionary! {
            "S" => "JavaScript",
            "JS" => lopdf::Object::string_literal(script_code),
        });
        let js_names = malicious_doc.add_object(lopdf::dictionary! {
            "Names" => vec![lopdf::Object::string_literal("Probe"), js_obj.into()],
        });
        let form_id = malicious_doc.add_object(lopdf::dictionary! {
            "Fields" => vec![pc_field.into()],
        });
        let cat_id = malicious_doc.add_object(lopdf::dictionary! {
            "Type" => "Catalog",
            "Pages" => pages_id,
            "AcroForm" => form_id,
            "Names" => lopdf::dictionary! { "JavaScript" => js_names },
        });
        malicious_doc.trailer.set("Root", cat_id);
        let mut malicious_bytes = Vec::new();
        malicious_doc.save_to(&mut malicious_bytes).unwrap();
        std::fs::write(store_dir.join("probe.pdf"), &malicious_bytes).unwrap();
        make_interactive_test_pdf(&store_dir.join("other.pdf"));

        let state = AppState::start(&ServeConfig {
            bind: "127.0.0.1:0".parse().unwrap(),
            store: StoreConfig {
                root: store_dir,
                git: None,
            },
            default_sheet: None,
            auth_token: None,
            autosave: false,
            git_auto_sync_secs: 0,
        })
        .unwrap();
        let app = build_router(state);

        // 1. Opening malicious PDF denies host file read; secret never leaks into form state.
        let (st, opened) = post_json(&app, "/api/session/open", json!({"path": "probe.pdf"})).await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(opened["state"]["character"]["name"], "BLOCKED");

        // 2. Edit with mismatched expected sheet returns 409 Conflict without modifying active sheet.
        let (st, _) = post_json(
            &app,
            "/api/session/edit",
            json!({"field": "PC Name", "value": "Wrong", "sheet": "other.pdf"}),
        )
        .await;
        assert_eq!(st, StatusCode::CONFLICT);

        // 3. Valid edit with --no-autosave marks sheet dirty; switching without force returns 409.
        let (st, _) = post_json(
            &app,
            "/api/session/edit",
            json!({"field": "PC Name", "value": "UnsavedHero", "sheet": "probe.pdf"}),
        )
        .await;
        assert_eq!(st, StatusCode::OK);
        let (st, _) = post_json(&app, "/api/session/open", json!({"path": "other.pdf"})).await;
        assert_eq!(st, StatusCode::CONFLICT);

        // 4. Switching with force=true succeeds.
        let (st, switched) = post_json(
            &app,
            "/api/session/open",
            json!({"path": "other.pdf", "force": true}),
        )
        .await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(switched["state"]["path"], "other.pdf");

        let _ = std::fs::remove_dir_all(&base);
    }
}
