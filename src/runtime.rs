use crate::pdf::Pdf;
use anyhow::{anyhow, bail, Context as _, Result};
use rquickjs::{Context, Ctx, Exception, Function, Runtime as Engine};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::VecDeque,
    sync::{Arc, Mutex},
};
pub struct Runtime {
    pub js: Context,
    _engine: Engine,
    pub loaded: usize,
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
        let repair_allowed = std::env::var_os("MPMB_STRICT_ORIGINAL_SCRIPTS").is_none()
            && pdf.scripts.iter().any(|(name, source)| {
                name == "Functions2"
                    && Sha256::digest(source.as_bytes())
                        .iter()
                        .map(|b| format!("{b:02x}"))
                        .collect::<String>()
                        == "ce4624265af7fad2456badd108fa6003e5dbb939263ee7269a4cbbf9e3055857"
            });
        let attachments = crate::attachments::read(&pdf.doc)?;
        let attachment_metadata: Vec<_> = attachments.values().cloned().collect();
        let exporter = std::cell::RefCell::new(crate::attachments::Exporter::default());
        js.with(|ctx|->Result<()>{
        ctx.globals().set("__attachment",Function::new(ctx.clone(),move|ctx:Ctx,request:String|->rquickjs::Result<String>{
            exporter.borrow_mut().export(&attachments,&request,interactive,attachment_output_dir.as_deref())
                .map(|v|v.to_string()).map_err(|e|Exception::throw_message(&ctx,&format!("{e:#}")))
        })?)?;
        let print_pdf=Arc::clone(pdf);
        ctx.globals().set("__print",Function::new(ctx.clone(),move|ctx:Ctx,request:String|->rquickjs::Result<String>{
            crate::printing::execute(&print_pdf,&request,interactive,print_output_dir.as_deref())
                .map(|v|v.to_string()).map_err(|e|Exception::throw_message(&ctx,&format!("{e:#}")))
        })?)?;
        ctx.globals().set("__log",Function::new(ctx.clone(),|s:String|{eprintln!("JS: {s}");true})?)?;
        let queue=Arc::new(Mutex::new(VecDeque::from(dialogs)));
        let trace_dir=std::env::var_os("MPMB_DIALOG_TRACE_DIR").map(std::path::PathBuf::from);let trace_count=Arc::new(Mutex::new(0usize));
        ctx.globals().set("__dialog",Function::new(ctx.clone(),move|ctx:Ctx,s:String|->rquickjs::Result<String>{
          (||->std::result::Result<String,String>{
            let request:Value=serde_json::from_str(&s).map_err(|e|e.to_string())?;
            if let Some(dir)=&trace_dir{std::fs::create_dir_all(dir).map_err(|e|e.to_string())?;let mut count=trace_count.lock().unwrap();*count+=1;std::fs::write(dir.join(format!("dialog-{:03}.json",*count)),&s).map_err(|e|e.to_string())?;}
            if let Some(mut reply)=queue.lock().unwrap().pop_front(){
                if let Some(title)=reply["title"].as_str(){if request["description"]["name"].as_str()!=Some(title){return Err(format!("Expected dialog {title}, received {}",request["description"]["name"]))}}
                if let Some(header)=reply["header"].as_str(){
                    fn find_header(node:&Value)->Option<&str>{if node["item_id"]=="head"{return node["name"].as_str()}node["elements"].as_array().and_then(|v|v.iter().find_map(find_header))}
                    if find_header(&request["description"])!=Some(header){return Err(format!("Expected dialog header {header}"))}
                }
                select_dialog_options(&request,&mut reply).map_err(|e|e.to_string())?;
                select_dialog_button(&request,&mut reply).map_err(|e|e.to_string())?;
                eprintln!("Dialog: {} [scripted response]",request["description"]["name"]);
                return Ok(reply.to_string())
            }
            if !interactive{return Err(format!("Unanswered dialog: {}",request["description"]["name"]))}
            crate::ui::modal(&request).map(|v|v.to_string()).map_err(|e|e.to_string())
          })().map_err(|e|Exception::throw_message(&ctx,&e))
        })?)?;
        let aq=Arc::new(Mutex::new(VecDeque::from(alerts)));
        let alert_trace_dir=std::env::var_os("MPMB_DIALOG_TRACE_DIR").map(std::path::PathBuf::from);let alert_count=Arc::new(Mutex::new(0usize));
        ctx.globals().set("__alert",Function::new(ctx.clone(),move|ctx:Ctx,s:String|->rquickjs::Result<String>{
          (||->std::result::Result<String,String>{
            let v:Value=serde_json::from_str(&s).map_err(|e|e.to_string())?;
            if let Some(dir)=&alert_trace_dir{std::fs::create_dir_all(dir).map_err(|e|e.to_string())?;let mut count=alert_count.lock().unwrap();*count+=1;std::fs::write(dir.join(format!("alert-{:03}.json",*count)),&s).map_err(|e|e.to_string())?;}
            if let Some(reply)=aq.lock().unwrap().pop_front(){eprintln!("Alert [scripted response]: {}",v["cTitle"]);return scripted_alert_response(&v,&reply).map(|v|v.to_string()).map_err(|e|e.to_string())}
            if !interactive{return Err(format!("Unanswered alert: {}",v["cTitle"]))}
            crate::ui::alert(&v).map(|v|v.to_string()).map_err(|e|e.to_string())
          })().map_err(|e|Exception::throw_message(&ctx,&e))
        })?)?;
        ctx.globals().set("__file",Function::new(ctx.clone(),move|ctx:Ctx,path:String|->rquickjs::Result<String>{
            (||->Result<String>{
                let selected=if path.is_empty(){
                    if !interactive{bail!("file picker requires interactive mode or explicit local path")}
                    let out=std::process::Command::new("zenity").args(["--file-selection","--title=Import MPMB JavaScript","--file-filter=JavaScript | *.js"]).output()?;
                    if !out.status.success(){return Ok("null".into())}String::from_utf8(out.stdout)?.trim_end_matches('\n').to_owned()
                }else{path};
                if selected.starts_with("http:")||selected.starts_with("https:"){bail!("URL imports are unsupported")}
                let bytes=std::fs::read(selected)?;if bytes.len()>16*1024*1024{bail!("import exceeds 16 MiB")}
                Ok(json!({"data":String::from_utf8(bytes)?}).to_string())
            })().map_err(|e|Exception::throw_message(&ctx,&format!("{e:#}")))
        })?)?;
        let initial=json!({"attachments":attachment_metadata,"repair_allowed":repair_allowed,"templates":pdf.templates,"trace":std::env::var("MPMB_TRACE_FIELDS").unwrap_or_default().split(',').collect::<Vec<_>>(),"bookmarks":pdf.bookmarks,"fields":pdf.fields,"order":pdf.order,"info":pdf.info,"file":pdf.path.file_name().unwrap().to_string_lossy(),"path":pdf.path,"pages":pdf.doc.get_pages().len()});
        ctx.globals().set("__initial",initial.to_string())?;
        ctx.eval::<(),_>(concat!(include_str!("acrobat.js"),"\nvoid 0;")).map_err(|e|anyhow!("Acrobat host: {e}: {:?}",ctx.catch()))?;
        Ok(())})?;
        let mut rt = Self {
            js,
            _engine: engine,
            loaded: 0,
        };
        for (name, code) in &pdf.scripts {
            rt.eval(code)
                .with_context(|| format!("original document script {name}"))?;
            rt.loaded += 1;
        }
        rt.eval("__host.applyQualifiedRepairs()")?;
        let diagnostics = rt.diagnostics()?;
        if diagnostics["errors"]
            .as_array()
            .is_some_and(|e| !e.is_empty())
        {
            bail!(
                "original initialization reported errors: {}",
                diagnostics["errors"]
            )
        }
        Ok(rt)
    }
    pub fn eval(&self, s: &str) -> Result<Value> {
        // Preserve stack traces, including exceptions caught by original sheet code in diagnostics.
        let quoted = serde_json::to_string(s)?;
        let wrapped=format!("(function(){{try{{let v=(0,eval)({quoted});return JSON.stringify({{ok:true,value:v===undefined?null:v}})}}catch(e){{return JSON.stringify({{ok:false,error:String(e),stack:e.stack}})}}}})()");
        let reply: String = self.raw(&wrapped)?;
        let v: Value = serde_json::from_str(&reply)?;
        if v["ok"] != true {
            return Err(anyhow!("{}\n{}", v["error"], v["stack"]));
        }
        Ok(v["value"].clone())
    }
    fn raw(&self, code: &str) -> Result<String> {
        self.js.with(|ctx| {
            ctx.eval::<String, _>(code)
                .map_err(|e| anyhow!("JavaScript engine: {e}: {:?}", ctx.catch()))
        })
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
        Ok(serde_json::from_str(&s)?)
    }
    pub fn edit(&self, n: &str, v: &Value) -> Result<()> {
        self.eval(&format!("__host.edit({},{})", serde_json::to_string(n)?, v))?;
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
            let field=|name:&str,value:&str,actions:Value|json!({"name":name,"value":value,"default_value":"","user_name":"","submit_name":"","kind":"Tx","flags":0,"display":0,"text_size":10,"widgets":[],"items":[],"actions":actions});
            ctx.globals().set("__initial",json!({"fields":{"A":field("A","2",json!({"V":"if (Number(event.value)<0) event.rc=false;"})),"B":field("B","0",json!({"C":"event.value=getField('A').value+1;"})),"C":field("C","0",json!({"C":"event.value=getField('B').value+1;"})),"Unchecked":json!({"kind":"Btn","flags":0,"value":"Off","default_value":"","items":[],"widgets":[],"actions":{},"export_values":["True"]})},"order":["B","C"],"info":{},"bookmarks":{"children":[]},"pages":1,"templates":{"blank":{"fields":{},"order":[]}}}).to_string()).unwrap();
            ctx.eval::<(),_>(concat!(include_str!("acrobat.js"),"\nvoid 0;")).unwrap();
            assert!(ctx.eval::<bool,_>(test).unwrap());
        });
    }
    #[test]
    fn original_order_and_numeric_values() {
        host("__host.edit('A','18'); getField('A').value===18 && getField('B').value===19 && getField('C').value===20 && getField('A').valueAsString==='18'");
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
    fn field_rect_uses_acrobat_top_bottom_order() {
        host("var f=getField('A');f._widgets=[{page:0,rect:[1,2,20,30]}];var correct=f.rect[1]===30;f.rect=[10,40,25,5];correct&&JSON.stringify(f._widgets[0].rect)==='[10,5,25,40]'");
    }
    #[test]
    fn indexed_rectangles_and_base_rectangle_change_only_the_selected_widget() {
        host("var f=getField('A');f._widgets=[{page:0,rect:[1,2,20,30]},{page:1,rect:[40,50,60,70]}];var second=getField('A.1'),before=JSON.stringify(second.rect);second.rect=[41,80,65,52];var firstUnchanged=JSON.stringify(f.rect)==='[1,30,20,2]';f.rect=[3,35,24,4];var copy=second.rect;copy[0]=999;var s=JSON.parse(__host.snapshot());before==='[40,70,60,50]'&&firstUnchanged&&JSON.stringify(s.A.widgets[0].rect)==='[3,4,24,35]'&&JSON.stringify(s.A.widgets[1].rect)==='[41,52,65,80]'");
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
    fn formatted_display_invalidates_appearance_without_changing_canonical_value() {
        host("var f=getField('A');var offset=10;f.setAction('Format','event.value=Number(event.value)+offset');f.value=2;f._appearanceDirty=false;offset=20;f.value=2;var s=JSON.parse(__host.snapshot()).A;s.value==='2'&&s.formatted===22&&s.appearanceDirty");
    }
    #[test]
    fn rich_format_invalidation_survives_an_unchanged_value_commit() {
        host("var f=getField('A');f.richText=true;var label='one';f.setAction('Format','event.richValue=[{text:label}]');f.value='stored';f._appearanceDirty=false;label='two';f.value='stored';var s=JSON.parse(__host.snapshot()).A;s.value==='stored'&&s.rawRichValue[0].text==='stored'&&s.richValue[0].text==='two'&&s.appearanceDirty");
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
    fn dialog_destroy_runs_after_commit_cancel_and_custom_end() {
        host("var trace=[],reply={result:'ok'};globalThis.__dialog=()=>JSON.stringify(reply);var def={description:{elements:[]},commit(){trace.push('commit')},cancel(){trace.push('cancel')},destroy(){trace.push('destroy')},other(d){d.end('save')}};__host.execDialog(def);reply={result:'cancel'};__host.execDialog(def);reply={result:'other'};var result=__host.execDialog(def);result==='save'&&JSON.stringify(trace)==='[\"commit\",\"destroy\",\"cancel\",\"destroy\",\"destroy\"]'");
    }
    #[test]
    fn popup_menu_returns_the_original_leaf_command() {
        host("globalThis.__dialog=function(){return JSON.stringify({event:'menu1'})};app.popUpMenuEx({cName:'Pages',oSubMenu:[{cName:'Companion',cReturn:'template#AScomp#add'}]})==='template#AScomp#add'");
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
