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
    fn select(options: &mut Value, label: &str, matches: &mut usize) {
        if let Some(options) = options.as_object_mut() {
            for (name, value) in options {
                if let Some(n) = value.as_i64() {
                    let magnitude = n.saturating_abs().max(1);
                    *value = json!(if name == label {
                        *matches += 1;
                        magnitude
                    } else {
                        -magnitude
                    });
                } else {
                    select(value, label, matches);
                }
            }
        }
    }
    for (id, label) in selections {
        let label = label.as_str().context("dialog selection must be a label")?;
        if request["enabled"][&id] == false || request["visible"][&id] == false {
            bail!("dialog control {id} is unavailable")
        }
        let mut options = request["values"][&id].clone();
        let mut matches = 0;
        select(&mut options, label, &mut matches);
        if matches != 1 {
            bail!("dialog control {id} offers {matches} matches for {label}")
        }
        if !reply["values"].is_object() {
            reply["values"] = json!({});
        }
        reply["values"][&id] = options;
    }
    Ok(())
}
impl Runtime {
    pub fn new(
        pdf: &Arc<Pdf>,
        dialogs: Vec<Value>,
        alerts: Vec<i32>,
        interactive: bool,
        print_output_dir: Option<std::path::PathBuf>,
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
        js.with(|ctx|->Result<()>{
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
                select_dialog_options(&request,&mut reply).map_err(|e|e.to_string())?;
                eprintln!("Dialog: {} [scripted response]",request["description"]["name"]);
                return Ok(reply.to_string())
            }
            if !interactive{return Err(format!("Unanswered dialog: {}",request["description"]["name"]))}
            crate::ui::modal(&request).map(|v|v.to_string()).map_err(|e|e.to_string())
          })().map_err(|e|Exception::throw_message(&ctx,&e))
        })?)?;
        let aq=Arc::new(Mutex::new(VecDeque::from(alerts)));
        ctx.globals().set("__alert",Function::new(ctx.clone(),move|ctx:Ctx,s:String|->rquickjs::Result<String>{
          (||->std::result::Result<String,String>{
            let v:Value=serde_json::from_str(&s).map_err(|e|e.to_string())?;
            if let Some(reply)=aq.lock().unwrap().pop_front(){eprintln!("Alert [scripted response]: {}",v["cTitle"]);return Ok(json!({"button":reply,"checked":v["oCheckbox"]["bInitialValue"].as_bool().unwrap_or(false)}).to_string())}
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
        let initial=json!({"repair_allowed":repair_allowed,"templates":pdf.templates,"trace":std::env::var("MPMB_TRACE_FIELDS").unwrap_or_default().split(',').collect::<Vec<_>>(),"bookmarks":pdf.bookmarks,"fields":pdf.fields,"order":pdf.order,"info":pdf.info,"file":pdf.path.file_name().unwrap().to_string_lossy(),"path":pdf.path,"pages":pdf.doc.get_pages().len()});
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
    fn host(test: &str) {
        let engine = Engine::new().unwrap();
        engine.set_max_stack_size(1024 * 1024);
        let context = Context::full(&engine).unwrap();
        context.with(|ctx|{
            let field=|name:&str,value:&str,actions:Value|json!({"name":name,"value":value,"default_value":"","user_name":"","submit_name":"","kind":"Tx","flags":0,"display":0,"text_size":10,"widgets":[],"items":[],"actions":actions});
            ctx.globals().set("__initial",json!({"fields":{"A":field("A","2",json!({"V":"if (Number(event.value)<0) event.rc=false;"})),"B":field("B","0",json!({"C":"event.value=getField('A').value+1;"})),"C":field("C","0",json!({"C":"event.value=getField('B').value+1;"}))},"order":["B","C"],"info":{},"bookmarks":{"children":[]},"pages":1,"templates":{"blank":{"fields":{},"order":[]}}}).to_string()).unwrap();
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
    fn template_spawn_and_deletion_update_the_live_model() {
        host("var definition=JSON.parse(__initial).fields.A;definition.widgets=[{page:0,id:[90,0],rect:[1,1,10,10]}];__host.data.templates.Test={fields:{A:definition},order:[]};getTemplate('Test').spawn(1,true,false);var added=getField('P1.Test.A')!==null&&numPages===2;deletePages(1);added&&numPages===1&&getField('P1.Test.A')===null&&getField('A')!==null");
    }
    #[test]
    fn dialog_list_operations_and_ok_handler_are_committed() {
        host("var saved;globalThis.__dialog=function(){return JSON.stringify({result:'ok'})};__host.execDialog({description:{elements:[]},initialize:function(d){d.load({list:{A:-1}});d.insertEntryInList({list:{B:-2}});d.focus('list')},ok:function(d){saved=d.store().list},commit:function(d){d.removeAllEntriesFromList('list')}});saved.A===-1&&saved.B===-2");
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
    fn undefined_field_assignment_does_not_reach_original_string_formatting() {
        host("getField('A').setAction('Format',\"event.value=event.value.replace(/x/g,'')\");getField('A').value=undefined;calculateNow();var state=JSON.parse(__host.snapshot());getField('A').valueAsString===''&&state.A.value===''&&state.A.formatted===''");
    }
}
