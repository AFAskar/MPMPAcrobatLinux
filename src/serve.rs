use crate::{
    pdf::Pdf,
    render::Renderer,
    runtime::{HostCapabilities, InteractionHandler, Runtime},
    storage::{GitConfig, SaveResult, SheetStore, StoreConfig},
};
use anyhow::{anyhow, bail, Context, Result};
use axum::{
    body::Body,
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
        atomic::{AtomicU64, AtomicU8, Ordering},
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
    pub allow_unauthenticated: bool,
    pub autosave: bool,
    pub git_auto_sync_secs: u64,
}

static SERVER_INSTANCE_SEQ: AtomicU64 = AtomicU64::new(1);

#[derive(Default)]
struct StoreSyncState {
    gen: u64,
    last_write_at: Option<Instant>,
}

#[derive(Default)]
struct StoreSyncTracker {
    inner: Mutex<StoreSyncState>,
}

impl StoreSyncTracker {
    fn mark_dirty(&self) -> u64 {
        let mut guard = self.inner.lock().unwrap();
        guard.gen = guard.gen.saturating_add(1);
        guard.last_write_at = Some(Instant::now());
        guard.gen
    }

    fn snapshot_gen(&self) -> u64 {
        self.inner.lock().unwrap().gen
    }

    fn clear_if_unchanged(&self, expected_gen: u64) -> bool {
        let mut guard = self.inner.lock().unwrap();
        if guard.gen == expected_gen {
            guard.last_write_at = None;
            true
        } else {
            false
        }
    }

    fn is_dirty(&self) -> bool {
        self.inner.lock().unwrap().last_write_at.is_some()
    }

