/* Local, scoped test adapter. Installed as a Reader application folder-level script. */
var MPMBTesting = {
    root: "/C/Users/mpmb-test/MPMB-Testing/",
    session: String(new Date().getTime()) + "-" + String(Math.random()).slice(2),
    lastId: null,
    busy: false,
    normalize: function(p) { return String(p).replace(/\\/g, "/").replace(/^C:/i, "/C"); },
    scoped: function(p) {
        p = this.normalize(p);
        if (p.toLowerCase().indexOf(this.root.toLowerCase()) !== 0 || p.indexOf("..") >= 0) throw Error("Path outside test workspace");
        return p;
    },
    execute: app.trustedFunction(function(q) {
        app.beginPriv();try{
        if (q.op === "ping") return {protocol:3,session:this.session,version:app.viewerVersion,type:app.viewerType};
        if (q.session !== this.session) throw Error("Stale or absent bridge session");
        var d = this.doc(q.path), out = {path:d.path,pages:d.numPages,fields:{}};
        if ((q.op==='set' || q.op==='call' || q.op==='focus' || q.op==='field_coercion') && this.normalize(q.path).toLowerCase().indexOf(this.root.toLowerCase()+'runs/')!==0)throw Error('Mutations require a disposable runs document');
        if (q.op === "read") {
            for (var i=0;i<q.fields.length;i++) { var f=d.getField(q.fields[i]);out.fields[q.fields[i]]=f ? f.valueAsString : null; }
            out.numFields=d.numFields;out.calculation={app:app.calculate,doc:d.calculate,delay:d.delay};
        } else if (q.op === "field_summary") {
            for(var i=0;i<q.fields.length;i++){
                var f=d.getField(q.fields[i]);if(!f){out.fields[q.fields[i]]=null;continue;}
                var text=f.valueAsString,a=1,b=0;
                for(var j=0;j<text.length;j++){a=(a+text.charCodeAt(j))%65521;b=(b+a)%65521;}
                out.fields[q.fields[i]]={code_units:text.length,adler32_utf16:String((b*65536+a)>>>0)};
            }
        } else if (q.op === "set") {
            for (var k in q.values) if (q.values.hasOwnProperty(k) && !d.getField(k))throw Error("Missing field: "+k);
            for (var k in q.values) if (q.values.hasOwnProperty(k)) { var f=d.getField(k);if (!f) throw Error("Missing field: "+k);f.value=q.values[k]; }
            d.calculateNow();
            for (var k in q.values) if (q.values.hasOwnProperty(k)) out.fields[k]=d.getField(k).valueAsString;
        } else if (q.op === "focus") {
            var field=d.getField(q.field);if(!field) throw Error("Missing field: "+q.field);out.value=field.valueAsString;
        } else if (q.op === "save") {
            var target=this.scoped(q.output);
            if (target.toLowerCase().indexOf(this.root.toLowerCase()+"runs/") !== 0) throw Error("Save target must be inside runs");
            d.calculateNow();d.saveAs({cPath:target,bPromptToOverwrite:false});out.path=d.path;
        } else if (q.op === "print_params") {
            var pp=d.getPrintParams();out.firstPage=pp.firstPage;out.lastPage=pp.lastPage;out.printerName=pp.printerName;out.interactive=pp.interactive;out.DuplexType=pp.DuplexType;
            out.interactionLevel={};out.duplexTypes={};
            var interaction=['full','automatic','silent'],duplex=['Simplex','DuplexFlipLongEdge','DuplexFlipShortEdge'];
            for(var i=0;i<interaction.length;i++)out.interactionLevel[interaction[i]]=pp.constants.interactionLevel[interaction[i]];
            for(var i=0;i<duplex.length;i++)out.duplexTypes[duplex[i]]=pp.constants.duplexTypes[duplex[i]];
        } else if (q.op === "field_coercion") {
            var f=d.getField('Player Name'),before=f.valueAsString;out.probes=[];
            var values=[undefined,null,true,false,0,1.5,'12'];
            try {for(var i=0;i<values.length;i++){f.value='sentinel';f.value=values[i];out.probes.push({inputType:typeof values[i],input:String(values[i]),valueType:typeof f.value,value:String(f.value),valueAsString:f.valueAsString});}}
            finally {f.value=before;}
        } else if (q.op === "call") {
            var allowed={resourceDecisionDialog:1,ClassFeatureOptions:1,resetLimFeaUsed:1,HealItNow:1,PrintButton:1,PrintTheSheet:1,calcCont:1,ImportUserScriptFile:1,RunUserScript:1,ApplyClasses:1,ApplyClassLevel:1,SelectClass:1,ApplyRace:1,ApplyBackground:1,GenerateSpellSheet:1,GenerateSpellSheetWithAll:1,DoTemplate:1,ApplyCompRace:1,ApplyWildshape:1,SetStringifieds:1};
            if (!allowed[q.name] || typeof d[q.name] !== "function") throw Error("Unsupported MPMB function: "+q.name);
            if(q.name==="ImportUserScriptFile"){
                if(q.file_picker){this.scoped(q.import_file);q.args=[];}
                else q.args[0]=this.scoped(q.args[0]);
            }
            var value=d[q.name].apply(d,q.args || []);out.returnType=typeof value;if(value===null || typeof value==="string" || typeof value==="number" || typeof value==="boolean")out.value=value;out.pages=d.numPages;
        } else if (q.op === "functions") {
            var names=q.names || [];out.calculation={app:app.calculate,doc:d.calculate,delay:d.delay};out.functions={};
            out.openDocuments=[];var active=app.activeDocs || [];
            for(var j=0;j<active.length;j++)out.openDocuments.push(String(active[j].path));
            for(var i=0;i<names.length;i++) out.functions[names[i]]=typeof d[names[i]];
        } else throw Error("Unknown operation");
        return out;
        }finally{app.endPriv();}
    })
};
/* Each privileged API is reached from an explicitly elevated trusted wrapper. */
MPMBTesting.doc=app.trustedFunction(function(path){
 app.beginPriv();
 try {
  path=MPMBTesting.scoped(path);
  var docs=app.activeDocs || [];
  for(var i=0;i<docs.length;i++) if(MPMBTesting.normalize(docs[i].path).toLowerCase()===path.toLowerCase())return docs[i];
  var opened=app.openDoc({cPath:path});
  if(!opened)throw Error("Reader did not disclose requested document");
  return opened;
 }finally{app.endPriv();}
});
MPMBTesting.deliverResult=app.trustedFunction(function() {
    var pending=MPMBTesting.pendingResult;
    if(!pending)return;
    MPMBTesting.pendingResult=null;
    MPMBTesting.resultTimer=null;
    try {
        app.alert({cTitle:"MPMB Automation Result",cMsg:"MPMB_RESULT\n"+pending.encoded,nIcon:3,nType:0});
        // The alert restores the previous control when dismissed. Focus only
        // after it returns, using the document named by the original request.
        if(pending.response.ok && pending.request.op==='focus'){
            app.beginPriv();try{MPMBTesting.doc(pending.request.path).getField(pending.request.field).setFocus();}finally{app.endPriv();}
        }
    } finally {MPMBTesting.busy=false;}
});