    fn is_idle_due(&self, idle_secs: u64) -> bool {
        idle_secs > 0
            && self
                .inner
                .lock()
                .unwrap()
                .last_write_at
                .is_some_and(|t| t.elapsed() >= Duration::from_secs(idle_secs))
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
struct DiscardTarget {
    sheet: String,
    session_id: String,
    revision: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PublicInteraction {
    pub id: String,
    #[serde(rename = "serverInstanceId", default)]
    pub server_instance_id: String,
    pub kind: String,
    pub request: Value,
}

type JobOutcome = std::result::Result<Value, (StatusCode, Value)>;

const JOB_QUEUED: u8 = 0;
const JOB_RUNNING: u8 = 1;
const JOB_CANCELLED: u8 = 2;

#[derive(Clone)]
struct JobGate(Arc<AtomicU8>);

impl JobGate {
    fn new() -> Self {
        Self(Arc::new(AtomicU8::new(JOB_QUEUED)))
    }

    fn try_start(&self) -> bool {
        self.0
            .compare_exchange(JOB_QUEUED, JOB_RUNNING, Ordering::SeqCst, Ordering::SeqCst)
            .is_ok()
    }

    fn try_cancel(&self) -> bool {
        self.0
            .compare_exchange(
                JOB_QUEUED,
                JOB_CANCELLED,
                Ordering::SeqCst,
                Ordering::SeqCst,
            )
            .is_ok()
    }
}

struct PendingInteraction {
    job_id: u64,
    public: PublicInteraction,
    tx: mpsc::SyncSender<Value>,
}

struct InteractionBridge {
    server_instance_id: String,
    seq: AtomicU64,
    state_seq: AtomicU64,
    current_job: AtomicU64,
    active: Mutex<Option<PendingInteraction>>,
    in_flight_jobs: Mutex<BTreeMap<u64, watch::Receiver<Option<JobOutcome>>>>,
    interaction_tx: watch::Sender<Option<(u64, PublicInteraction)>>,
    events_tx: broadcast::Sender<Value>,
}

impl InteractionBridge {
    fn new(
        server_instance_id: String,
        interaction_tx: watch::Sender<Option<(u64, PublicInteraction)>>,
        events_tx: broadcast::Sender<Value>,
    ) -> Arc<Self> {
        Arc::new(Self {
            server_instance_id,
            seq: AtomicU64::new(1),
            state_seq: AtomicU64::new(1),
            current_job: AtomicU64::new(0),
            active: Mutex::new(None),
            in_flight_jobs: Mutex::new(BTreeMap::new()),
            interaction_tx,
            events_tx,
        })
    }

    fn next_state_seq(&self) -> u64 {
        self.state_seq.fetch_add(1, Ordering::SeqCst)
    }

    fn register_job(&self, job_id: u64, rx: watch::Receiver<Option<JobOutcome>>) {
        self.in_flight_jobs.lock().unwrap().insert(job_id, rx);
    }

    fn finish_job(&self, job_id: u64) {
        self.in_flight_jobs.lock().unwrap().remove(&job_id);
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

    fn respond(
        &self,
        id: &str,
        reply: Value,
    ) -> Result<(u64, watch::Receiver<Option<JobOutcome>>)> {
        if let Some(reply_inst) = reply.get("serverInstanceId").and_then(Value::as_str) {
            if reply_inst != self.server_instance_id {
                bail!("interaction serverInstanceId mismatch (server restarted)");
            }
        }
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
        let _ = self.events_tx.send(json!({
            "type": "interaction_cleared",
            "id": pending.public.id,
            "serverInstanceId": self.server_instance_id,
        }));
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
        let id = format!(
            "{}-int-{}",
            self.server_instance_id,
            self.seq.fetch_add(1, Ordering::SeqCst)
        );
        let public = PublicInteraction {
            id,
            server_instance_id: self.server_instance_id.clone(),
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
            // Publish both notifications while holding `active` so `respond()`
            // cannot emit `interaction_cleared` before `interaction_requested`.
            let _ = self.interaction_tx.send(Some((job_id, public.clone())));
            let _ = self.events_tx.send(json!({
                "type": "interaction_requested",
                "interaction": public,
            }));
        }
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
        gate: JobGate,
        done: watch::Sender<Option<JobOutcome>>,
        rel_path: String,
        force: bool,
        discard: Option<DiscardTarget>,
        expected_session: Option<String>,
    },
    GetState {
        reply: mpsc::SyncSender<Result<Value>>,
    },
    GetField {
        name: String,
        expected_sheet: Option<String>,
        expected_session: Option<String>,
        reply: mpsc::SyncSender<Result<Value>>,
    },
    GetPageWidgets {
        page: i32,
        expected_sheet: Option<String>,
        expected_session: Option<String>,
        expected_rev: Option<u64>,
        reply: mpsc::SyncSender<Result<Value>>,
    },
    RenderPagePng {
        page: i32,
        width: usize,
        expected_sheet: Option<String>,
        expected_session: Option<String>,
        expected_rev: Option<u64>,
        reply: mpsc::SyncSender<Result<Vec<u8>>>,
    },
    Edit {
        job_id: u64,
        gate: JobGate,
        done: watch::Sender<Option<JobOutcome>>,
        field: String,
        value: Value,
        mode: String,
        expected_sheet: Option<String>,
        expected_session: Option<String>,
    },
    Activate {
        job_id: u64,
        gate: JobGate,
        done: watch::Sender<Option<JobOutcome>>,
        field: String,
        index: i64,
        shift: bool,
        modifier: bool,
        expected_sheet: Option<String>,
        expected_session: Option<String>,
    },
    InvokeMenu {
        job_id: u64,
        gate: JobGate,
        done: watch::Sender<Option<JobOutcome>>,
        name: String,
        expected_sheet: Option<String>,
        expected_session: Option<String>,
    },
    RunCommand {
        job_id: u64,
        gate: JobGate,
        done: watch::Sender<Option<JobOutcome>>,
        action: String,
        expected_sheet: Option<String>,
        expected_session: Option<String>,
    },
    RunBookmark {
        job_id: u64,
        gate: JobGate,
        done: watch::Sender<Option<JobOutcome>>,
        path: String,
        expected_sheet: Option<String>,
        expected_session: Option<String>,
    },
    SaveNow {
        job_id: u64,
        gate: JobGate,
        done: watch::Sender<Option<JobOutcome>>,
        force: bool,
        expected_sheet: Option<String>,
        expected_session: Option<String>,
    },
    GitSync {
        job_id: u64,
        gate: JobGate,
        done: watch::Sender<Option<JobOutcome>>,
        message: String,
    },
    GitPull {
        job_id: u64,
        gate: JobGate,
        done: watch::Sender<Option<JobOutcome>>,
        force: bool,
        discard: Option<DiscardTarget>,
        expected_session: Option<String>,
    },
    CheckIdleAutoSync {
        job_id: u64,
        gate: JobGate,
        done: watch::Sender<Option<JobOutcome>>,
        idle_secs: u64,
    },
}

struct ActiveSheet {
    rel_path: String,
    session_id: String,
    pdf: Arc<Pdf>,
    rt: Runtime,
    disk_sha256: String,
    revision: u64,
    dirty_since_save: bool,
    sidecar_dirty: bool,
    last_tick: Instant,
    projected: Option<(u64, Vec<u8>)>,
    page_pngs: BTreeMap<(i32, u64, usize), Vec<u8>>,
    page_sizes: BTreeMap<(i32, u64), (f32, f32)>,
}

struct SheetWorker {
    store: Arc<SheetStore>,
    bridge: Arc<InteractionBridge>,
    sync_tracker: Arc<StoreSyncTracker>,
    job_seq: Arc<AtomicU64>,
    server_instance_id: String,
    session_seq: u64,
    renderer: Option<Renderer>,
    autosave: bool,
    capabilities: HostCapabilities,
    active: Option<ActiveSheet>,
    last_save_conflict: Option<SaveResult>,
}

impl SheetWorker {
    fn run(mut self, rx: mpsc::Receiver<WorkerCommand>) {
        loop {
            let wait = self
                .active
                .as_ref()
                .map(|sh| Duration::from_millis(100).saturating_sub(sh.last_tick.elapsed()))
                .unwrap_or_else(|| Duration::from_millis(100));
            match rx.recv_timeout(wait) {
                Ok(cmd) => {
                    self.handle_command(cmd);
                    if self
                        .active
                        .as_ref()
                        .is_some_and(|sh| sh.last_tick.elapsed() >= Duration::from_millis(100))
                    {
                        self.tick_timers();
                    }
                }
                Err(mpsc::RecvTimeoutError::Timeout) => self.tick_timers(),
                Err(mpsc::RecvTimeoutError::Disconnected) => break,
            }
        }
    }

    fn tick_timers(&mut self) {
        let elapsed = {
            let Some(sh) = self.active.as_mut() else {
                return;
            };
            let elapsed = sh.last_tick.elapsed().as_millis() as u64;
            if elapsed < 50 {
                return;
            }
            let has_timers = sh
                .rt
                .diagnostics()
                .ok()
                .and_then(|d| d.get("timers").and_then(Value::as_u64))
                .unwrap_or(0)
                > 0;
            if !has_timers {
                sh.last_tick = Instant::now();
                return;
            }
            elapsed
        };
        let job_id = self.job_seq.fetch_add(1, Ordering::SeqCst);
        let (done_tx, done_rx) = watch::channel(None);
        self.bridge.register_job(job_id, done_rx);
        self.bridge.set_current_job(job_id);

        let (prev_rev, adv_res, next_rev) = {
            let sh = self.active.as_mut().unwrap();
            sh.last_tick = Instant::now();
            let prev = sh.revision;
            let res = sh.rt.advance(elapsed);
            let next = sh
                .rt
                .eval("__host.revision")
                .ok()
                .and_then(|v| v.as_u64())
                .unwrap_or(prev);
            (prev, res, next)
        };

        let outcome: JobOutcome = if next_rev != prev_rev {
            let mut_res = self.after_mutation();
            if let Err(err) = adv_res {
                let msg = format!("Timer callback failed: {err:#}");
                let _ = self.bridge.events_tx.send(json!({
                    "type": "error",
                    "message": msg,
                }));
                if let Ok(val) = &mut_res {
                    if let Some(state) = val.get("state") {
                        let _ = self.bridge.events_tx.send(json!({
                            "type": "state_updated",
                            "state": state,
                        }));
                    }
                }
                Err((StatusCode::BAD_REQUEST, json!({"error": msg})))
            } else {
                match mut_res {
                    Ok(val) => {
                        if let Some(state) = val.get("state") {
                            let _ = self.bridge.events_tx.send(json!({
                                "type": "state_updated",
                                "state": state,
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
                        Err((StatusCode::BAD_REQUEST, json!({"error": msg})))
                    }
                }
            }
        } else if let Err(err) = adv_res {
            let msg = format!("Timer callback failed: {err:#}");
            let _ = self.bridge.events_tx.send(json!({
                "type": "error",
                "message": msg,
            }));
            Err((StatusCode::BAD_REQUEST, json!({"error": msg})))
        } else {
            Ok(json!({"status": "idle"}))
        };

        let _ = self.bridge.interaction_tx.send(None);
        let _ = done_tx.send(Some(outcome));
        self.bridge.finish_job(job_id);
    }

    fn handle_command(&mut self, cmd: WorkerCommand) {
        match cmd {
            WorkerCommand::GetState { reply } => {
                let _ = reply.send(self.build_state_payload());
            }
            WorkerCommand::GetField {
                name,
                expected_sheet,
                expected_session,
                reply,
            } => {
                let res = self
                    .verify_expected_target(expected_sheet.as_deref(), expected_session.as_deref())
                    .and_then(|()| self.inspect_field(&name));
                let _ = reply.send(res);
            }
            WorkerCommand::GetPageWidgets {
                page,
                expected_sheet,
                expected_session,
                expected_rev,
                reply,
            } => {
                let res = self.page_widgets(
                    page,
                    expected_sheet.as_deref(),
                    expected_session.as_deref(),
                    expected_rev,
                );
                let _ = reply.send(res);
            }
            WorkerCommand::RenderPagePng {
                page,
                width,
                expected_sheet,
                expected_session,
                expected_rev,
                reply,
            } => {
                let res = self.render_page_png(
                    page,
                    width,
                    expected_sheet.as_deref(),
                    expected_session.as_deref(),
                    expected_rev,
                );
                let _ = reply.send(res);
            }
            WorkerCommand::CheckIdleAutoSync {
                job_id,
                gate,
                done,
                idle_secs,
            } => {
                let should_sync = idle_secs > 0
                    && self.store.git_enabled()
                    && self.sync_tracker.is_idle_due(idle_secs);
                if should_sync {
                    self.run_job(job_id, gate, done, |w| {
                        w.do_git_sync("Auto-sync MPMB session")
                    });
                } else {
                    let _ = done.send(Some(Ok(json!({"status": "skipped"}))));
                    self.bridge.finish_job(job_id);
                }
            }
            WorkerCommand::Open {
                job_id,
                gate,
                done,
                rel_path,
                force,
                discard,
                expected_session,
            } => {
                self.run_job(job_id, gate, done, |w| {
                    w.open_sheet(
                        &rel_path,
                        force,
                        discard.as_ref(),
                        expected_session.as_deref(),
                    )
                });
            }
            WorkerCommand::Edit {
                job_id,
                gate,
                done,
                field,
                value,
                mode,
                expected_sheet,
                expected_session,
            } => {
                self.run_job(job_id, gate, done, |w| {
                    w.verify_expected_target(
                        expected_sheet.as_deref(),
                        expected_session.as_deref(),
                    )?;
                    w.edit_field(&field, &value, &mode)
                });
            }
            WorkerCommand::Activate {
                job_id,
                gate,
                done,
                field,
                index,
                shift,
                modifier,
                expected_sheet,
                expected_session,
            } => {
                self.run_job(job_id, gate, done, |w| {
                    w.verify_expected_target(
                        expected_sheet.as_deref(),
                        expected_session.as_deref(),
                    )?;
                    w.activate_field(&field, index, shift, modifier)
                });
            }
            WorkerCommand::InvokeMenu {
                job_id,
                gate,
                done,
                name,
                expected_sheet,
                expected_session,
            } => {
                self.run_job(job_id, gate, done, |w| {
                    w.verify_expected_target(
                        expected_sheet.as_deref(),
                        expected_session.as_deref(),
                    )?;
                    w.invoke_menu(&name)
                });
            }
            WorkerCommand::RunCommand {
                job_id,
                gate,
                done,
                action,
                expected_sheet,
                expected_session,
            } => {
                self.run_job(job_id, gate, done, |w| {
                    w.verify_expected_target(
                        expected_sheet.as_deref(),
                        expected_session.as_deref(),
                    )?;
                    w.run_command(&action)
                });
            }
            WorkerCommand::RunBookmark {
                job_id,
                gate,
                done,
                path,
                expected_sheet,
                expected_session,
            } => {
                self.run_job(job_id, gate, done, |w| {
                    w.verify_expected_target(
                        expected_sheet.as_deref(),
                        expected_session.as_deref(),
                    )?;
                    w.run_bookmark(&path)
                });
            }
            WorkerCommand::SaveNow {
                job_id,
                gate,
                done,
                force,
                expected_sheet,
                expected_session,
            } => {
                self.run_job(job_id, gate, done, |w| {
                    w.verify_expected_target(
                        expected_sheet.as_deref(),
                        expected_session.as_deref(),
                    )?;
                    w.save_active(force)
                });
            }
            WorkerCommand::GitSync {
                job_id,
                gate,
                done,
                message,
            } => {
                self.run_job(job_id, gate, done, |w| w.do_git_sync(&message));
            }
            WorkerCommand::GitPull {
                job_id,
                gate,
                done,
                force,
                discard,
                expected_session,
            } => {
                self.run_job(job_id, gate, done, |w| {
                    w.do_git_pull(force, discard.as_ref(), expected_session.as_deref())
                });
            }
        }
    }

    fn run_job<F>(
        &mut self,
        job_id: u64,
        gate: JobGate,
        done: watch::Sender<Option<JobOutcome>>,
        f: F,
    ) where
        F: FnOnce(&mut Self) -> Result<Value>,
    {
        if !gate.try_start() {
            // Cancelled before execution (e.g. rejected with 409 because an earlier
            // job opened a modal interaction while this job was queued).
            self.bridge.finish_job(job_id);
            return;
        }
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

    fn verify_expected_target(
        &self,
        expected_sheet: Option<&str>,
        expected_session: Option<&str>,
    ) -> Result<()> {
        if let Some(exp) = expected_sheet.map(str::trim).filter(|s| !s.is_empty()) {
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
        }
        if let Some(exp_sess) = expected_session.map(str::trim).filter(|s| !s.is_empty()) {
            let active_sess = self
                .active
                .as_ref()
                .map(|s| s.session_id.as_str())
                .unwrap_or("<none>");
            if active_sess != exp_sess {
                bail!(
                    "conflict: active sheet session changed (expected '{exp_sess}', active is '{active_sess}'); refresh before retrying"
                );
            }
        }
        Ok(())
    }

    fn verify_page_target(
        &self,
        expected_sheet: Option<&str>,
        expected_session: Option<&str>,
        expected_rev: Option<u64>,
        current_rev: u64,
    ) -> Result<()> {
        self.verify_expected_target(expected_sheet, expected_session)?;
        if let Some(exp_rev) = expected_rev {
            if exp_rev != current_rev {
                bail!(
                    "conflict: active sheet revision changed (expected rev {exp_rev}, active is rev {current_rev}); refresh before retrying"
                );
            }
        }
        Ok(())
    }

    fn check_discard_guard(
        &self,
        action: &str,
        force: bool,
        discard: Option<&DiscardTarget>,
        expected_session: Option<&str>,
    ) -> Option<Value> {
        let cur = self.active.as_ref()?;
        let current_target = DiscardTarget {
            sheet: cur.rel_path.clone(),
            session_id: cur.session_id.clone(),
            revision: cur.revision,
        };
        if !cur.dirty_since_save {
            if let Some(exp_sess) = expected_session.map(str::trim).filter(|s| !s.is_empty()) {
                if cur.session_id != exp_sess {
                    return Some(json!({
                        "status": "conflict",
                        "code": "discard_target_stale",
                        "error": format!(
                            "conflict: active session changed before {action} (expected session '{exp_sess}', active is '{}' session '{}' rev {}); refresh before retrying",
                            cur.rel_path, cur.session_id, cur.revision
                        ),
                        "discardTarget": current_target,
                    }));
                }
            }
            if let Some(req_discard) = discard {
                if req_discard.sheet != cur.rel_path || req_discard.session_id != cur.session_id {
                    return Some(json!({
                        "status": "conflict",
                        "code": "discard_target_stale",
                        "error": format!(
                            "conflict: active session changed before {action} (expected '{}' session '{}', active is '{}' session '{}' rev {}); refresh before retrying",
                            req_discard.sheet,
                            req_discard.session_id,
                            cur.rel_path,
                            cur.session_id,
                            cur.revision,
                        ),
                        "discardTarget": current_target,
                    }));
                }
            }
            return None;
        }
        if !force {
            return Some(json!({
                "status": "conflict",
                "code": "unsaved_edits",
                "error": format!(
                    "conflict: active sheet '{}' has unsaved edits (rev {}); save first or confirm discarding them before {action}",
                    cur.rel_path, cur.revision
                ),
                "discardTarget": current_target,
            }));
        }
        if let Some(exp_sess) = expected_session.map(str::trim).filter(|s| !s.is_empty()) {
            if cur.session_id != exp_sess {
                return Some(json!({
                    "status": "conflict",
                    "code": "discard_target_stale",
                    "error": format!(
                        "conflict: active unsaved session changed before {action} (expected session '{exp_sess}', active is '{}' session '{}' rev {}); refresh before discarding",
                        cur.rel_path, cur.session_id, cur.revision
                    ),
                    "discardTarget": current_target,
                }));
            }
        }
        let Some(req_discard) = discard else {
            return Some(json!({
                "status": "conflict",
                "code": "discard_target_required",
                "error": format!(
                    "conflict: discarding unsaved edits on '{}' (rev {}) requires passing the matching discardTarget",
                    cur.rel_path, cur.revision
                ),
                "discardTarget": current_target,
            }));
        };
        if req_discard != &current_target {
            return Some(json!({
                "status": "conflict",
                "code": "discard_target_stale",
                "error": format!(
                    "conflict: active unsaved edits changed before {action} (expected '{}' session '{}' rev {}, active is '{}' session '{}' rev {}); refresh before discarding",
                    req_discard.sheet,
                    req_discard.session_id,
                    req_discard.revision,
                    cur.rel_path,
                    cur.session_id,
                    cur.revision,
                ),
                "discardTarget": current_target,
            }));
        }
        None
    }

    fn open_sheet(
        &mut self,
        rel_path: &str,
        force: bool,
        discard: Option<&DiscardTarget>,
        expected_session: Option<&str>,
    ) -> Result<Value> {
        if let Some(conflict) =
            self.check_discard_guard("opening another sheet", force, discard, expected_session)
        {
            return Ok(conflict);
        }
        self.open_sheet_unchecked(rel_path)
    }

    fn open_sheet_unchecked(&mut self, rel_path: &str) -> Result<Value> {
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
            self.capabilities,
        )?;
        // Reject sheets that fail their startup readiness check BEFORE replacing
        // the currently active session.
        rt.ready()?;
        let revision = rt
            .eval("__host.revision")
            .ok()
            .and_then(|v| v.as_u64())
            .unwrap_or(0);
        self.session_seq += 1;
        let session_id = format!("{}-s{}", self.server_instance_id, self.session_seq);
        self.active = Some(ActiveSheet {
            rel_path: norm,
            session_id,
            pdf,
            rt,
            disk_sha256: sha,
            revision,
            dirty_since_save: false,
            sidecar_dirty: false,
            last_tick: Instant::now(),
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
        let state_seq = self.bridge.next_state_seq();
        let dirty_since_sync = self.sync_tracker.is_dirty();
        let Some(sh) = &self.active else {
            return Ok(json!({
                "open": false,
                "serverInstanceId": self.server_instance_id,
                "stateSeq": state_seq,
                "dirtySinceSync": dirty_since_sync,
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
        obj.insert("serverInstanceId".into(), json!(self.server_instance_id));
        obj.insert("sessionId".into(), json!(sh.session_id));
        obj.insert("stateSeq".into(), json!(state_seq));
        obj.insert("path".into(), json!(sh.rel_path));
        obj.insert("diskSha256".into(), json!(sh.disk_sha256));
        obj.insert("dirtySinceSave".into(), json!(sh.dirty_since_save));
        obj.insert("dirtySinceSync".into(), json!(dirty_since_sync));
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
        if rev != sh.revision {
            sh.revision = rev;
            sh.page_pngs.clear();
            sh.page_sizes.retain(|&(_, r), _| r == rev);
        }
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

    fn page_widgets(
        &mut self,
        page: i32,
        expected_sheet: Option<&str>,
        expected_session: Option<&str>,
        expected_rev: Option<u64>,
    ) -> Result<Value> {
        self.verify_expected_target(expected_sheet, expected_session)?;
        let (rev, projected) = self.ensure_projected()?;
        self.verify_page_target(expected_sheet, expected_session, expected_rev, rev)?;
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
            "sheet": sh.rel_path,
            "sessionId": sh.session_id,
            "page": page,
            "revision": rev,
            "pageSize": [size.0, size.1],
            "widgets": widgets,
        }))
    }

    fn render_page_png(
        &mut self,
        page: i32,
        width: usize,
        expected_sheet: Option<&str>,
        expected_session: Option<&str>,
        expected_rev: Option<u64>,
    ) -> Result<Vec<u8>> {
        self.verify_expected_target(expected_sheet, expected_session)?;
        let width = width.clamp(320, 2200);
        let quantized_w = ((width as f32 / 64.0).round() as usize * 64).clamp(320, 2200);
        let (rev, projected) = self.ensure_projected()?;
        self.verify_page_target(expected_sheet, expected_session, expected_rev, rev)?;
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
        let mut mutated = false;
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
                sh.page_sizes.clear();
                sh.dirty_since_save = true;
                mutated = true;
            }
        }
        if mutated {
            self.sync_tracker.mark_dirty();
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

    fn finish_mutation(&mut self, eval_result: Result<()>) -> Result<Value> {
        let rev_before = self.active.as_ref().map(|s| s.revision);
        // Reconcile sheet revision, dirty tracking, autosave, and projected
        // cache even if the script threw after partially mutating fields.
        let mutation = self.after_mutation();
        let rev_after = self.active.as_ref().map(|s| s.revision);
        if let Err(err) = eval_result {
            if rev_after != rev_before {
                if let Ok(val) = &mutation {
                    if let Some(state) = val.get("state") {
                        let _ = self.bridge.events_tx.send(json!({
                            "type": "state_updated",
                            "state": state,
                        }));
                    }
                }
            }
            return Err(err);
        }
        mutation
    }

    fn edit_field(&mut self, field: &str, value: &Value, mode: &str) -> Result<Value> {
        let eval_result = {
            let sh = self.active.as_ref().context("no sheet is open")?;
            match mode {
                "choice" => sh.rt.select_choice(field, value),
                "direct" => sh.rt.edit(field, value),
                _ => sh.rt.user_edit(field, value),
            }
        };
        self.finish_mutation(eval_result)
    }

    fn activate_field(
        &mut self,
        field: &str,
        index: i64,
        shift: bool,
        modifier: bool,
    ) -> Result<Value> {
        let eval_result = {
            let sh = self.active.as_ref().context("no sheet is open")?;
            let qname = serde_json::to_string(field)?;
            let mods = json!({"shift": shift, "modifier": modifier});
            sh.rt
                .eval(&format!("__host.activate({qname},{index},{mods})"))
                .map(|_| ())
        };
        self.finish_mutation(eval_result)
    }

    fn invoke_menu(&mut self, name: &str) -> Result<Value> {
        let eval_result = {
            let sh = self.active.as_ref().context("no sheet is open")?;
            let qname = serde_json::to_string(name)?;
            sh.rt
                .eval(&format!("__host.invokeMenu({qname})"))
                .map(|_| ())
        };
        self.finish_mutation(eval_result)
    }

    fn run_command(&mut self, action: &str) -> Result<Value> {
        let script = match action {
            "short_rest" => Some((
                true,
                "if(typeof resetLimFeaUsed==='function')resetLimFeaUsed('short rest');calculateNow();",
            )),
            "long_rest" => Some((
                true,
                "if(typeof resetLimFeaUsed==='function')resetLimFeaUsed('long rest');var hm=getField('HP Max'),hc=getField('HP Current');if(hm&&hc&&hm.valueAsString)hc.value=hm.valueAsString;calculateNow();",
            )),
            "spell_sheet" => Some((true, "GenerateSpellSheet()")),
            "add_companion" => Some((true, "DoTemplate('AScomp','Add',null,true)")),
            "add_wildshape" => Some((true, "DoTemplate('WSfront','Add',null,true)")),
            "recalculate" => Some((false, "calculateNow()")),
            other => bail!("unsupported command action: {other}"),
        };
        let eval_result = {
            let sh = self.active.as_ref().context("no sheet is open")?;
            let (is_command, code) = script.unwrap();
            if is_command {
                sh.rt.command(code)
            } else {
                sh.rt.eval(code).map(|_| ())
            }
        };
        self.finish_mutation(eval_result)
    }

    fn run_bookmark(&mut self, path: &str) -> Result<Value> {
        if !is_safe_bookmark_path(path) {
            bail!("invalid bookmark path");
        }
        let eval_result = {
            let sh = self.active.as_ref().context("no sheet is open")?;
            sh.rt.eval(&format!("{path}.execute()")).map(|_| ())
        };
        self.finish_mutation(eval_result)
    }

    fn persist_active(&mut self, force: bool) -> Result<SaveResult> {
        let sh = self.active.as_mut().context("no sheet is open")?;
        sh.rt.ready()?;
        let rev = sh
            .rt
            .eval("__host.revision")
            .ok()
            .and_then(|v| v.as_u64())
            .unwrap_or(sh.revision);
        if rev != sh.revision {
            sh.revision = rev;
            sh.projected = None;
            sh.page_pngs.clear();
            sh.page_sizes.clear();
            sh.dirty_since_save = true;
        }

        // If a prior save already replaced the PDF on disk and only sidecar
        // publication failed, retry ONLY the sidecar write without overwriting
        // the PDF (unless the sheet has new edits or `force` was requested).
        if !force && !sh.dirty_since_save && sh.sidecar_dirty {
            let extracted = sh.rt.eval(EXTRACT_STATE_JS).unwrap_or(Value::Null);
            let sidecar = build_state_sidecar(&sh.rel_path, &extracted, &sh.disk_sha256);
            self.store
                .write_sidecar_atomic(&sh.rel_path, &sh.disk_sha256, &sidecar)?;
            sh.sidecar_dirty = false;
            self.sync_tracker.mark_dirty();
            self.last_save_conflict = None;
            let size_bytes = sh
                .projected
                .as_ref()
                .map(|(_, b)| b.len() as u64)
                .unwrap_or(0);
            return Ok(SaveResult::Saved {
                sha256: sh.disk_sha256.clone(),
                size_bytes,
                sidecar_written: true,
            });
        }

        let snap = sh.rt.snapshot()?;
        let pdf_bytes = sh.pdf.project(&snap)?;
        let post_rev = sh
            .rt
            .eval("__host.revision")
            .ok()
            .and_then(|v| v.as_u64())
            .unwrap_or(sh.revision);
        if post_rev != sh.revision {
            sh.revision = post_rev;
            sh.page_pngs.clear();
            sh.page_sizes.clear();
        }
        sh.projected = Some((sh.revision, pdf_bytes.clone()));

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
                sh.sidecar_dirty = false;
                self.sync_tracker.mark_dirty();
                self.last_save_conflict = None;
            }
            SaveResult::PartialSidecarFailed {
                sha256,
                sidecar_error,
                ..
            } => {
                // Record the new PDF hash so a follow-up retry writes only the
                // unfinished sidecar instead of conflicting with our own PDF write.
                sh.disk_sha256 = sha256.clone();
                sh.dirty_since_save = false;
                sh.sidecar_dirty = true;
                self.sync_tracker.mark_dirty();
                self.last_save_conflict = None;
                bail!("PDF saved, but sidecar publication failed: {sidecar_error}");
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
            SaveResult::PartialSidecarFailed { .. } => (
                "partial",
                "Saved PDF to disk, but failed updating state sidecar",
            ),
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
        let sync_gen = self.sync_tracker.snapshot_gen();
        let sync = self.store.git_sync(&commit_msg)?;
        let git = self.store.git_status()?;
        let pending = git.dirty || (git.ahead > 0 && !git.head_backed_up);
        if (sync.pushed || sync.status == "clean") && !pending {
            self.sync_tracker.clear_if_unchanged(sync_gen);
        } else if pending && !self.sync_tracker.is_dirty() {
            self.sync_tracker.mark_dirty();
        }
        let state = self.build_state_payload()?;
        Ok(json!({
            "status": "ok",
            "sync": sync,
            "git": git,
            "state": state,
        }))
    }

    fn do_git_pull(
        &mut self,
        force: bool,
        discard: Option<&DiscardTarget>,
        expected_session: Option<&str>,
    ) -> Result<Value> {
        if let Some(conflict) =
            self.check_discard_guard("pulling from Git", force, discard, expected_session)
        {
            return Ok(conflict);
        }
        let pull = self.store.git_pull()?;
        if pull.updated {
            if let Some(rel) = self.active.as_ref().map(|s| s.rel_path.clone()) {
                match self.store.read_sheet_bytes(&rel) {
                    Ok(_) => {
                        let _ = self.open_sheet_unchecked(&rel)?;
                    }
                    Err(err) => {
                        let is_missing = err.chain().any(|cause| {
                            cause
                                .downcast_ref::<std::io::Error>()
                                .is_some_and(|io| io.kind() == std::io::ErrorKind::NotFound)
                        });
                        if is_missing {
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
                        return Err(err);
                    }
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

fn validate_bind_auth(
    bind: SocketAddr,
    auth_token: Option<&str>,
    allow_unauthenticated: bool,
) -> Result<()> {
    let has_token = auth_token.is_some_and(|t| !t.trim().is_empty());
    if !bind.ip().is_loopback() && !has_token && !allow_unauthenticated {
        bail!(
            "refusing to bind non-loopback address {bind} without authentication; \
             set --auth-token / MPMB_AUTH_TOKEN, bind loopback (127.0.0.1), \
             or explicitly opt in with --allow-unauthenticated / MPMB_ALLOW_UNAUTHENTICATED=1"
        );
    }
    Ok(())
}

#[derive(Clone)]
struct AppState {
    store: Arc<SheetStore>,
    bridge: Arc<InteractionBridge>,
    sync_tracker: Arc<StoreSyncTracker>,
    server_instance_id: String,
    cmd_tx: mpsc::Sender<WorkerCommand>,
    job_seq: Arc<AtomicU64>,
    interaction_rx: watch::Receiver<Option<(u64, PublicInteraction)>>,
    auth_token: Option<String>,
    pdfium_available: bool,
}

impl AppState {
    fn start(config: &ServeConfig) -> Result<Self> {
        Self::start_with_capabilities(config, HostCapabilities::server_restricted())
    }

    fn start_with_capabilities(
        config: &ServeConfig,
        capabilities: HostCapabilities,
    ) -> Result<Self> {
        validate_bind_auth(
            config.bind,
            config.auth_token.as_deref(),
            config.allow_unauthenticated,
        )?;
        let store = Arc::new(SheetStore::open(config.store.clone())?);
        let (interaction_tx, interaction_rx) = watch::channel(None);
        let (events_tx, _) = broadcast::channel(64);
        let sync_tracker = Arc::new(StoreSyncTracker::default());
        if store.git_enabled() {
            if let Ok(status) = store.git_status() {
                if status.dirty || (status.ahead > 0 && !status.head_backed_up) {
                    sync_tracker.mark_dirty();
                }
            }
        }
        let job_seq = Arc::new(AtomicU64::new(1));
        let boot_ns = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0);
        let server_instance_id = format!(
            "srv-{boot_ns}-{}-{}",
            std::process::id(),
            SERVER_INSTANCE_SEQ.fetch_add(1, Ordering::SeqCst)
        );
        let bridge = InteractionBridge::new(server_instance_id.clone(), interaction_tx, events_tx);
        let (cmd_tx, cmd_rx) = mpsc::channel();

        let (ready_tx, ready_rx) = mpsc::sync_channel::<bool>(1);
        let worker_store = Arc::clone(&store);
        let worker_bridge = Arc::clone(&bridge);
        let worker_sync_tracker = Arc::clone(&sync_tracker);
        let worker_job_seq = Arc::clone(&job_seq);
        let worker_instance_id = server_instance_id.clone();
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
                    sync_tracker: worker_sync_tracker,
                    job_seq: worker_job_seq,
                    server_instance_id: worker_instance_id,
                    session_seq: 0,
                    renderer,
                    autosave,
                    capabilities,
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
            sync_tracker,
            server_instance_id,
            cmd_tx,
            job_seq,
            interaction_rx,
            auth_token: config.auth_token.clone().filter(|t| !t.trim().is_empty()),
            pdfium_available,
        };

        if let Some(default_sheet) = &config.default_sheet {
            let job_id = state.job_seq.fetch_add(1, Ordering::SeqCst);
            let gate = JobGate::new();
            let (done_tx, done_rx) = watch::channel(None);
            state.bridge.register_job(job_id, done_rx);
            let _ = state.cmd_tx.send(WorkerCommand::Open {
                job_id,
                gate,
                done: done_tx,
                rel_path: default_sheet.clone(),
                force: true,
                discard: None,
                expected_session: None,
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
        make_cmd: impl FnOnce(u64, JobGate, watch::Sender<Option<JobOutcome>>) -> WorkerCommand,
    ) -> Response {
        if let Some(conflict) = self.interaction_conflict_response() {
            return conflict;
        }
        let job_id = self.job_seq.fetch_add(1, Ordering::SeqCst);
        let gate = JobGate::new();
        let (done_tx, done_rx) = watch::channel(None);
        self.bridge.register_job(job_id, done_rx.clone());
        let mut int_rx = self.interaction_rx.clone();
        if self
            .cmd_tx
            .send(make_cmd(job_id, gate.clone(), done_tx))
            .is_err()
        {
            self.bridge.finish_job(job_id);
            return err_response(StatusCode::INTERNAL_SERVER_ERROR, "sheet worker stopped");
        }
        self.await_job_or_interaction(done_rx, &mut int_rx, job_id, Some(&gate), None)
            .await
    }

    async fn await_job_or_interaction(
        &self,
        mut done_rx: watch::Receiver<Option<JobOutcome>>,
        int_rx: &mut watch::Receiver<Option<(u64, PublicInteraction)>>,
        target_job_id: u64,
        gate: Option<&JobGate>,
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
                    // Only return 409 Conflict if we atomically cancel our queued
                    // job before the worker starts executing it. If our job has
                    // already started running, keep waiting for its own result.
                    if gate.is_some_and(|g| g.try_cancel()) {
                        self.bridge.finish_job(target_job_id);
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
#[serde(rename_all = "camelCase")]
struct OpenRequest {
    path: String,
    #[serde(default)]
    force: bool,
    #[serde(default)]
    discard: Option<DiscardTarget>,
    #[serde(default)]
    session: Option<String>,
}

#[derive(Deserialize)]
struct FieldQuery {
    name: String,
    sheet: Option<String>,
    session: Option<String>,
    token: Option<String>,
}

#[derive(Deserialize)]
struct PageImageQuery {
    w: Option<usize>,
    sheet: Option<String>,
    rev: Option<u64>,
    session: Option<String>,
    token: Option<String>,
}

#[derive(Deserialize, Default)]
struct PageWidgetsQuery {
    sheet: Option<String>,
    rev: Option<u64>,
    session: Option<String>,
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
    #[serde(default)]
    session: Option<String>,
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
    #[serde(default)]
    session: Option<String>,
}

#[derive(Deserialize)]
struct MenuRequest {
    name: String,
    #[serde(default)]
    sheet: Option<String>,
    #[serde(default)]
    session: Option<String>,
}

#[derive(Deserialize)]
struct CommandRequest {
    action: String,
    #[serde(default)]
    sheet: Option<String>,
    #[serde(default)]
    session: Option<String>,
}

#[derive(Deserialize)]
struct BookmarkRequest {
    path: String,
    #[serde(default)]
    sheet: Option<String>,
    #[serde(default)]
    session: Option<String>,
}

#[derive(Deserialize, Default)]
struct SaveRequest {
    #[serde(default)]
    force: bool,
    #[serde(default)]
    sheet: Option<String>,
    #[serde(default)]
    session: Option<String>,
}

#[derive(Deserialize, Default)]
#[serde(rename_all = "camelCase")]
struct PullRequest {
    #[serde(default)]
    force: bool,
    #[serde(default)]
    discard: Option<DiscardTarget>,
    #[serde(default)]
    session: Option<String>,
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
        .route("/livez", get(handle_livez))
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

async fn handle_livez() -> impl IntoResponse {
    Json(json!({
        "ok": true,
        "version": env!("CARGO_PKG_VERSION"),
    }))
}

async fn handle_healthz(State(state): State<AppState>) -> impl IntoResponse {
    // Never acquire the store mutex or shell out to Git in health/readiness
    // handlers so slow Git sync pushes cannot trigger probe failures.
    Json(json!({
        "ok": true,
        "version": env!("CARGO_PKG_VERSION"),
        "pdfium": state.pdfium_available,
        "gitEnabled": state.store.git_enabled(),
        "gitBranch": state.store.git_branch(),
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
    body: Body,
) -> Response {
    // Authenticate BEFORE reading or buffering any request body bytes.
    if !state.check_auth(&headers, q.token.as_deref()) {
        return err_response(StatusCode::UNAUTHORIZED, "unauthorized");
    }
    let store = Arc::clone(&state.store);
    let name = q.name.clone();
    let (norm, mut staged) =
        match tokio::task::spawn_blocking(move || store.start_staged_upload(&name)).await {
            Ok(Ok(pair)) => pair,
            Ok(Err(e)) => return err_response(StatusCode::BAD_REQUEST, format!("{e:#}")),
            Err(e) => return err_response(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()),
        };

    let mut stream = body.into_data_stream();
    while let Some(chunk_res) = stream.next().await {
        let chunk = match chunk_res {
            Ok(c) => c,
            Err(e) => {
                let msg = e.to_string();
                let status = if msg.contains("length limit exceeded") {
                    StatusCode::PAYLOAD_TOO_LARGE
                } else {
                    StatusCode::BAD_REQUEST
                };
                return err_response(status, msg);
            }
        };
        if chunk.is_empty() {
            continue;
        }
        staged = match tokio::task::spawn_blocking(move || -> Result<_> {
            staged.write_chunk(&chunk)?;
            Ok(staged)
        })
        .await
        {
            Ok(Ok(s)) => s,
            Ok(Err(e)) => {
                let msg = format!("{e:#}");
                let status = if msg.contains("exceeds 64 MiB") {
                    StatusCode::PAYLOAD_TOO_LARGE
                } else {
                    StatusCode::BAD_REQUEST
                };
                return err_response(status, msg);
            }
            Err(e) => return err_response(StatusCode::INTERNAL_SERVER_ERROR, e.to_string()),
        };
    }

    let store = Arc::clone(&state.store);
    let overwrite = q.overwrite;
    match tokio::task::spawn_blocking(move || store.commit_staged_upload(&norm, staged, overwrite))
        .await
    {
        Ok(Ok(entry)) => {
            state.sync_tracker.mark_dirty();
            (StatusCode::CREATED, Json(json!({"sheet": entry}))).into_response()
        }
        Ok(Err(e)) => {
            let msg = format!("{e:#}");
            let status = if msg.contains("already exists") {
                StatusCode::CONFLICT
            } else if msg.contains("exceeds 64 MiB") {
                StatusCode::PAYLOAD_TOO_LARGE
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
    // Reject sheet switches while a dialog or alert is active (via dispatch_job's
    // interaction_conflict_response) rather than implicitly cancelling in-progress
    // Acrobat code whose pre-modal edits or cancel callbacks could mutate state.
    state
        .dispatch_job(|job_id, gate, done| WorkerCommand::Open {
            job_id,
            gate,
            done,
            rel_path: req.path,
            force: req.force,
            discard: req.discard,
            expected_session: req.session,
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
                "serverInstanceId": state.server_instance_id,
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
                        "serverInstanceId": state.server_instance_id,
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
            expected_sheet: q.sheet,
            expected_session: q.session,
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
        Ok(Err(e)) => {
            let msg = format!("{e:#}");
            let status = if msg.contains("conflict") {
                StatusCode::CONFLICT
            } else {
                StatusCode::NOT_FOUND
            };
            err_response(status, msg)
        }
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
        .dispatch_job(|job_id, gate, done| WorkerCommand::Edit {
            job_id,
            gate,
            done,
            field: req.field,
            value: req.value,
            mode: req.mode,
            expected_sheet: req.sheet,
            expected_session: req.session,
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
        .dispatch_job(|job_id, gate, done| WorkerCommand::Activate {
            job_id,
            gate,
            done,
            field: req.field,
            index: req.index,
            shift: req.shift,
            modifier: req.modifier,
            expected_sheet: req.sheet,
            expected_session: req.session,
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
        .dispatch_job(|job_id, gate, done| WorkerCommand::InvokeMenu {
            job_id,
            gate,
            done,
            name: req.name,
            expected_sheet: req.sheet,
            expected_session: req.session,
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
        .dispatch_job(|job_id, gate, done| WorkerCommand::RunCommand {
            job_id,
            gate,
            done,
            action: req.action,
            expected_sheet: req.sheet,
            expected_session: req.session,
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
        .dispatch_job(|job_id, gate, done| WorkerCommand::RunBookmark {
            job_id,
            gate,
            done,
            path: req.path,
            expected_sheet: req.sheet,
            expected_session: req.session,
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
        .dispatch_job(|job_id, gate, done| WorkerCommand::SaveNow {
            job_id,
            gate,
            done,
            force: req.force,
            expected_sheet: req.sheet,
            expected_session: req.session,
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
            expected_sheet: q.sheet,
            expected_session: q.session,
            expected_rev: q.rev,
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
            let status = if msg.contains("conflict") {
                StatusCode::CONFLICT
            } else if msg.contains("PDFium") {
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
    Query(q): Query<PageWidgetsQuery>,
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
        .send(WorkerCommand::GetPageWidgets {
            page,
            expected_sheet: q.sheet,
            expected_session: q.session,
            expected_rev: q.rev,
            reply: tx,
        })
        .is_err()
    {
        return err_response(StatusCode::INTERNAL_SERVER_ERROR, "sheet worker stopped");
    }
    match state.await_sync_read(rx, "timed out reading widgets").await {
        Ok(Ok(v)) => ([(header::VARY, "Authorization")], Json(v)).into_response(),
        Ok(Err(e)) => {
            let msg = format!("{e:#}");
            let status = if msg.contains("conflict") {
                StatusCode::CONFLICT
            } else {
                StatusCode::BAD_REQUEST
            };
            err_response(status, msg)
        }
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
        .await_job_or_interaction(done_rx, &mut int_rx, job_id, None, Some(&id))
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
        .dispatch_job(|job_id, gate, done| WorkerCommand::GitSync {
            job_id,
            gate,
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
    let req = req.map(|Json(r)| r).unwrap_or_default();
    state
        .dispatch_job(|job_id, gate, done| WorkerCommand::GitPull {
            job_id,
            gate,
            done,
            force: req.force,
            discard: req.discard,
            expected_session: req.session,
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
        std::env::var("MPMB_SERVE_BIND").unwrap_or_else(|_| "127.0.0.1:8080".to_owned());
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
    let mut allow_unauthenticated = std::env::var("MPMB_ALLOW_UNAUTHENTICATED")
        .ok()
        .is_some_and(|v| matches!(v.trim().to_ascii_lowercase().as_str(), "1" | "true" | "yes"));
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
                       --bind <addr:port>          Listen address (MPMB_SERVE_BIND, default 127.0.0.1:8080)\n\
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
                       --auth-token <token>        Bearer/query token; required on non-loopback binds (MPMB_AUTH_TOKEN)\n\
                       --allow-unauthenticated     Explicitly allow non-loopback bind without auth token (MPMB_ALLOW_UNAUTHENTICATED=1)\n\
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
            "--allow-unauthenticated" => allow_unauthenticated = true,
            "--no-autosave" => autosave = false,
            other => bail!("unknown serve option: {other}"),
        }
        i += 1;
    }

    let bind: SocketAddr = bind_str
        .parse()
        .with_context(|| format!("invalid --bind address: {bind_str}"))?;
    let auth_token = auth_token.filter(|s| !s.trim().is_empty());
    validate_bind_auth(bind, auth_token.as_deref(), allow_unauthenticated)?;
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
        allow_unauthenticated,
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
        let poll_secs = idle.clamp(1, 15);
        tokio::spawn(async move {
            let mut ticker = tokio::time::interval(Duration::from_secs(poll_secs));
            loop {
                ticker.tick().await;
                if bridge.active_public().is_some() {
                    continue;
                }
                let job_id = job_seq.fetch_add(1, Ordering::SeqCst);
                let gate = JobGate::new();
                let (done_tx, done_rx) = watch::channel(None);
                bridge.register_job(job_id, done_rx);
                if tx
                    .send(WorkerCommand::CheckIdleAutoSync {
                        job_id,
                        gate,
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
            allow_unauthenticated: false,
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
            allow_unauthenticated: false,
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
    async fn switching_sheets_mid_cascading_dialog_requires_finishing_modal_first() {
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
        let step1_id = modal["interaction"]["id"].as_str().unwrap().to_owned();

        // Attempting to switch sheets while Step 1 is open returns 409 interaction_required
        // instead of implicitly cancelling in-progress Acrobat callbacks.
        let (open_blocked_st, open_blocked) =
            post_json(&app, "/api/session/open", json!({"path": "second.pdf"})).await;
        assert_eq!(open_blocked_st, StatusCode::CONFLICT);
        assert_eq!(open_blocked["status"], "interaction_required");
        assert_eq!(open_blocked["interaction"]["id"], step1_id);

        // Explicitly cancelling Step 1 advances to the cascading 'Confirm Cancel' alert.
        let (cancel1_st, cancel1) = post_json(
            &app,
            &format!("/api/session/interaction/{step1_id}"),
            json!({"result": "cancel", "values": {}}),
        )
        .await;
        assert_eq!(cancel1_st, StatusCode::ACCEPTED);
        assert_eq!(cancel1["interaction"]["kind"], "alert");
        let alert_id = cancel1["interaction"]["id"].as_str().unwrap().to_owned();

        // Sheet switch is still blocked while the cascading alert is active.
        let (open_blocked2_st, open_blocked2) =
            post_json(&app, "/api/session/open", json!({"path": "second.pdf"})).await;
        assert_eq!(open_blocked2_st, StatusCode::CONFLICT);
        assert_eq!(open_blocked2["interaction"]["id"], alert_id);

        // Answering the cascading alert completes the job, after which switching succeeds.
        let (alert_ok_st, _) = post_json(
            &app,
            &format!("/api/session/interaction/{alert_id}"),
            json!({"button": 4, "checked": false}),
        )
        .await;
        assert_eq!(alert_ok_st, StatusCode::OK);

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
        let corrupt_upload = app
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
        assert_eq!(corrupt_upload.status(), StatusCode::BAD_REQUEST);
        assert!(!base.join("sheets/corrupt.pdf").exists());
        // Simulate on-disk corruption written outside the upload endpoint.
        std::fs::write(
            base.join("sheets/corrupt.pdf"),
            b"%PDF-1.7\nthis-is-corrupt-garbage",
        )
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
            allow_unauthenticated: false,
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

        // 3. Valid edit with --no-autosave marks sheet dirty; switching without force returns 409
        //    with a structured discardTarget.
        let (st, _) = post_json(
            &app,
            "/api/session/edit",
            json!({"field": "PC Name", "value": "UnsavedHero", "sheet": "probe.pdf"}),
        )
        .await;
        assert_eq!(st, StatusCode::OK);
        let (st, conflict) =
            post_json(&app, "/api/session/open", json!({"path": "other.pdf"})).await;
        assert_eq!(st, StatusCode::CONFLICT);
        let discard_target = conflict["discardTarget"].clone();
        assert_eq!(discard_target["sheet"], "probe.pdf");

        // 4. Switching with force=true and matching discardTarget succeeds.
        let (st, switched) = post_json(
            &app,
            "/api/session/open",
            json!({"path": "other.pdf", "force": true, "discard": discard_target}),
        )
        .await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(switched["state"]["path"], "other.pdf");

        let _ = std::fs::remove_dir_all(&base);
    }

    #[tokio::test]
    async fn server_round2_livez_auth_upload_readiness_menu_throw_and_cancelled_queued_job() {
        let base = std::env::temp_dir().join(format!("mpmb-serve-round2-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&base);
        let store_dir = base.join("store");
        std::fs::create_dir_all(&store_dir).unwrap();

        // Build a PDF with:
        // - PC Name field
        // - a menu item "MutateThenThrow" that mutates PC Name and throws
        // - a menu item "SlowPrompt" that spins briefly before opening an alert
        let build_scripted_pdf = |out_path: &std::path::Path, js: &str| {
            use lopdf::{dictionary, Object, StringFormat};
            let mut doc = lopdf::Document::with_version("1.7");
            let pages_id = doc.new_object_id();
            let field_id = doc.add_object(dictionary! {
                "Type" => "Annot",
                "Subtype" => "Widget",
                "FT" => "Tx",
                "T" => Object::String(b"PC Name".to_vec(), StringFormat::Literal),
                "V" => Object::String(b"Initial".to_vec(), StringFormat::Literal),
                "Rect" => vec![10.into(), 10.into(), 200.into(), 40.into()],
            });
            let page_id = doc.add_object(dictionary! {
                "Type" => "Page",
                "Parent" => pages_id,
                "MediaBox" => vec![0.into(), 0.into(), 612.into(), 792.into()],
                "Annots" => vec![field_id.into()],
            });
            doc.objects.insert(
                pages_id,
                Object::Dictionary(dictionary! {
                    "Type" => "Pages",
                    "Kids" => vec![page_id.into()],
                    "Count" => 1,
                }),
            );
            let form_id = doc.add_object(dictionary! {
                "Fields" => vec![field_id.into()],
            });
            let js_action = doc.add_object(dictionary! {
                "S" => "JavaScript",
                "JS" => Object::String(js.as_bytes().to_vec(), StringFormat::Literal),
            });
            let js_tree = doc.add_object(dictionary! {
                "Names" => vec![
                    Object::String(b"Init".to_vec(), StringFormat::Literal),
                    js_action.into(),
                ],
            });
            let names_id = doc.add_object(dictionary! {
                "JavaScript" => js_tree,
            });
            let cat_id = doc.add_object(dictionary! {
                "Type" => "Catalog",
                "Pages" => pages_id,
                "AcroForm" => form_id,
                "Names" => names_id,
            });
            doc.trailer.set("Root", cat_id);
            let mut bytes = Vec::new();
            doc.save_to(&mut bytes).unwrap();
            std::fs::write(out_path, bytes).unwrap();
        };

        build_scripted_pdf(
            &store_dir.join("good.pdf"),
            r#"
                app.addMenuItem({
                    cName: "MutateThenThrow",
                    cUser: "Mutate Then Throw",
                    cParent: "Edit",
                    cExec: "getField('PC Name').value = 'MutatedBeforeThrow'; throw new Error('boom');"
                });
                app.addMenuItem({
                    cName: "DelayedAlert",
                    cUser: "Delayed Alert",
                    cParent: "Edit",
                    cExec: "var t = Date.now(); while (Date.now() - t < 300) {} app.alert({cTitle:'Pause', cMsg:'Wait', nType:0, nIcon:0}); getField('PC Name').value = 'AfterAlert';"
                });
            "#,
        );
        // Startup leaves `delay = true` with no resumable timer -> Runtime::ready() fails!
        build_scripted_pdf(&store_dir.join("stuck-ready.pdf"), "this.delay = true;");
        // Startup infinite loop -> server script_timeout interrupts it without wedging worker!
        build_scripted_pdf(
            &store_dir.join("infinite-loop.pdf"),
            "try { while (true) {} } catch (e) {}",
        );
        make_interactive_test_pdf(&store_dir.join("second.pdf"));

        let state = AppState::start_with_capabilities(
            &ServeConfig {
                bind: "127.0.0.1:0".parse().unwrap(),
                store: StoreConfig {
                    root: store_dir.clone(),
                    git: None,
                },
                default_sheet: None,
                auth_token: Some("tok-r2".into()),
                allow_unauthenticated: false,
                autosave: false,
                git_auto_sync_secs: 0,
            },
            HostCapabilities::server_restricted()
                .with_script_timeout(Some(Duration::from_millis(600))),
        )
        .unwrap();
        let state_handle = state.clone();
        let app = build_router(state);

        // 1. /livez and /healthz respond 200 OK without auth.
        for path in ["/livez", "/healthz"] {
            let resp = app
                .clone()
                .oneshot(Request::builder().uri(path).body(Body::empty()).unwrap())
                .await
                .unwrap();
            assert_eq!(resp.status(), StatusCode::OK, "{path} should return 200");
        }

        // 2. Unauthenticated upload returns 401 BEFORE reading/staging body.
        let unauth_up = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/api/sheets/upload?name=unauth.pdf")
                    .body(Body::from(b"%PDF-1.7\n%should-not-write\n".to_vec()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(unauth_up.status(), StatusCode::UNAUTHORIZED);
        assert!(!store_dir.join("unauth.pdf").exists());

        // Helper with auth header.
        let authed_post = |app: Router, uri: &'static str, body: Value| async move {
            let resp = app
                .oneshot(
                    Request::builder()
                        .method("POST")
                        .uri(uri)
                        .header("authorization", "Bearer tok-r2")
                        .header("content-type", "application/json")
                        .body(Body::from(body.to_string()))
                        .unwrap(),
                )
                .await
                .unwrap();
            let status = resp.status();
            let bytes = axum::body::to_bytes(resp.into_body(), 4 * 1024 * 1024)
                .await
                .unwrap();
            let json: Value = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
            (status, json)
        };

        // 3. Open good.pdf, then attempt to open stuck-ready.pdf -> rejected, keeping good.pdf active!
        let (st, opened) = authed_post(
            app.clone(),
            "/api/session/open",
            json!({"path": "good.pdf"}),
        )
        .await;
        assert_eq!(st, StatusCode::OK);
        let seq1 = opened["state"]["stateSeq"].as_u64().unwrap();
        let (st, _) = authed_post(
            app.clone(),
            "/api/session/open",
            json!({"path": "stuck-ready.pdf"}),
        )
        .await;
        assert_eq!(st, StatusCode::BAD_REQUEST);
        let state_resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/api/session/state")
                    .header("authorization", "Bearer tok-r2")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        let state_json: Value = serde_json::from_slice(
            &axum::body::to_bytes(state_resp.into_body(), 1024 * 1024)
                .await
                .unwrap(),
        )
        .unwrap();
        assert_eq!(state_json["path"], "good.pdf");
        assert!(state_json["stateSeq"].as_u64().unwrap() > seq1);

        // 4. Menu item that mutates PC Name and then throws STILL marks dirty_since_save=true,
        //    so a non-force switch returns 409 Conflict instead of silently losing the edit!
        let (st, _) = authed_post(
            app.clone(),
            "/api/session/menu",
            json!({"name": "MutateThenThrow", "sheet": "good.pdf"}),
        )
        .await;
        assert_eq!(st, StatusCode::BAD_REQUEST);
        let (st, _) = authed_post(
            app.clone(),
            "/api/session/open",
            json!({"path": "second.pdf"}),
        )
        .await;
        assert_eq!(st, StatusCode::CONFLICT);

        // Save to clear dirty flag before testing queued-job cancellation.
        let (st, _) = authed_post(
            app.clone(),
            "/api/session/save",
            json!({"sheet": "good.pdf"}),
        )
        .await;
        assert_eq!(st, StatusCode::OK);

        // 5. Queue Job B (edit PC Name -> 'GhostQueuedEdit') deterministically BEFORE Job A opens its alert.
        //    Job B must receive 409 Conflict AND must NOT execute after Job A's alert is answered!
        let prev_job = state_handle.bridge.current_job.load(Ordering::SeqCst);
        let app_a = app.clone();
        let job_a = tokio::spawn(async move {
            authed_post(
                app_a,
                "/api/session/menu",
                json!({"name": "DelayedAlert", "sheet": "good.pdf"}),
            )
            .await
        });
        // Synchronize until Job A has entered the worker loop and started its spin
        // while no interaction is active yet.
        for _ in 0..500 {
            if state_handle.bridge.current_job.load(Ordering::SeqCst) != prev_job {
                break;
            }
            tokio::time::sleep(Duration::from_millis(2)).await;
        }
        assert_ne!(
            state_handle.bridge.current_job.load(Ordering::SeqCst),
            prev_job,
            "Job A should have entered the worker"
        );
        assert!(
            state_handle.bridge.active_public().is_none(),
            "Job B must queue BEFORE Job A opens its alert"
        );
        let app_b = app.clone();
        let job_b = tokio::spawn(async move {
            authed_post(
                app_b,
                "/api/session/edit",
                json!({"field": "PC Name", "value": "GhostQueuedEdit", "sheet": "good.pdf"}),
            )
            .await
        });
        // Wait until Job B is actually registered in flight while alert is still not open,
        // failing explicitly if the observation loop times out.
        let mut observed_queued = false;
        for _ in 0..500 {
            if state_handle.bridge.in_flight_jobs.lock().unwrap().len() >= 2 {
                observed_queued = true;
                break;
            }
            tokio::time::sleep(Duration::from_millis(2)).await;
        }
        assert!(
            observed_queued,
            "timed out waiting to observe Job B queued in flight"
        );
        assert!(
            state_handle.bridge.active_public().is_none(),
            "Job B must have queued while Job A's alert was still unopened"
        );

        let (st_a, body_a) = job_a.await.unwrap();
        assert_eq!(st_a, StatusCode::ACCEPTED);
        let inter_id = body_a["interaction"]["id"].as_str().unwrap().to_owned();

        let (st_b, _) = job_b.await.unwrap();
        assert_eq!(st_b, StatusCode::CONFLICT);

        // Answer Job A's alert.
        let reply_uri = format!("/api/session/interaction/{inter_id}");
        let reply_resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri(&reply_uri)
                    .header("authorization", "Bearer tok-r2")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        json!({"button": 1, "checked": false}).to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(reply_resp.status(), StatusCode::OK);

        // Issue a fresh GET /api/session/state (queued AFTER Job B in the worker channel)
        // to prove the worker passed and skipped cancelled Job B without mutating state.
        let post_state_resp = app
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/api/session/state")
                    .header("authorization", "Bearer tok-r2")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(post_state_resp.status(), StatusCode::OK);
        let post_state: Value = serde_json::from_slice(
            &axum::body::to_bytes(post_state_resp.into_body(), 1024 * 1024)
                .await
                .unwrap(),
        )
        .unwrap();
        assert_eq!(
            post_state["character"]["name"], "AfterAlert",
            "cancelled queued Job B must never execute after Job A finishes"
        );

        // 6. Startup infinite-loop PDF times out cleanly without wedging the server worker,
        //    and the SAME worker immediately opens a normal sheet afterward.
        let discard_good = json!({
            "sheet": post_state["path"],
            "sessionId": post_state["sessionId"],
            "revision": post_state["revision"],
        });
        let started = Instant::now();
        let (st_loop, body_loop) = authed_post(
            app.clone(),
            "/api/session/open",
            json!({"path": "infinite-loop.pdf", "force": true, "discard": discard_good}),
        )
        .await;
        assert_eq!(st_loop, StatusCode::BAD_REQUEST);
        assert!(
            body_loop["error"]
                .as_str()
                .unwrap_or("")
                .contains("timed out"),
            "unexpected timeout payload: {body_loop}"
        );
        assert!(
            started.elapsed() < Duration::from_secs(5),
            "infinite-loop open hung past script timeout"
        );
        let (st_ok, body_ok) = authed_post(
            app.clone(),
            "/api/session/open",
            json!({"path": "second.pdf", "force": true, "discard": discard_good}),
        )
        .await;
        assert_eq!(st_ok, StatusCode::OK);
        assert_eq!(body_ok["state"]["path"], "second.pdf");

        let _ = std::fs::remove_dir_all(&base);
    }

    fn make_scripted_hp_pdf(
        path: &std::path::Path,
        hp: &str,
        init_js: &str,
        button_js: Option<&str>,
    ) {
        let mut doc = lopdf::Document::with_version("1.7");
        let pages_id = doc.new_object_id();
        let page_id = doc.new_object_id();
        let f_name = doc.add_object(dictionary! {
            "Type" => "Annot",
            "Subtype" => "Widget",
            "FT" => "Tx",
            "T" => Object::String(b"PC Name".to_vec(), StringFormat::Literal),
            "V" => Object::String(b"Baseline Hero".to_vec(), StringFormat::Literal),
            "Rect" => vec![40.into(), 740.into(), 240.into(), 764.into()],
            "P" => page_id,
        });
        let f_hp = doc.add_object(dictionary! {
            "Type" => "Annot",
            "Subtype" => "Widget",
            "FT" => "Tx",
            "T" => Object::String(b"HP Current".to_vec(), StringFormat::Literal),
            "V" => Object::String(hp.as_bytes().to_vec(), StringFormat::Literal),
            "Rect" => vec![40.into(), 700.into(), 240.into(), 724.into()],
            "P" => page_id,
        });
        let mut annots: Vec<Object> = vec![f_name.into(), f_hp.into()];
        let mut fields: Vec<Object> = vec![f_name.into(), f_hp.into()];
        if let Some(bjs) = button_js {
            let btn_action = doc.add_object(dictionary! {
                "S" => "JavaScript",
                "JS" => Object::String(bjs.as_bytes().to_vec(), StringFormat::Literal),
            });
            let f_btn = doc.add_object(dictionary! {
                "Type" => "Annot",
                "Subtype" => "Widget",
                "FT" => "Btn",
                "Ff" => 65536,
                "T" => Object::String(b"ActionButton".to_vec(), StringFormat::Literal),
                "AA" => dictionary! { "U" => btn_action },
                "Rect" => vec![260.into(), 700.into(), 360.into(), 724.into()],
                "P" => page_id,
            });
            annots.push(f_btn.into());
            fields.push(f_btn.into());
        }
        doc.objects.insert(
            page_id,
            Object::Dictionary(dictionary! {
                "Type" => "Page",
                "Parent" => pages_id,
                "MediaBox" => vec![0.into(), 0.into(), 612.into(), 792.into()],
                "Annots" => annots,
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
        let form_id = doc.add_object(dictionary! { "Fields" => fields });
        let mut catalog = dictionary! {
            "Type" => "Catalog",
            "Pages" => pages_id,
            "AcroForm" => form_id,
        };
        if !init_js.is_empty() {
            let js_action = doc.add_object(dictionary! {
                "S" => "JavaScript",
                "JS" => Object::String(init_js.as_bytes().to_vec(), StringFormat::Literal),
            });
            let js_tree = doc.add_object(dictionary! {
                "Names" => vec![
                    Object::String(b"Init".to_vec(), StringFormat::Literal),
                    js_action.into(),
                ],
            });
            let names_id = doc.add_object(dictionary! { "JavaScript" => js_tree });
            catalog.set("Names", names_id);
        }
        let catalog_id = doc.add_object(catalog);
        doc.trailer.set("Root", catalog_id);
        doc.save(path).unwrap();
    }

    #[test]
    fn parse_args_and_startup_fail_closed_on_non_loopback_without_auth() {
        // Explicit loopback default succeeds without auth token.
        let loopback = parse_args(&["--bind".into(), "127.0.0.1:8080".into()])
            .unwrap()
            .unwrap();
        assert!(loopback.bind.ip().is_loopback());
        assert!(!loopback.allow_unauthenticated);

        let ipv6_loopback = parse_args(&["--bind".into(), "[::1]:8080".into()])
            .unwrap()
            .unwrap();
        assert!(ipv6_loopback.bind.ip().is_loopback());

        // Non-loopback without auth token or opt-in fails closed.
        assert!(validate_bind_auth("0.0.0.0:8080".parse().unwrap(), None, false).is_err());
        assert!(validate_bind_auth("0.0.0.0:8080".parse().unwrap(), Some("   "), false).is_err());
        assert!(validate_bind_auth("[::]:8080".parse().unwrap(), None, false).is_err());

        // Non-loopback succeeds with auth token or explicit opt-in.
        assert!(validate_bind_auth("0.0.0.0:8080".parse().unwrap(), Some("secret"), false).is_ok());
        assert!(validate_bind_auth("0.0.0.0:8080".parse().unwrap(), None, true).is_ok());

        let with_token = parse_args(&[
            "--bind".into(),
            "0.0.0.0:8080".into(),
            "--auth-token".into(),
            "tok-123".into(),
        ])
        .unwrap()
        .unwrap();
        assert_eq!(with_token.auth_token.as_deref(), Some("tok-123"));

        let with_opt_in = parse_args(&[
            "--bind".into(),
            "0.0.0.0:8080".into(),
            "--allow-unauthenticated".into(),
        ])
        .unwrap()
        .unwrap();
        assert!(with_opt_in.allow_unauthenticated);

        // AppState::start enforces the same invariant directly.
        let err = AppState::start(&ServeConfig {
            bind: "0.0.0.0:8080".parse().unwrap(),
            store: StoreConfig {
                root: std::env::temp_dir().join("mpmb-serve-nonloopback-unused"),
                git: None,
            },
            default_sheet: None,
            auth_token: None,
            allow_unauthenticated: false,
            autosave: true,
            git_auto_sync_secs: 0,
        })
        .err()
        .expect("non-loopback AppState::start without auth must fail");
        assert!(format!("{err:#}").contains("refusing to bind non-loopback"));
    }

    #[tokio::test]
    async fn idle_timers_advance_and_deliver_mutations_and_modals() {
        let (base, _, app) = setup_test_app("idle-timers", false);
        let sheet_path = base.join("sheets/timer.pdf");
        std::fs::create_dir_all(sheet_path.parent().unwrap()).unwrap();
        make_scripted_hp_pdf(
            &sheet_path,
            "10",
            r#"
                app.addMenuItem({
                    cName: "DeferredAlert",
                    cUser: "Deferred Alert",
                    cParent: "Edit",
                    cExec: "app.setTimeOut(\"app.alert({cTitle:'TimerAlert',cMsg:'Fired',nType:0});getField('HP Current').value='19';\", 100);"
                });
            "#,
            Some("app.setTimeOut(\"getField('HP Current').value='13';\", 100);"),
        );

        let (st, opened) = post_json(&app, "/api/session/open", json!({"path": "timer.pdf"})).await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(opened["state"]["vitals"]["hpCurrent"], "10");

        // 1. Activate button that schedules a 100ms timer mutating HP Current -> 13.
        let (st, _) = post_json(
            &app,
            "/api/session/activate",
            json!({"field": "ActionButton", "index": 0, "sheet": "timer.pdf"}),
        )
        .await;
        assert_eq!(st, StatusCode::OK);

        let mut observed_13 = false;
        for _ in 0..30 {
            tokio::time::sleep(Duration::from_millis(75)).await;
            let (st, state) = get_json(&app, "/api/session/state").await;
            assert_eq!(st, StatusCode::OK);
            if state["vitals"]["hpCurrent"] == "13" {
                observed_13 = true;
                break;
            }
        }
        assert!(
            observed_13,
            "100ms deferred Acrobat timer should have fired while worker was idle"
        );

        // Verify the timer-driven mutation was autosaved to disk by reopening.
        let (st, reopened) =
            post_json(&app, "/api/session/open", json!({"path": "timer.pdf"})).await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(reopened["state"]["vitals"]["hpCurrent"], "13");

        // 2. Schedule a deferred alert via menu, wait for it to pause on InteractionBridge,
        //    answer it, and confirm the post-alert mutation completes.
        let (st, _) = post_json(
            &app,
            "/api/session/menu",
            json!({"name": "DeferredAlert", "sheet": "timer.pdf"}),
        )
        .await;
        assert_eq!(st, StatusCode::OK);

        let mut alert_id = None;
        for _ in 0..30 {
            tokio::time::sleep(Duration::from_millis(75)).await;
            let (st, state) = get_json(&app, "/api/session/state").await;
            assert_eq!(st, StatusCode::OK);
            if state["busy"] == true {
                if let Some(id) = state["activeInteraction"]["id"].as_str() {
                    alert_id = Some(id.to_owned());
                    break;
                }
            }
        }
        let alert_id = alert_id.expect("deferred timer alert should have surfaced via bridge");
        let (st, reply) = post_json(
            &app,
            &format!("/api/session/interaction/{alert_id}"),
            json!({"button": 1, "checked": false}),
        )
        .await;
        assert_eq!(st, StatusCode::OK, "reply failed: {reply}");
        assert_eq!(reply["state"]["vitals"]["hpCurrent"], "19");

        let _ = std::fs::remove_dir_all(&base);
    }

    #[tokio::test]
    async fn failed_commands_and_actions_reconcile_partial_mutations_with_autosave_on_and_off() {
        for autosave in [false, true] {
            let nanos = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let base = std::env::temp_dir().join(format!(
                "mpmb-serve-partial-{autosave}-{}-{nanos}",
                std::process::id()
            ));
            let store_dir = base.join("sheets");
            std::fs::create_dir_all(&store_dir).unwrap();
            make_scripted_hp_pdf(
                &store_dir.join("partial.pdf"),
                "10",
                r#"
                    function GenerateSpellSheet() {
                        getField('HP Current').value = '17';
                        throw new Error('simulated spell sheet failure');
                    }
                "#,
                Some("getField('HP Current').value = '15'; throw new Error('button boom');"),
            );
            make_scripted_hp_pdf(&store_dir.join("other.pdf"), "20", "", None);

            let state = AppState::start(&ServeConfig {
                bind: "127.0.0.1:0".parse().unwrap(),
                store: StoreConfig {
                    root: store_dir.clone(),
                    git: None,
                },
                default_sheet: None,
                auth_token: None,
                allow_unauthenticated: false,
                autosave,
                git_auto_sync_secs: 0,
            })
            .unwrap();
            let app = build_router(state);

            let (st, opened) =
                post_json(&app, "/api/session/open", json!({"path": "partial.pdf"})).await;
            assert_eq!(st, StatusCode::OK);
            let rev0 = opened["state"]["revision"].as_u64().unwrap();

            // Failing button action mutates HP -> 15 before throwing.
            let (st, _) = post_json(
                &app,
                "/api/session/activate",
                json!({"field": "ActionButton", "index": 0, "sheet": "partial.pdf"}),
            )
            .await;
            assert_eq!(st, StatusCode::BAD_REQUEST);
            let (st, after_btn) = get_json(&app, "/api/session/state").await;
            assert_eq!(st, StatusCode::OK);
            assert_eq!(after_btn["vitals"]["hpCurrent"], "15");
            assert!(after_btn["revision"].as_u64().unwrap() > rev0);

            // Failing run_command(spell_sheet) mutates HP -> 17 before throwing.
            let (st, _) = post_json(
                &app,
                "/api/session/command",
                json!({"action": "spell_sheet", "sheet": "partial.pdf"}),
            )
            .await;
            assert_eq!(st, StatusCode::BAD_REQUEST);
            let (st, after_cmd) = get_json(&app, "/api/session/state").await;
            assert_eq!(st, StatusCode::OK);
            assert_eq!(after_cmd["vitals"]["hpCurrent"], "17");

            if autosave {
                assert_eq!(after_cmd["dirtySinceSave"], false);
                // Reopen from disk proves autosave persisted the partial mutation!
                let (st, reopened) =
                    post_json(&app, "/api/session/open", json!({"path": "partial.pdf"})).await;
                assert_eq!(st, StatusCode::OK);
                assert_eq!(reopened["state"]["vitals"]["hpCurrent"], "17");
            } else {
                assert_eq!(after_cmd["dirtySinceSave"], true);
                // Switching sheets without force MUST return 409 instead of silently dropping partial edits.
                let (st, _) =
                    post_json(&app, "/api/session/open", json!({"path": "other.pdf"})).await;
                assert_eq!(st, StatusCode::CONFLICT);
                // Explicit save persists the partial mutation cleanly.
                let (st, _) =
                    post_json(&app, "/api/session/save", json!({"sheet": "partial.pdf"})).await;
                assert_eq!(st, StatusCode::OK);
                let (st, reopened) =
                    post_json(&app, "/api/session/open", json!({"path": "partial.pdf"})).await;
                assert_eq!(st, StatusCode::OK);
                assert_eq!(reopened["state"]["vitals"]["hpCurrent"], "17");
            }

            let _ = std::fs::remove_dir_all(&base);
        }
    }

    #[tokio::test]
    async fn session_id_and_page_target_guards_prevent_cross_sheet_and_stale_cache_mixups() {
        let (base, _, app) = setup_test_app("session-page-guards", false);
        let store_dir = base.join("sheets");
        std::fs::create_dir_all(&store_dir).unwrap();
        make_scripted_hp_pdf(&store_dir.join("alpha.pdf"), "10", "", Some(""));
        make_scripted_hp_pdf(&store_dir.join("beta.pdf"), "20", "", None);

        let (st, a1) = post_json(&app, "/api/session/open", json!({"path": "alpha.pdf"})).await;
        assert_eq!(st, StatusCode::OK);
        let srv1 = a1["state"]["serverInstanceId"].as_str().unwrap().to_owned();
        let sess_a1 = a1["state"]["sessionId"].as_str().unwrap().to_owned();
        let rev_a1 = a1["state"]["revision"].as_u64().unwrap();
        assert!(!srv1.is_empty());
        assert!(!sess_a1.is_empty());

        // Reopening the SAME path mints a fresh sessionId so edits/field reads
        // bound to the prior session are rejected with 409 Conflict.
        let (st, a2) = post_json(&app, "/api/session/open", json!({"path": "alpha.pdf"})).await;
        assert_eq!(st, StatusCode::OK);
        let sess_a2 = a2["state"]["sessionId"].as_str().unwrap().to_owned();
        assert_ne!(sess_a1, sess_a2);

        let (st, _) = post_json(
            &app,
            "/api/session/edit",
            json!({"field": "HP Current", "value": "99", "sheet": "alpha.pdf", "session": sess_a1}),
        )
        .await;
        assert_eq!(st, StatusCode::CONFLICT);
        let (st, _) = get_json(
            &app,
            &format!("/api/session/field?name=HP%20Current&sheet=alpha.pdf&session={sess_a1}"),
        )
        .await;
        assert_eq!(st, StatusCode::CONFLICT);

        // Switch to beta.pdf.
        let (st, b1) = post_json(&app, "/api/session/open", json!({"path": "beta.pdf"})).await;
        assert_eq!(st, StatusCode::OK);
        let sess_b1 = b1["state"]["sessionId"].as_str().unwrap().to_owned();
        let rev_b1 = b1["state"]["revision"].as_u64().unwrap();

        // Alpha-keyed page widget and page image requests MUST return 409 Conflict,
        // never 200 with Beta's content!
        let (st, _) = get_json(
            &app,
            &format!("/api/session/page/0/widgets?sheet=alpha.pdf&rev={rev_a1}&session={sess_a2}"),
        )
        .await;
        assert_eq!(st, StatusCode::CONFLICT);
        let (st, _) = get_json(
            &app,
            &format!("/api/session/page/0/image?w=640&sheet=alpha.pdf&rev={rev_a1}"),
        )
        .await;
        assert_eq!(st, StatusCode::CONFLICT);
        // Revision mismatch on beta.pdf also returns 409 Conflict.
        let (st, _) = get_json(
            &app,
            &format!(
                "/api/session/page/0/widgets?sheet=beta.pdf&rev={}&session={sess_b1}",
                rev_b1 + 42
            ),
        )
        .await;
        assert_eq!(st, StatusCode::CONFLICT);

        // Matching beta.pdf target returns 200 with sheet & sessionId metadata.
        let (st, widgets) = get_json(
            &app,
            &format!("/api/session/page/0/widgets?sheet=beta.pdf&rev={rev_b1}&session={sess_b1}"),
        )
        .await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(widgets["sheet"], "beta.pdf");
        assert_eq!(widgets["sessionId"], sess_b1);

        // A second server instance gets a distinct serverInstanceId.
        let (_, _, app2) = setup_test_app("session-page-guards-2", false);
        let (st, s2) = get_json(&app2, "/api/session/state").await;
        assert_eq!(st, StatusCode::OK);
        assert_ne!(s2["serverInstanceId"].as_str().unwrap(), srv1);

        let _ = std::fs::remove_dir_all(&base);
    }

    #[tokio::test]
    async fn idle_git_autosync_pushes_prior_sheet_edits_after_switching_to_clean_sheet() {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let base = std::env::temp_dir().join(format!(
            "mpmb-serve-autosync-switch-{}-{nanos}",
            std::process::id()
        ));
        let bare = base.join("remote.git");
        let data_dir = base.join("sheets");
        std::fs::create_dir_all(&bare).unwrap();
        assert!(Command::new("git")
            .args(["init", "--bare", "-b", "main"])
            .arg(&bare)
            .status()
            .unwrap()
            .success());

        let state = AppState::start(&ServeConfig {
            bind: "127.0.0.1:0".parse().unwrap(),
            store: StoreConfig {
                root: data_dir.clone(),
                git: Some(GitConfig::new(bare.to_string_lossy().into_owned())),
            },
            default_sheet: None,
            auth_token: None,
            allow_unauthenticated: false,
            autosave: true,
            git_auto_sync_secs: 1,
        })
        .unwrap();
        make_scripted_hp_pdf(&data_dir.join("alpha.pdf"), "10", "", None);
        make_scripted_hp_pdf(&data_dir.join("beta.pdf"), "20", "", None);
        let app = build_router(state.clone());

        // Baseline sync.
        let (st, _) = post_json(&app, "/api/git/sync", json!({"message": "baseline"})).await;
        assert_eq!(st, StatusCode::OK);
        let git_rev = |dir: &std::path::Path| -> String {
            let mut cmd = Command::new("git");
            for key in [
                "GIT_DIR",
                "GIT_WORK_TREE",
                "GIT_INDEX_FILE",
                "GIT_COMMON_DIR",
                "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            ] {
                cmd.env_remove(key);
            }
            let out = cmd
                .current_dir(dir)
                .args(["rev-parse", "refs/heads/main"])
                .output()
                .unwrap();
            assert!(out.status.success());
            String::from_utf8_lossy(&out.stdout).trim().to_owned()
        };
        let base_sha = git_rev(&bare);

        // Edit alpha.pdf, then switch to clean beta.pdf.
        assert_eq!(
            post_json(&app, "/api/session/open", json!({"path": "alpha.pdf"}))
                .await
                .0,
            StatusCode::OK
        );
        assert_eq!(
            post_json(
                &app,
                "/api/session/edit",
                json!({"field": "HP Current", "value": "17", "sheet": "alpha.pdf"}),
            )
            .await
            .0,
            StatusCode::OK
        );
        let (st, beta_opened) =
            post_json(&app, "/api/session/open", json!({"path": "beta.pdf"})).await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(
            beta_opened["state"]["dirtySinceSync"], true,
            "switching to a clean sheet must preserve store-level dirtySinceSync"
        );

        // Wait past the 1s idle threshold and trigger CheckIdleAutoSync.
        tokio::time::sleep(Duration::from_millis(1150)).await;
        let res = state
            .dispatch_job(|job_id, gate, done| WorkerCommand::CheckIdleAutoSync {
                job_id,
                gate,
                done,
                idle_secs: 1,
            })
            .await;
        assert_eq!(res.status(), StatusCode::OK);
        let body = json_body(res).await;
        assert_eq!(body["sync"]["status"], "synced");
        assert_eq!(body["sync"]["pushed"], true);
        assert_ne!(
            git_rev(&bare),
            base_sha,
            "idle autosync must advance remote main"
        );
        assert_eq!(body["state"]["dirtySinceSync"], false);

        let _ = std::fs::remove_dir_all(&base);
    }

    #[tokio::test]
    async fn stale_discard_confirmation_is_rejected_on_open_and_git_pull() {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let base = std::env::temp_dir().join(format!(
            "mpmb-serve-discard-guard-{}-{nanos}",
            std::process::id()
        ));
        let bare = base.join("remote.git");
        let data_dir = base.join("sheets");
        std::fs::create_dir_all(&bare).unwrap();
        assert!(Command::new("git")
            .args(["init", "--bare", "-b", "main"])
            .arg(&bare)
            .status()
            .unwrap()
            .success());

        let state = AppState::start(&ServeConfig {
            bind: "127.0.0.1:0".parse().unwrap(),
            store: StoreConfig {
                root: data_dir.clone(),
                git: Some(GitConfig::new(bare.to_string_lossy().into_owned())),
            },
            default_sheet: None,
            auth_token: None,
            allow_unauthenticated: false,
            autosave: false,
            git_auto_sync_secs: 0,
        })
        .unwrap();
        make_scripted_hp_pdf(&data_dir.join("alpha.pdf"), "10", "", None);
        make_scripted_hp_pdf(&data_dir.join("beta.pdf"), "20", "", None);
        let app = build_router(state);

        assert_eq!(
            post_json(&app, "/api/git/sync", json!({"message": "baseline"}))
                .await
                .0,
            StatusCode::OK
        );

        // Open Alpha and make unsaved edit HP 10 -> 11.
        let (st, a_open) = post_json(&app, "/api/session/open", json!({"path": "alpha.pdf"})).await;
        assert_eq!(st, StatusCode::OK);
        let alpha_session = a_open["state"]["sessionId"].as_str().unwrap().to_owned();
        let (st, _) = post_json(
            &app,
            "/api/session/edit",
            json!({"field": "HP Current", "value": "11", "sheet": "alpha.pdf", "session": alpha_session}),
        )
        .await;
        assert_eq!(st, StatusCode::OK);

        // Non-force switch returns 409 with structured discardTarget naming Alpha & rev.
        let (st, conflict1) =
            post_json(&app, "/api/session/open", json!({"path": "beta.pdf"})).await;
        assert_eq!(st, StatusCode::CONFLICT);
        assert_eq!(conflict1["code"], "unsaved_edits");
        let alpha_target_v1 = conflict1["discardTarget"].clone();
        assert_eq!(alpha_target_v1["sheet"], "alpha.pdf");
        assert_eq!(alpha_target_v1["sessionId"], alpha_session);

        // 1. Intervening edit within the SAME session invalidates the earlier confirmation!
        let (st, _) = post_json(
            &app,
            "/api/session/edit",
            json!({"field": "HP Current", "value": "12", "sheet": "alpha.pdf", "session": alpha_session}),
        )
        .await;
        assert_eq!(st, StatusCode::OK);
        let (st, stale_same_sess) = post_json(
            &app,
            "/api/session/open",
            json!({"path": "beta.pdf", "force": true, "discard": alpha_target_v1}),
        )
        .await;
        assert_eq!(st, StatusCode::CONFLICT);
        assert_eq!(stale_same_sess["code"], "discard_target_stale");
        let alpha_target_v2 = stale_same_sess["discardTarget"].clone();
        assert_ne!(alpha_target_v2["revision"], alpha_target_v1["revision"]);

        // 2. Force open without discardTarget is also rejected while dirty.
        let (st, missing_target) = post_json(
            &app,
            "/api/session/open",
            json!({"path": "beta.pdf", "force": true}),
        )
        .await;
        assert_eq!(st, StatusCode::CONFLICT);
        assert_eq!(missing_target["code"], "discard_target_required");

        // 3. Matching discardTarget lets Client 2 switch to Beta and edit HP 20 -> 21.
        let (st, beta_open) = post_json(
            &app,
            "/api/session/open",
            json!({"path": "beta.pdf", "force": true, "discard": alpha_target_v2}),
        )
        .await;
        assert_eq!(st, StatusCode::OK);
        let beta_session = beta_open["state"]["sessionId"].as_str().unwrap().to_owned();
        let (st, _) = post_json(
            &app,
            "/api/session/edit",
            json!({"field": "HP Current", "value": "21", "sheet": "beta.pdf", "session": beta_session}),
        )
        .await;
        assert_eq!(st, StatusCode::OK);

        // 4. Client 1's now-stale confirmation (from Alpha) MUST NOT discard Beta's unsaved HP 21!
        let (st, stale_cross) = post_json(
            &app,
            "/api/session/open",
            json!({"path": "alpha.pdf", "force": true, "discard": alpha_target_v1}),
        )
        .await;
        assert_eq!(st, StatusCode::CONFLICT);
        assert_eq!(stale_cross["code"], "discard_target_stale");
        let (st, stale_sess_field) = post_json(
            &app,
            "/api/session/open",
            json!({"path": "alpha.pdf", "force": true, "session": alpha_session}),
        )
        .await;
        assert_eq!(st, StatusCode::CONFLICT);
        assert_eq!(stale_sess_field["code"], "discard_target_stale");

        let (st, still_beta) = get_json(&app, "/api/session/state").await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(still_beta["path"], "beta.pdf");
        assert_eq!(still_beta["vitals"]["hpCurrent"], "21");

        // 5. Git pull enforces the exact same discardTarget guard (cross-sheet & same-session rev)!
        let (st, pull_conflict) = post_json(&app, "/api/git/pull", json!({"force": false})).await;
        assert_eq!(st, StatusCode::CONFLICT);
        assert_eq!(pull_conflict["code"], "unsaved_edits");
        let beta_target_v1 = pull_conflict["discardTarget"].clone();
        assert_eq!(beta_target_v1["sheet"], "beta.pdf");
        assert_eq!(beta_target_v1["sessionId"], beta_session);

        // Stale Alpha target rejected on force pull.
        let (st, stale_pull) = post_json(
            &app,
            "/api/git/pull",
            json!({"force": true, "discard": alpha_target_v1}),
        )
        .await;
        assert_eq!(st, StatusCode::CONFLICT);
        assert_eq!(stale_pull["code"], "discard_target_stale");

        // Intervening Beta edit HP 21 -> 22 invalidates beta_target_v1 on force pull.
        let (st, _) = post_json(
            &app,
            "/api/session/edit",
            json!({"field": "HP Current", "value": "22", "sheet": "beta.pdf", "session": beta_session}),
        )
        .await;
        assert_eq!(st, StatusCode::OK);
        let (st, stale_pull_rev) = post_json(
            &app,
            "/api/git/pull",
            json!({"force": true, "discard": beta_target_v1}),
        )
        .await;
        assert_eq!(st, StatusCode::CONFLICT);
        assert_eq!(stale_pull_rev["code"], "discard_target_stale");
        let beta_target_v2 = stale_pull_rev["discardTarget"].clone();

        // Exact fresh discardTarget succeeds on force pull.
        let (st, pull_ok) = post_json(
            &app,
            "/api/git/pull",
            json!({"force": true, "discard": beta_target_v2}),
        )
        .await;
        assert_eq!(st, StatusCode::OK, "pull failed: {pull_ok}");

        let _ = std::fs::remove_dir_all(&base);
    }

    #[tokio::test]
    async fn restart_recovers_pending_idle_git_sync_and_preserves_concurrent_writes() {
        // 1. StoreSyncTracker generation guard never clears concurrent writes.
        let tracker = StoreSyncTracker::default();
        let gen1 = tracker.mark_dirty();
        assert!(tracker.is_dirty());
        let gen2 = tracker.mark_dirty();
        assert_ne!(gen1, gen2);
        assert!(!tracker.clear_if_unchanged(gen1));
        assert!(tracker.is_dirty());
        assert!(tracker.clear_if_unchanged(gen2));
        assert!(!tracker.is_dirty());

        // 2. Restarting a server against a dirty checkout recovers dirtySinceSync & idle auto-sync.
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let base = std::env::temp_dir().join(format!(
            "mpmb-serve-restart-sync-{}-{nanos}",
            std::process::id()
        ));
        let bare = base.join("remote.git");
        let data_dir = base.join("sheets");
        std::fs::create_dir_all(&bare).unwrap();
        assert!(Command::new("git")
            .args(["init", "--bare", "-b", "main"])
            .arg(&bare)
            .status()
            .unwrap()
            .success());

        let git_cmd = |dir: &std::path::Path, args: &[&str]| -> String {
            let mut cmd = Command::new("git");
            for key in [
                "GIT_DIR",
                "GIT_WORK_TREE",
                "GIT_INDEX_FILE",
                "GIT_COMMON_DIR",
                "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            ] {
                cmd.env_remove(key);
            }
            let out = cmd.current_dir(dir).args(args).output().unwrap();
            assert!(
                out.status.success(),
                "git {:?} failed: {}",
                args,
                String::from_utf8_lossy(&out.stderr)
            );
            String::from_utf8_lossy(&out.stdout).trim().to_owned()
        };

        let make_cfg = |idle_secs: u64| ServeConfig {
            bind: "127.0.0.1:0".parse().unwrap(),
            store: StoreConfig {
                root: data_dir.clone(),
                git: Some(GitConfig::new(bare.to_string_lossy().into_owned())),
            },
            default_sheet: None,
            auth_token: None,
            allow_unauthenticated: false,
            autosave: true,
            git_auto_sync_secs: idle_secs,
        };

        // Server 1: baseline sync, edit Alpha HP 10 -> 17 (autosaved, not yet synced), then stop.
        let base_sha = {
            let s1 = AppState::start(&make_cfg(300)).unwrap();
            make_scripted_hp_pdf(&data_dir.join("alpha.pdf"), "10", "", None);
            let app1 = build_router(s1);
            assert_eq!(
                post_json(&app1, "/api/git/sync", json!({"message": "baseline"}))
                    .await
                    .0,
                StatusCode::OK
            );
            let sha = git_cmd(&bare, &["rev-parse", "refs/heads/main"]);
            assert_eq!(
                post_json(&app1, "/api/session/open", json!({"path": "alpha.pdf"}))
                    .await
                    .0,
                StatusCode::OK
            );
            assert_eq!(
                post_json(
                    &app1,
                    "/api/session/edit",
                    json!({"field": "HP Current", "value": "17", "sheet": "alpha.pdf"}),
                )
                .await
                .0,
                StatusCode::OK
            );
            assert_eq!(git_cmd(&bare, &["rev-parse", "refs/heads/main"]), sha);
            sha
        };

        // Server 2: restart against same checkout -> must immediately report dirtySinceSync=true
        // and push Alpha on idle auto-sync!
        let s2 = AppState::start(&make_cfg(1)).unwrap();
        let app2 = build_router(s2.clone());
        let (st, state2) = get_json(&app2, "/api/session/state").await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(
            state2["dirtySinceSync"], true,
            "restarted server must recover dirty Git working tree state"
        );
        tokio::time::sleep(Duration::from_millis(1150)).await;
        let res = s2
            .dispatch_job(|job_id, gate, done| WorkerCommand::CheckIdleAutoSync {
                job_id,
                gate,
                done,
                idle_secs: 1,
            })
            .await;
        assert_eq!(res.status(), StatusCode::OK);
        let body = json_body(res).await;
        assert_eq!(body["sync"]["pushed"], true);
        assert_eq!(body["state"]["dirtySinceSync"], false);
        let after_dirty_sha = git_cmd(&bare, &["rev-parse", "refs/heads/main"]);
        assert_ne!(after_dirty_sha, base_sha);

        // Server 3: create an unpushed local commit (clean tree, ahead=1), restart -> must recover & push!
        make_scripted_hp_pdf(&data_dir.join("beta.pdf"), "25", "", None);
        git_cmd(&data_dir, &["add", "beta.pdf"]);
        git_cmd(&data_dir, &["commit", "-m", "unpushed local commit"]);
        let s3 = AppState::start(&make_cfg(1)).unwrap();
        let app3 = build_router(s3.clone());
        let (st, state3) = get_json(&app3, "/api/session/state").await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(
            state3["dirtySinceSync"], true,
            "restarted server must recover unpushed local commits (ahead > 0)"
        );
        tokio::time::sleep(Duration::from_millis(1150)).await;
        let res3 = s3
            .dispatch_job(|job_id, gate, done| WorkerCommand::CheckIdleAutoSync {
                job_id,
                gate,
                done,
                idle_secs: 1,
            })
            .await;
        assert_eq!(res3.status(), StatusCode::OK);
        let body3 = json_body(res3).await;
        assert_eq!(body3["sync"]["pushed"], true);
        assert_ne!(
            git_cmd(&bare, &["rev-parse", "refs/heads/main"]),
            after_dirty_sha
        );

        let _ = std::fs::remove_dir_all(&base);
    }

    #[tokio::test]
    async fn rejected_stale_force_open_preserves_active_modal_and_session_state() {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let base = std::env::temp_dir().join(format!(
            "mpmb-serve-modal-discard-{}-{nanos}",
            std::process::id()
        ));
        let data_dir = base.join("sheets");
        std::fs::create_dir_all(&data_dir).unwrap();

        make_scripted_hp_pdf(&data_dir.join("alpha.pdf"), "10", "", None);
        // Beta's button opens an Acrobat dialog whose cancel handler mutates HP Current to 99!
        make_scripted_hp_pdf(
            &data_dir.join("alpha.pdf"),
            "10",
            "",
            // Mutates previously clean Alpha HP 10 -> 21 BEFORE opening a confirmation dialog
            // whose cancel path mutates HP to 99!
            Some(
                "getField('HP Current').value = '21'; var r = app.execDialog({description:{name:'Alpha Confirm',elements:[{type:'ok_cancel'}]}}); if (r === 'cancel') { getField('HP Current').value = '99'; }",
            ),
        );
        // Beta's button opens an Acrobat dialog whose cancel handler mutates HP Current to 99!
        make_scripted_hp_pdf(
            &data_dir.join("beta.pdf"),
            "20",
            "",
            Some(
                "var r = app.execDialog({description:{name:'Beta Prompt',elements:[{type:'ok_cancel'}]}}); if (r === 'cancel') { getField('HP Current').value = '99'; }",
            ),
        );

        let state = AppState::start(&ServeConfig {
            bind: "127.0.0.1:0".parse().unwrap(),
            store: StoreConfig {
                root: data_dir,
                git: None,
            },
            default_sheet: None,
            auth_token: None,
            allow_unauthenticated: false,
            autosave: false,
            git_auto_sync_secs: 0,
        })
        .unwrap();
        let app = build_router(state);

        // Part 1: Previously clean Alpha mutates HP 10 -> 21 before opening a modal.
        // A normal Open Beta MUST reject with 409 interaction_required without cancelling Alpha's modal!
        let (st, a_open) = post_json(&app, "/api/session/open", json!({"path": "alpha.pdf"})).await;
        assert_eq!(st, StatusCode::OK);
        let alpha_session = a_open["state"]["sessionId"].as_str().unwrap().to_owned();
        let (st, alpha_modal) = post_json(
            &app,
            "/api/session/activate",
            json!({"field": "ActionButton", "index": 0, "sheet": "alpha.pdf", "session": alpha_session}),
        )
        .await;
        assert_eq!(st, StatusCode::ACCEPTED);
        let alpha_int_id = alpha_modal["interaction"]["id"]
            .as_str()
            .unwrap()
            .to_owned();

        let (st, blocked_clean_open) =
            post_json(&app, "/api/session/open", json!({"path": "beta.pdf"})).await;
        assert_eq!(st, StatusCode::CONFLICT);
        assert_eq!(blocked_clean_open["status"], "interaction_required");
        assert_eq!(blocked_clean_open["interaction"]["id"], alpha_int_id);

        // Answering OK completes Alpha with HP 21 (NOT 99 from Cancel!) and marks dirtySinceSave=true.
        let (st, alpha_done) = post_json(
            &app,
            &format!("/api/session/interaction/{alpha_int_id}"),
            json!({"result": "ok", "values": {}}),
        )
        .await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(alpha_done["state"]["vitals"]["hpCurrent"], "21");
        assert_eq!(alpha_done["state"]["dirtySinceSave"], true);

        let (st, conflict_alpha) =
            post_json(&app, "/api/session/open", json!({"path": "beta.pdf"})).await;
        assert_eq!(st, StatusCode::CONFLICT);
        assert_eq!(conflict_alpha["code"], "unsaved_edits");
        let alpha_target = conflict_alpha["discardTarget"].clone();

        // Part 2: Switch to Beta with valid Alpha discardTarget, edit Beta HP 20 -> 21, and open Beta's dialog.
        let (st, b_open) = post_json(
            &app,
            "/api/session/open",
            json!({"path": "beta.pdf", "force": true, "discard": alpha_target}),
        )
        .await;
        assert_eq!(st, StatusCode::OK);
        let beta_session = b_open["state"]["sessionId"].as_str().unwrap().to_owned();
        assert_eq!(
            post_json(
                &app,
                "/api/session/edit",
                json!({"field": "HP Current", "value": "21", "sheet": "beta.pdf", "session": beta_session}),
            )
            .await
            .0,
            StatusCode::OK
        );
        let (st, modal_resp) = post_json(
            &app,
            "/api/session/activate",
            json!({"field": "ActionButton", "index": 0, "sheet": "beta.pdf", "session": beta_session}),
        )
        .await;
        assert_eq!(st, StatusCode::ACCEPTED);
        let beta_int_id = modal_resp["interaction"]["id"].as_str().unwrap().to_owned();
        assert!(!modal_resp["interaction"]["serverInstanceId"]
            .as_str()
            .unwrap_or("")
            .is_empty());

        // Stale force-open (Alpha's old target), missing-target force-open, and non-force open
        // MUST all return 409 interaction_required WITHOUT cancelling Beta's dialog or running its cancel callback!
        for body in [
            json!({"path": "alpha.pdf", "force": true, "discard": alpha_target}),
            json!({"path": "alpha.pdf", "force": true}),
            json!({"path": "alpha.pdf"}),
        ] {
            let (st, resp) = post_json(&app, "/api/session/open", body).await;
            assert_eq!(st, StatusCode::CONFLICT);
            assert_eq!(resp["status"], "interaction_required");
            assert_eq!(resp["interaction"]["id"], beta_int_id);
        }

        // Beta's dialog must STILL be active!
        let (st, busy_state) = get_json(&app, "/api/session/state").await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(busy_state["busy"], true);
        assert_eq!(busy_state["activeInteraction"]["id"], beta_int_id);

        // Answering OK on Beta's dialog completes cleanly with HP 21 (NOT 99 from cancel)!
        let (st, reply_ok) = post_json(
            &app,
            &format!("/api/session/interaction/{beta_int_id}"),
            json!({"result": "ok", "values": {}}),
        )
        .await;
        assert_eq!(st, StatusCode::OK, "reply failed: {reply_ok}");
        assert_eq!(reply_ok["state"]["path"], "beta.pdf");
        assert_eq!(reply_ok["state"]["vitals"]["hpCurrent"], "21");

        let _ = std::fs::remove_dir_all(&base);
    }

    #[tokio::test]
    async fn restarted_server_rejects_old_interaction_reply_and_accepts_new_prompt() {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let base = std::env::temp_dir().join(format!(
            "mpmb-serve-restart-int-{}-{nanos}",
            std::process::id()
        ));
        let data_dir = base.join("sheets");
        std::fs::create_dir_all(&data_dir).unwrap();

        let dialog_js = "var r = app.execDialog({description:{name:'Set HP',elements:[{type:'edit_text',item_id:'hp'},{type:'ok_cancel'}]},initialize(d){d.load({hp:getField('HP Current').valueAsString});},commit(d){getField('HP Current').value=d.store().hp;}});";
        make_scripted_hp_pdf(&data_dir.join("alpha.pdf"), "10", "", Some(dialog_js));
        make_scripted_hp_pdf(&data_dir.join("beta.pdf"), "20", "", Some(dialog_js));

        let make_cfg = || ServeConfig {
            bind: "127.0.0.1:0".parse().unwrap(),
            store: StoreConfig {
                root: data_dir.clone(),
                git: None,
            },
            default_sheet: None,
            auth_token: None,
            allow_unauthenticated: false,
            autosave: true,
            git_auto_sync_secs: 0,
        };

        // Server 1 opens Alpha and mints its first interaction ID.
        let old_int_id = {
            let app1 = build_router(AppState::start(&make_cfg()).unwrap());
            assert_eq!(
                post_json(&app1, "/api/session/open", json!({"path": "alpha.pdf"}))
                    .await
                    .0,
                StatusCode::OK
            );
            let (st, m1) = post_json(
                &app1,
                "/api/session/activate",
                json!({"field": "ActionButton", "index": 0, "sheet": "alpha.pdf"}),
            )
            .await;
            assert_eq!(st, StatusCode::ACCEPTED);
            m1["interaction"]["id"].as_str().unwrap().to_owned()
        };

        // Server 2 (restarted) opens Beta and mints its own first interaction ID.
        let app2 = build_router(AppState::start(&make_cfg()).unwrap());
        assert_eq!(
            post_json(&app2, "/api/session/open", json!({"path": "beta.pdf"}))
                .await
                .0,
            StatusCode::OK
        );
        let (st, m2) = post_json(
            &app2,
            "/api/session/activate",
            json!({"field": "ActionButton", "index": 0, "sheet": "beta.pdf"}),
        )
        .await;
        assert_eq!(st, StatusCode::ACCEPTED);
        let new_int_id = m2["interaction"]["id"].as_str().unwrap().to_owned();
        assert_ne!(
            old_int_id, new_int_id,
            "interaction IDs across server restarts must be globally unique"
        );

        // Posting Server 1's old reply to Server 2 MUST fail with 409 and leave Beta's modal open!
        let (st, stale_reply) = post_json(
            &app2,
            &format!("/api/session/interaction/{old_int_id}"),
            json!({"result": "ok", "values": {"hp": "999"}}),
        )
        .await;
        assert_eq!(
            st,
            StatusCode::CONFLICT,
            "old interaction reply must be rejected: {stale_reply}"
        );
        let (st, busy) = get_json(&app2, "/api/session/state").await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(busy["busy"], true);
        assert_eq!(busy["activeInteraction"]["id"], new_int_id);

        // Responding with Server 2's actual interaction ID succeeds and applies Beta's edit.
        let (st, ok_reply) = post_json(
            &app2,
            &format!("/api/session/interaction/{new_int_id}"),
            json!({"result": "ok", "values": {"hp": "25"}}),
        )
        .await;
        assert_eq!(st, StatusCode::OK, "new reply failed: {ok_reply}");
        assert_eq!(ok_reply["state"]["path"], "beta.pdf");
        assert_eq!(ok_reply["state"]["vitals"]["hpCurrent"], "25");

        let _ = std::fs::remove_dir_all(&base);
    }

    #[tokio::test]
    async fn diverged_git_conflict_backup_is_deduplicated_across_idle_ticks_and_restart() {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let base = std::env::temp_dir().join(format!(
            "mpmb-serve-conflict-dedup-{}-{nanos}",
            std::process::id()
        ));
        let bare = base.join("remote.git");
        let upstream = base.join("upstream");
        let data_dir = base.join("sheets");
        std::fs::create_dir_all(&bare).unwrap();
        assert!(Command::new("git")
            .args(["init", "--bare", "-b", "main"])
            .arg(&bare)
            .status()
            .unwrap()
            .success());

        let git_cmd = |dir: &std::path::Path, args: &[&str]| -> String {
            let mut cmd = Command::new("git");
            for key in [
                "GIT_DIR",
                "GIT_WORK_TREE",
                "GIT_INDEX_FILE",
                "GIT_COMMON_DIR",
                "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            ] {
                cmd.env_remove(key);
            }
            let out = cmd.current_dir(dir).args(args).output().unwrap();
            assert!(
                out.status.success(),
                "git {:?} failed: {}",
                args,
                String::from_utf8_lossy(&out.stderr)
            );
            String::from_utf8_lossy(&out.stdout).trim().to_owned()
        };
        let conflict_refs = || -> Vec<String> {
            git_cmd(
                &bare,
                &["for-each-ref", "--format=%(refname)", "refs/heads/conflict"],
            )
            .lines()
            .filter(|l| !l.trim().is_empty())
            .map(str::to_owned)
            .collect()
        };

        let make_cfg = |repo_url: String| ServeConfig {
            bind: "127.0.0.1:0".parse().unwrap(),
            store: StoreConfig {
                root: data_dir.clone(),
                git: Some(GitConfig::new(repo_url)),
            },
            default_sheet: None,
            auth_token: None,
            allow_unauthenticated: false,
            autosave: true,
            git_auto_sync_secs: 1,
        };
        let bare_url = bare.to_string_lossy().into_owned();

        // 1. Seed baseline and push to bare remote.
        let s1 = AppState::start(&make_cfg(bare_url.clone())).unwrap();
        make_scripted_hp_pdf(&data_dir.join("alpha.pdf"), "10", "", None);
        let app1 = build_router(s1.clone());
        assert_eq!(
            post_json(&app1, "/api/git/sync", json!({"message": "baseline"}))
                .await
                .0,
            StatusCode::OK
        );

        // 2. Open alpha.pdf first, THEN advance remote main from an independent upstream clone
        //    so local main diverges instead of fast-forwarding on open.
        assert_eq!(
            post_json(&app1, "/api/session/open", json!({"path": "alpha.pdf"}))
                .await
                .0,
            StatusCode::OK
        );
        git_cmd(
            &base,
            &["clone", "-b", "main", &bare_url, upstream.to_str().unwrap()],
        );
        git_cmd(&upstream, &["config", "user.name", "Upstream"]);
        git_cmd(&upstream, &["config", "user.email", "up@example.com"]);
        make_scripted_hp_pdf(&upstream.join("upstream.pdf"), "50", "", None);
        git_cmd(&upstream, &["add", "upstream.pdf"]);
        git_cmd(&upstream, &["commit", "-m", "upstream commit"]);
        git_cmd(&upstream, &["push", "origin", "main"]);

        // 3. Make one server-side edit -> first idle sync creates exactly ONE conflict branch.
        assert_eq!(
            post_json(
                &app1,
                "/api/session/edit",
                json!({"field": "HP Current", "value": "17", "sheet": "alpha.pdf"}),
            )
            .await
            .0,
            StatusCode::OK
        );
        tokio::time::sleep(Duration::from_millis(1150)).await;
        let res1 = s1
            .dispatch_job(|job_id, gate, done| WorkerCommand::CheckIdleAutoSync {
                job_id,
                gate,
                done,
                idle_secs: 1,
            })
            .await;
        assert_eq!(res1.status(), StatusCode::OK);
        let b1 = json_body(res1).await;
        assert_eq!(b1["sync"]["status"], "conflict_branch");
        assert_eq!(b1["state"]["dirtySinceSync"], false);
        let refs_after_first = conflict_refs();
        assert_eq!(
            refs_after_first.len(),
            1,
            "expected 1 conflict branch: {refs_after_first:?}"
        );

        // 4. Subsequent idle ticks AND manual sync with no new edits must NOT create duplicates!
        for _ in 0..2 {
            tokio::time::sleep(Duration::from_millis(1100)).await;
            let skip = s1
                .dispatch_job(|job_id, gate, done| WorkerCommand::CheckIdleAutoSync {
                    job_id,
                    gate,
                    done,
                    idle_secs: 1,
                })
                .await;
            assert_eq!(skip.status(), StatusCode::OK);
            assert_eq!(json_body(skip).await["status"], "skipped");
        }
        let (st, manual_dup) =
            post_json(&app1, "/api/git/sync", json!({"message": "manual retry"})).await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(manual_dup["sync"]["status"], "conflict_branch");
        assert_eq!(
            conflict_refs(),
            refs_after_first,
            "same SHA must not create duplicate remote conflict branches"
        );
        drop(app1);
        drop(s1);

        // 5. Restart server on the same diverged checkout -> dirtySinceSync stays false and
        //    no duplicate conflict branch is created on idle ticks!
        let s2 = AppState::start(&make_cfg(bare_url.clone())).unwrap();
        let app2 = build_router(s2.clone());
        let (st, st2) = get_json(&app2, "/api/session/state").await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(st2["dirtySinceSync"], false);
        assert!(st2["git"]["last_conflict_branch"].as_str().is_some());
        tokio::time::sleep(Duration::from_millis(1100)).await;
        let skip2 = s2
            .dispatch_job(|job_id, gate, done| WorkerCommand::CheckIdleAutoSync {
                job_id,
                gate,
                done,
                idle_secs: 1,
            })
            .await;
        assert_eq!(json_body(skip2).await["status"], "skipped");
        assert_eq!(conflict_refs(), refs_after_first);

        // 6. A later edit produces a NEW SHA and DOES sync to a second conflict branch!
        assert_eq!(
            post_json(&app2, "/api/session/open", json!({"path": "alpha.pdf"}))
                .await
                .0,
            StatusCode::OK
        );
        assert_eq!(
            post_json(
                &app2,
                "/api/session/edit",
                json!({"field": "HP Current", "value": "18", "sheet": "alpha.pdf"}),
            )
            .await
            .0,
            StatusCode::OK
        );
        tokio::time::sleep(Duration::from_millis(1150)).await;
        let res2 = s2
            .dispatch_job(|job_id, gate, done| WorkerCommand::CheckIdleAutoSync {
                job_id,
                gate,
                done,
                idle_secs: 1,
            })
            .await;
        assert_eq!(res2.status(), StatusCode::OK);
        let b2 = json_body(res2).await;
        assert_eq!(b2["sync"]["status"], "conflict_branch");
        assert_eq!(b2["state"]["dirtySinceSync"], false);
        assert_eq!(
            conflict_refs().len(),
            2,
            "later edit must create a new backup ref"
        );
        drop(app2);
        drop(s2);

        // 7. Switching the SAME checkout to a brand-new empty second remote MUST NOT treat
        //    the first remote's conflict backup marker as valid — startup must report
        //    head_backed_up=false, dirtySinceSync=true, and idle sync must push to remote2!
        //    Also verify the marker never stores the raw remote URL.
        let marker_raw =
            std::fs::read_to_string(data_dir.join(".git/mpmb-conflict-backup.json")).unwrap();
        assert!(
            !marker_raw.contains(&bare_url),
            "conflict backup marker must hash destination identity rather than storing raw URL"
        );
        let bare2 = base.join("remote2.git");
        std::fs::create_dir_all(&bare2).unwrap();
        assert!(Command::new("git")
            .args(["init", "--bare", "-b", "main"])
            .arg(&bare2)
            .status()
            .unwrap()
            .success());
        let bare2_url = bare2.to_string_lossy().into_owned();
        let s_r2 = AppState::start(&make_cfg(bare2_url)).unwrap();
        let app_r2 = build_router(s_r2.clone());
        let (st, st_r2) = get_json(&app_r2, "/api/session/state").await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(st_r2["git"]["head_backed_up"], false);
        assert_eq!(st_r2["dirtySinceSync"], true);
        tokio::time::sleep(Duration::from_millis(1150)).await;
        let res_r2 = s_r2
            .dispatch_job(|job_id, gate, done| WorkerCommand::CheckIdleAutoSync {
                job_id,
                gate,
                done,
                idle_secs: 1,
            })
            .await;
        assert_eq!(res_r2.status(), StatusCode::OK);
        let b_r2 = json_body(res_r2).await;
        assert_eq!(b_r2["sync"]["pushed"], true);
        assert!(!git_cmd(&bare2, &["rev-parse", "refs/heads/main"]).is_empty());
        drop(app_r2);
        drop(s_r2);

        // 8. A failed/unbacked local commit (ahead > 0, head_backed_up == false) MUST still
        //    recover dirtySinceSync=true on restart so it retries!
        make_scripted_hp_pdf(&data_dir.join("unbacked.pdf"), "33", "", None);
        git_cmd(&data_dir, &["add", "unbacked.pdf"]);
        git_cmd(&data_dir, &["commit", "-m", "failed backup local commit"]);
        let s3 = AppState::start(&make_cfg(bare_url)).unwrap();
        let app3 = build_router(s3.clone());
        let (st, st3) = get_json(&app3, "/api/session/state").await;
        assert_eq!(st, StatusCode::OK);
        assert_eq!(st3["dirtySinceSync"], true);
        assert_eq!(st3["git"]["head_backed_up"], false);

        let _ = std::fs::remove_dir_all(&base);
    }
}