MPMBTesting.run=app.trustedFunction(function(q) {
    if(MPMBTesting.busy)throw Error("Previous command is awaiting its result");
    app.beginPriv();
    var response={id:q.id,session:MPMBTesting.session,ok:false};
    try {
        if(!q.expires || q.expires < new Date().getTime()) throw Error("Expired command");
        if(q.id===MPMBTesting.lastId) throw Error("Duplicate command");
        MPMBTesting.lastId=q.id;
        response.result=MPMBTesting.execute(q);response.ok=true;
    } catch(e) {response.error=String(e);}
    finally {app.endPriv();}
    var encoded=JSON.stringify(response);
    if(encoded.length>12000){
        response={id:q.id,session:MPMBTesting.session,ok:false,operation_completed:response.ok,error:'Response exceeds the dialog transport limit. Do not repeat mutations; use field_summary or inspect a saved PDF.'};
        encoded=JSON.stringify(response);
    }
    MPMBTesting.pendingResult={encoded:encoded,response:response,request:q};
    MPMBTesting.busy=true;
    // Let the originating document-menu frame return before presenting its
    // receipt. Keep the timer alive; it inherits that menu's document context.
    try {MPMBTesting.resultTimer=app.setTimeOut("MPMBTesting.deliverResult();",0);}
    catch(timerError){MPMBTesting.deliverResult();}
});

MPMBTesting.consume=app.trustedFunction(function(target){
 app.beginPriv();
 var q=null,stage='receive native request';
 try {
  var text=app.response({cQuestion:'Serialized local test request',cTitle:'MPMB Automation Request',cDefault:'',bPassword:false});
  if(text===null)return;
  stage='parse request JSON';
  q=JSON.parse(text);
  if(!q.id || !/^[a-f0-9]{32}$/.test(q.id))throw Error('Invalid request id');
  if(q.op!=='ping' && (!target || MPMBTesting.normalize(target.path).toLowerCase()!==MPMBTesting.scoped(q.path).toLowerCase())){
   throw Error('Requested document is not the active menu context');
  }
  MPMBTesting.run(q);
 }catch(error){
  app.alert({cTitle:'MPMB Automation Result',cMsg:'MPMB_RESULT\n'+JSON.stringify({id:q?q.id:'invalid',session:MPMBTesting.session,ok:false,error:String(error),stage:stage}),nType:0});
 }finally{app.endPriv();}
});
app.addMenuItem({cName:'MPMBTestingMenu',cUser:'&MPMB testing command',cParent:'File',cExec:'MPMBTesting.consume(event.target);',nPos:0});
