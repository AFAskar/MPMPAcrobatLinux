// Acrobat host implementation. Original document scripts are loaded unmodified.
// The closure owns all live field state. PDF objects and UI use read-only snapshots.
// Acrobat's legacy replace callbacks receive empty strings for unmatched groups.
// The Windows probe in the development evidence verifies this observable behavior.
const __nativeReplace=String.prototype.replace;
String.prototype.replace=function(pattern,replacement){
  if(typeof replacement!=='function')return __nativeReplace.call(this,pattern,replacement);
  return __nativeReplace.call(this,pattern,function(...args){
    const end=args.length-(typeof args[args.length-1]==='object'?3:2);
    for(let i=1;i<end;i++)if(args[i]===undefined)args[i]='';
    return replacement.apply(undefined,args);
  });
};
var __host = (function () {
  const data=JSON.parse(__initial), fields={}, names=[], journal=[];
  const timers=new Map(), menus={}, gaps=[], errors=[], repairs=[], printJobs=[], assigning=new Set(), formatDirty=new Set();
  let clock=0, timerId=0, calculating=false, pending=false, revision=0;
  function unsupported(name) { gaps.push(name); throw Error('Unsupported Acrobat API: '+name); }
  function gap(name) { if(gaps.indexOf(name)<0)gaps.push(name); }
  function source(v, seen) {
    if(v===undefined)return 'undefined'; if(v===null)return 'null';
    if(typeof v==='function')return v.toString();
    if(v instanceof RegExp)return v.toString();
    if(v instanceof Error){errors.push({stage:'original-caught-exception',error:String(v),stack:v.stack});return '(new '+v.name+'('+JSON.stringify(v.message)+'))'}
    if(typeof v!=='object')return JSON.stringify(v);
    seen=seen||[];if(seen.indexOf(v)>=0)throw Error('cyclic toSource');
    seen.push(v);let s=Array.isArray(v)?'['+v.map(x=>source(x,seen)).join(',')+']':'({'+Object.keys(v).map(k=>JSON.stringify(k)+':'+source(v[k],seen)).join(',')+'})';seen.pop();return s;
  }
  Object.defineProperty(Object.prototype,'toSource',{value:function(){return source(this)},configurable:true});
  function addField(n,x) {
    const f={name:n,value:x.value,defaultValue:x.default_value,userName:x.user_name,submitName:x.submit_name,
      type:({Tx:'text',Ch:x.flags&131072?'combobox':'listbox',Btn:x.flags&65536?'button':x.flags&32768?'radiobutton':'checkbox'})[x.kind],
      readonly:!!(x.flags&1),display:x.display,textSize:x.text_size,textFont:x.text_font||'Helvetica',multiline:!!(x.flags&4096),
      richText:false,richValue:x.rich_value||[],textColor:['G',0],fillColor:['T'],strokeColor:['G',0],
      alignment:['left','center','right'][x.alignment||0],lineWidth:1,borderStyle:'solid',buttonPosition:0,buttonAlignX:50,buttonAlignY:50,
      calcOrderIndex:data.order.indexOf(n),items:x.items,exportValues:x.export_values||['Yes'],currentValueIndices:-1,
      page:x.widgets.length===1?x.widgets[0].page:x.widgets.map(w=>w.page),
      rect:x.widgets.length?x.widgets[0].rect:[],_widgets:x.widgets.map(w=>Object.assign({},w)),_actions:Object.assign({},x.actions),
      get valueAsString(){return String(this.value)}, get numItems(){return this.items.length},
      getItemAt(i,exportValue){let v=this.items[i];return Array.isArray(v)?v[exportValue?0:1]:v},
      setItems(items){this.items=items.slice()}, clearItems(){this.items=[]},
      insertItemAt(label,exp,i){this.items.splice(i===undefined?this.items.length:i,0,exp===undefined?label:[exp,label])},
      deleteItemAt(i){this.items.splice(i,1)},
      checkThisBox(i,on){this.value=on?(this.exportValues[i]||'Yes'):'Off'},isBoxChecked(i){return String(this.value)===(this.exportValues[i]||'Yes')?1:0},
      setAction(type,code){const key=({Calculate:'C',Validate:'V',Keystroke:'K',Format:'F',MouseUp:'U',MouseDown:'D',OnFocus:'Fo',OnBlur:'Bl'})[type];if(!key)return unsupported('Field.setAction '+type);code=String(code);if(this._actions[key]!==code){this._actions[key]=code;this._modifiedActions=this._modifiedActions||{};this._modifiedActions[key]=code;revision++;}},
      setFocus(){data.focus=n;const page=Array.isArray(this.page)?this.page.find(p=>p>=0):this.page;if(page>=0)globalThis.pageNum=page;},getArray(){return [this]},
      buttonGetIcon(face=0){if(face!==0)return unsupported('Field.buttonGetIcon non-normal face');return this._icon||{field:n,face:0}},
      buttonSetIcon(icon,face=0){if(face!==0)return unsupported('Field.buttonSetIcon non-normal face');if(!icon||typeof icon.field!=='string')return unsupported('Field.buttonSetIcon external icon');this._icon=Object.assign({},icon);revision++},
      buttonSetCaption(c,face=0){if(![0,1,2].includes(face))throw Error('Invalid button face');this._captions=this._captions||{};this._captions[face]=String(c);if(face===0)this._caption=String(c);revision++},buttonGetCaption(face=0){return this._captions&&this._captions[face]!==undefined?this._captions[face]:this._caption===undefined?(x.caption||''):this._caption},
    };
    for(const prop of ['textSize','textFont','richText','richValue','textColor','fillColor','strokeColor','alignment','lineWidth','borderStyle']){
      let stored=f[prop];Object.defineProperty(f,prop,{enumerable:true,get(){return stored},set(v){if(JSON.stringify(v)!==JSON.stringify(stored))gap('Field.'+prop+' appearance/persistence');stored=v;if(prop==='richValue'&&Array.isArray(v))f.value=v.map(span=>span.text||'').join('')}});
    }
    for(const prop of ['userName','submitName']){let stored=f[prop];Object.defineProperty(f,prop,{enumerable:true,get(){return stored},set(v){stored=String(v)}})}
    for(const prop of ['display','readonly']){let stored=f[prop];Object.defineProperty(f,prop,{enumerable:true,get(){return stored},set(v){if(stored!==v)revision++;stored=v}})}
    let raw=x.value;
    Object.defineProperty(f,'value',{enumerable:true,get(){return x.kind!=='Btn'&&typeof raw==='string'&&/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(raw)?Number(raw):raw},set(v){
      // Reader leaves the Wildfire Spirit's absent hit-die value as an empty
      // field. Undefined must not leak into subsequent original Format events.
      if(v===undefined)v='';
      if(raw===v)return;
      if(data.trace&&data.trace.includes(n))__log(n+': '+String(raw)+' -> '+String(v)+'\n'+new Error().stack);
      if(assigning.has(n)){raw=v;return}
      assigning.add(n);
      try {let e=eventRun(f,'V',v);if(e.rc){if(String(raw)!==String(e.value))formatDirty.add(n);if(raw!==e.value)revision++;raw=e.value;f._formatted=undefined;if(globalThis.event&&event.target===f&&event.name==='Calculate')event.value=e.value;if(globalThis.calculate&&globalThis.app&&app.calculate&&!calculating)calculateNow();}} finally{assigning.delete(n)}
    }});
    Object.defineProperty(f,'valueAsString',{get(){return String(raw)}});
    Object.defineProperty(f,'rect',{get(){const r=f._widgets[0]&&f._widgets[0].rect;return r&&r.length===4?[r[0],Math.max(r[1],r[3]),r[2],Math.min(r[1],r[3])]:[]},set(r){if(!Array.isArray(r)||r.length!==4||r.some(v=>!Number.isFinite(Number(v))))throw Error('Invalid field rectangle');for(const w of f._widgets)w.rect=[Number(r[0]),Math.min(Number(r[1]),Number(r[3])),Number(r[2]),Math.max(Number(r[1]),Number(r[3]))];revision++}});
    Object.defineProperty(f,'currentValueIndices',{get(){const values=Array.isArray(f.value)?f.value:[f.value];const found=f.items.map((_,i)=>i).filter(i=>values.some(v=>String(v)===String(f.getItemAt(i,true))));return x.flags&2097152?found:found.length?found[0]:-1},set(v){const ids=Array.isArray(v)?v:[v];if(ids.some(i=>!Number.isInteger(Number(i))||Number(i)<0||Number(i)>=f.items.length))throw Error('Invalid choice index');f.value=x.flags&2097152?ids.map(i=>f.getItemAt(Number(i),true)):f.getItemAt(Number(ids[0]),true)}});
    Object.defineProperty(f,'page',{get(){let pages=f._widgets.map(w=>w.page).filter(p=>p>=0);return pages.length===0?(f._widgets.length>1?[-1]:-1):f._widgets.length>1?pages:pages[0]}});
    Object.defineProperty(f,'calcOrderIndex',{get(){return data.order.indexOf(n)},set(i){const old=data.order.indexOf(n);if(old>=0)data.order.splice(old,1);data.order.splice(Math.max(0,Number(i)||0),0,n)}});
    fields[n]=f;names.push(n);return f;
  }
  for(const n of Object.keys(data.fields))addField(n,data.fields[n]);
  function spawn(template,index,rename,overlay){
    const t=data.templates&&data.templates[template];if(!t)throw Error('Unknown template '+template);
    if(overlay)return unsupported('Template.spawn overlay');
    index=index===undefined?0:Number(index);rename=rename===undefined?true:!!rename;
    if(!Number.isInteger(index)||index<0||index>globalThis.numPages)throw Error('Invalid spawn page index');

    const prefix=rename?'P'+index+'.'+template+'.':'';
    for(const n of Object.keys(t.fields))if(rename&&fields[prefix+n])throw Error('Duplicate template field '+prefix+n);
    for(const n of names)for(const w of fields[n]._widgets)if(w.page>=index)w.page++;
    for(const n of Object.keys(t.fields)){
      const x=JSON.parse(JSON.stringify(t.fields[n])),base=fields[n];
      if(base){x.value=base.valueAsString;x.user_name=base.userName;x.submit_name=base.submitName;x.display=base.display;x.rich_value=base.richValue;}
      for(const w of x.widgets)w.page=index;
      if(rename)addField(prefix+n,x);else{if(!fields[n])throw Error('Missing shared template field '+n);fields[n]._widgets.push(...x.widgets);}

    }
    for(const n of t.order)if(!data.order.includes(prefix+n))data.order.push(prefix+n);
    journal.push({op:'spawn',template,index,rename});globalThis.numPages++;globalThis.numFields=names.length;revision++;
  }
  function removeField(name){
    for(let i=names.length-1;i>=0;i--){let n=names[i];if(n===name||n.startsWith(name+'.')){names.splice(i,1);delete fields[n];let c=data.order.indexOf(n);if(c>=0)data.order.splice(c,1);}}
    journal.push({op:'removeField',name});globalThis.numFields=names.length;revision++;
  }
  function deletePages(first,last){
    const start=Number(typeof first==='object'?first.nStart:first===undefined?0:first),end=Number(typeof first==='object'?(first.nEnd===undefined?start:first.nEnd):last===undefined?start:last);
    if(!Number.isInteger(start)||!Number.isInteger(end)||start<0||end<start||end>=globalThis.numPages||end-start+1>=globalThis.numPages)throw Error('Invalid page deletion');
    for(let i=names.length-1;i>=0;i--){const n=names[i],f=fields[n],hadWidgets=f._widgets.length>0;f._widgets=f._widgets.filter(w=>w.page<start||w.page>end);for(const w of f._widgets)if(w.page>end)w.page-=end-start+1;
      if(hadWidgets&&!f._widgets.length){names.splice(i,1);delete fields[n];let c=data.order.indexOf(n);if(c>=0)data.order.splice(c,1);}}
    journal.push({op:'deletePages',start,end});globalThis.numPages-=end-start+1;globalThis.pageNum=Math.min(globalThis.pageNum,globalThis.numPages-1);globalThis.numFields=names.length;revision++;
  }
  function eventRun(f,key,value,extra) {
    let previous=globalThis.event;
    let e=Object.assign({target:f,source:fields[data.focus]||f,name:({C:'Calculate',V:'Validate',K:'Keystroke',F:'Format',U:'Mouse Up'})[key]||key,type:'Field',value:value,rc:true,willCommit:true,change:'',selStart:0,selEnd:0},extra||{});
    globalThis.event=e;
    try {if(f._actions[key]) (0,eval)(f._actions[key]);return e;}
    catch(err){errors.push({stage:'field',field:f.name,event:key,error:String(err),stack:err.stack});throw err}
    finally {globalThis.event=previous;}
  }
  function calculateNow() {
    if(calculating){pending=true;return}
    calculating=true;
    try {let passes=0; do {pending=false;for(const n of data.order){let f=fields[n];if(!f)throw Error('Missing calculation target '+n);if(f._actions.C){const e=eventRun(f,'C',f.value);if(e.rc)f.value=e.value;f._formatted=eventRun(f,'F',f.value).value;}}if(++passes>8)throw Error('calculation did not settle');}while(pending);const changed=Array.from(formatDirty);formatDirty.clear();for(const n of changed){const f=fields[n];if(f&&f._actions.F&&f._widgets.some(w=>w.page>=0))f._formatted=eventRun(f,'F',f.value).value;}}finally{calculating=false}
  }
  function edit(n,v) {
    let f=fields[n];if(!f)throw Error('Unknown field '+n);if(f.readonly)throw Error('Read-only field '+n);
    data.focus=n;
    let k=eventRun(f,'K',v);if(!k.rc)return false;
    f.value=k.value;
    if(globalThis.calculate&&app.calculate)calculateNow();
    f._formatted=eventRun(f,'F',f.value).value;globalThis.dirty=true;return true;
  }
  function activate(n,index=0){
    const f=fields[n];if(!f)throw Error('Unknown field '+n);data.focus=n;
    eventRun(f,'Fo',f.value);eventRun(f,'D',f.value);
    if(!f.readonly&&(f.type==='checkbox'||f.type==='radiobutton'))f.checkThisBox(index,f.type==='radiobutton'||!f.isBoxChecked(index));
    eventRun(f,'U',f.value);if(globalThis.calculate&&app.calculate)calculateNow();
  }
  function pageWidgets(page){const result=[];for(const n of names){const f=fields[n];if(f.display===1||f.display===3)continue;f._widgets.forEach((w,index)=>{if(w.page===page)result.push({name:n,index,rect:w.rect,type:f.type,readonly:f.readonly})})}return result;}
  function advance(ms) {
    const target=clock+ms;let count=0;
    while(true){let due=Array.from(timers.values()).filter(t=>t.at<=target).sort((a,b)=>a.at-b.at||a.id-b.id)[0];if(!due)break;
      clock=due.at;timers.delete(due.id);if(++count>100)throw Error('timer budget exceeded');
      try{(0,eval)(due.code)}catch(e){errors.push({stage:'timer',code:due.code,error:String(e),stack:e.stack});throw e}
    }clock=target;
  }
  function execDialog(def) {

    const store={},enabled={},visible={};let ended=null,focus=null;
    const dialog={load(x){Object.assign(store,x)},store(){return JSON.parse(JSON.stringify(store))},enable(x){Object.assign(enabled,x)},visible(x){Object.assign(visible,x)},end(x){ended=x},
      setForeColorRed(id){gap('Dialog.setForeColorRed visual')},focus(id){focus=id},setFocus(id){focus=id},insertEntryInList(o){for(const id of Object.keys(o))store[id]=Object.assign(store[id]||{},o[id])},removeAllEntriesFromList(id){store[id]={}},
    };
    const controls=[];function collect(e){if(e.item_id)controls.push(e);(e.elements||[]).forEach(collect)}collect(def.description||{});
    if(def.initialize)def.initialize(dialog);
    function finish(result){if(def.destroy)def.destroy(dialog);return result;}
    for(let i=0;i<1000;i++) {
      const rendered=Object.assign({},store);
      for(const key of Object.keys(rendered)){const icon=iconData(rendered[key]);if(icon)rendered[key]=icon;}
      const reply=JSON.parse(__dialog(JSON.stringify({description:def.description,values:rendered,enabled,visible,focus})));
      if(reply.values)for(const key of Object.keys(reply.values)){if(!store[key]||typeof store[key].read!=='function')store[key]=reply.values[key];}
      const control=reply.event&&controls.filter(c=>c.item_id===reply.event)[0];if(control&&control.type==='radio'){for(const c of controls)if(c.type==='radio'&&c.group_id===control.group_id)store[c.item_id]=c.item_id===control.item_id;}
      if(reply.result==='other'){if(def.other)def.other(dialog);if(ended!==null)return finish(ended);continue;}
      if(reply.event){if(typeof def[reply.event]==='function')def[reply.event](dialog);if(ended!==null)return finish(ended);continue;}
      if(reply.result==='ok') {if(def.validate&&!def.validate(dialog))continue;if(def.ok)def.ok(dialog);if(ended!==null)return finish(ended);if(def.commit)def.commit(dialog);return finish('ok')}
      if(def.cancel)def.cancel(dialog);return finish('cancel');
    }throw Error('dialog interaction budget exceeded');
  }
  function command(code){const previous=globalThis.event;globalThis.event={type:'App',name:'Exec',target:globalThis,rc:true};try{return (0,eval)(code)}finally{globalThis.event=previous}}
  function invokeMenu(name){const m=menus[name];if(!m)throw Error('Unknown menu '+name);const previous=globalThis.event;globalThis.event={type:'App',name:'Exec',target:globalThis,rc:true};try{if(m.cEnable)(0,eval)(m.cEnable);if(event.rc)(0,eval)(m.cExec||m.cExpr||'')}finally{globalThis.event=previous}}
  function iconData(icon){if(!icon||typeof icon.read!=='function'||!icon.width||!icon.height)return null;const copy=Object.assign({},icon,{count:0}),argb=icon.read.call(copy,icon.width*icon.height*8);if(typeof argb!=='string'||argb.length!==icon.width*icon.height*8||!/^[0-9a-f]+$/i.test(argb))throw Error('Unsupported Acrobat icon stream');return {width:icon.width,height:icon.height,argb};}
  function menuItems(){const out=[];for(const name of Object.keys(menus)){const m=menus[name];if(!m.cExec&&!m.cExpr)continue;const previous=globalThis.event;globalThis.event={target:globalThis,type:'App',name:'Exec',rc:true};try{if(m.cEnable)(0,eval)(m.cEnable);const enabled=!!event.rc;event.rc=false;if(m.cMarked)(0,eval)(m.cMarked);out.push({name,label:m.cLabel||m.cUser||name,tooltip:m.cTooltext||'',enabled,marked:!!event.rc,icon:iconData(m.oIcon)})}finally{globalThis.event=previous}}return out;}
  function popup(items){
    const choices={},def={description:{name:'MPMB menu',elements:[]},initialize(dialog){dialog.enable(enabled)}};const enabled={};let count=0;
    function build(item){if(typeof item==='string')item={cName:item};if(!item||item.cName==='-')return null;const id='menu'+count++;enabled[id]=item.bEnabled!==false;
      if(item.oSubMenu)return {type:'cluster',item_id:id,name:item.cName,elements:item.oSubMenu.map(build).filter(Boolean)};
      choices[id]=item.cReturn===undefined?item.cName:item.cReturn;def[id]=function(dialog){dialog.end(id)};
      return {type:'button',item_id:id,name:(item.bMarked?'✓ ':'')+item.cName};
    }
    def.description.elements=items.map(build).filter(Boolean);const result=execDialog(def);return Object.prototype.hasOwnProperty.call(choices,result)?choices[result]:undefined;
  }
  function applyQualifiedRepairs(){
    if(!data.repair_allowed)return;
    const source=globalThis.ApplyWildshape&&ApplyWildshape.toString();
    if(!source||!source.includes('var prop = entries[i];')||!source.includes('pop.wildshapeShow'))throw Error('Qualified wild-shape repair did not match the loaded function');
    const fixed=source.replace(/\bpop\./g,'prop.');
    globalThis.ApplyWildshape=(0,eval)('('+fixed+')');
    const repair={id:'mpmb-2024-261023-wildshape-pop-typo',scope:'runtime only',embedded_scripts_modified:false,reason:'Original ApplyWildshape reads pop instead of its local prop variable'};
    repairs.push(repair);__log('Applied qualified runtime repair: '+repair.id);
  }
  return {activate,pageWidgets,menuItems,popup,applyQualifiedRepairs,get revision(){return revision},recordError(e){errors.push(e)},fields,names,data,menus,gaps,errors,source,unsupported,gap,calculateNow,edit,advance,execDialog,invokeMenu,command,spawn,removeField,deletePages,
    print(params){const result=JSON.parse(__print(JSON.stringify({params,state:JSON.parse(__host.snapshot())})));printJobs.push(result);return undefined},
    ready(){let n=0;while(!globalThis.calculate||!app.calculate||globalThis.delay){let t=Array.from(timers.values()).sort((a,b)=>a.at-b.at)[0];if(!t||++n>100)throw Error('Document calculations suspended without a resumable timer');advance(Math.max(0,t.at-clock));}return true},
    snapshot(){let o={__structure:journal,__order:data.order};if(data.bookmarksChanged)o.__bookmarks=bookmarkRoot;for(const n of names){let f=fields[n];o[n]={value:Array.isArray(f.value)?f.value:f.valueAsString,icon:f._icon,caption:f._caption,captions:f._captions,actions:f._modifiedActions,widgets:f._widgets,currentValueIndices:f.currentValueIndices,textSize:f.textSize,alignment:f.alignment,multiline:f.multiline,textColor:f.textColor,textFont:f.textFont,richValue:f.richValue,formatted:f._formatted===undefined?f.value:f._formatted,display:f.display,userName:f.userName,submitName:f.submitName,readonly:f.readonly,items:f.items};}return JSON.stringify(o)},
    timer(code,ms){let id=++timerId;timers.set(id,{id,code:String(code),at:clock+Math.max(1,Number(ms)||1)});return id},clear(id){timers.delete(id)},
    diagnostics(){return JSON.stringify({gaps,errors,repairs,printJobs,timers:timers.size,field_count:names.length,menus:Object.keys(menus)})}
  };
})();
var display={visible:0,hidden:1,noPrint:2,noView:3};
var color={transparent:['T'],black:['G',0],white:['G',1],red:['RGB',1,0,0],blue:['RGB',0,0,1],green:['RGB',0,1,0],ltGray:['G',0.75],gray:['G',0.5],dkGray:['G',0.25],convert(c){return c},equal(a,b){return JSON.stringify(a)===JSON.stringify(b)}};
var font={Helv:'Helvetica',HelvB:'Helvetica-Bold',HelvI:'Helvetica-Oblique',HelvBI:'Helvetica-BoldOblique',TiRo:'Times-Roman',Cour:'Courier',ZaDb:'ZapfDingbats'};
var border={s:'solid',d:'dashed',b:'beveled',i:'inset',u:'underline'};
var highlight={n:'none',i:'invert',p:'push',o:'outline'};
var position={textOnly:0,iconOnly:1,iconTextV:2,textIconV:3,iconTextH:4,textIconH:5,overlay:6};
var scaleWhen={always:0,never:1,tooBig:2,tooSmall:3},scaleHow={proportional:0,anamorphic:1};
var event={target:globalThis,name:'Open',type:'Doc',value:'',rc:true};
var console={println(s){__log(String(s))},show(){__host.gap('console.show UI')},clear(){__host.gap('console.clear UI')}};
var global={};
var app={viewerType:'Reader',viewerVersion:26,formsVersion:26,platform:'UNIX',language:'ENU',calculate:true,runtimeHighlight:false,
  execDialog:__host.execDialog,
  setTimeOut(code,ms){return __host.timer(code,ms)},clearTimeOut(id){__host.clear(id)},
  setInterval(){return __host.unsupported('app.setInterval')},clearInterval(id){__host.clear(id)},
  alert(o){o=typeof o==='string'?{cMsg:o}:o;if(/error/i.test(o.cTitle||''))__host.recordError({stage:'original-alert',error:o.cMsg,title:o.cTitle});const r=JSON.parse(__alert(JSON.stringify(o)));if(o.oCheckbox)o.oCheckbox.bAfterValue=!!r.checked;return r.button},
  response(question,title,defaultValue,password,label){const o=typeof question==='object'?question:{cQuestion:question,cTitle:title,cDefault:defaultValue,bPassword:password,cLabel:label};let answer=o.cDefault||'';const result=__host.execDialog({description:{name:o.cTitle||'MPMB response',elements:[{type:'static_text',name:o.cQuestion||''},{type:'edit_text',item_id:'answer',password:!!o.bPassword,char_width:50},{type:'ok_cancel'}]},initialize(d){d.load({answer:String(answer)})},commit(d){answer=d.store().answer}});return result==='ok'?answer:null},
  popUpMenuEx(...items){return __host.popup(items)},popUpMenu(...items){function convert(v){return Array.isArray(v)?{cName:v[0],oSubMenu:v.slice(1).map(convert)}:{cName:String(v)}}return __host.popup(items.map(convert))},
  addMenuItem(o){__host.menus[o.cName]=o},addSubMenu(o){__host.menus[o.cName]=o},
  addToolButton(o){__host.menus[o.cName]=o},removeToolButton(o){delete __host.menus[typeof o==='string'?o:o.cName]},
  removeMenuItem(n){delete __host.menus[n]},removeSubMenu(n){delete __host.menus[n]},
  execMenuItem(n){return __host.unsupported('app.execMenuItem '+n)},
  thermometer:{duration:100,value:0,text:undefined,begin(){this.text=''},end(){this.text=undefined}},
  get activeDocs(){return [globalThis]},
};
var util={
  printf(fmt,...args){let i=0;return fmt.replace(/%([+0 ,]*)(\d*)(?:\.(\d+))?([dfsxX])/g,(m,flags,width,prec,type)=>{let v=args[i++];let s=type==='s'?String(v):type==='d'?String(Math.trunc(Number(v))):type==='f'?Number(v).toFixed(prec===undefined?6:Number(prec)):Number(v).toString(16);if(flags.includes('+')&&Number(v)>=0)s='+'+s;return s.padStart(Number(width)||0,flags.includes('0')?'0':' ')})},
  printd(fmt,date){let d=date||new Date();return String(fmt).replace(/yyyy|yy|mmmm|mmm|mm|dd|HH|MM|ss/g,t=>({yyyy:d.getFullYear(),yy:String(d.getFullYear()).slice(-2),mmmm:d.toLocaleString('en',{month:'long'}),mmm:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getMonth()],mm:String(d.getMonth()+1).padStart(2,'0'),dd:String(d.getDate()).padStart(2,'0'),HH:d.getHours(),MM:d.getMinutes(),ss:d.getSeconds()})[t])},
  scand(fmt,s){let d=new Date(s);return isNaN(d)?null:d},
  readFileIntoStream(path){return JSON.parse(__file(path||''))},stringFromStream(stream){if(!stream||typeof stream.data!=='string')throw Error('Invalid text stream');return stream.data},
};
Object.assign(globalThis,{
  info:JSON.parse(__initial).info,documentFileName:JSON.parse(__initial).file,path:JSON.parse(__initial).path,
  numPages:JSON.parse(__initial).pages,numFields:__host.names.length,calculate:true,delay:false,dirty:false,pageNum:0,
  getField(n){n=String(n).replace(/\.{2,}/g,'.');if(__host.fields[n])return __host.fields[n];const selected=/^(.*)\.(\d+)$/.exec(n);if(selected&&__host.fields[selected[1]]){const base=__host.fields[selected[1]],index=Number(selected[2]);if(!base._widgets[index])return null;return new Proxy(base,{get(target,key){if(key==='page')return target._widgets[index].page;if(key==='setFocus')return function(){__host.data.focus=target.name;__host.data.focusWidget=index;const page=target._widgets[index].page;if(page>=0)globalThis.pageNum=page;};return target[key]}})}const prefix=String(n)+'.';let children=__host.names.filter(x=>x.startsWith(prefix));return children.length?new Proxy({name:n,getArray(){return children.map(x=>__host.fields[x])}},{get(o,k){return k in o?o[k]:__host.fields[children[0]][k]},set(o,k,v){for(const child of children)__host.fields[child][k]=v;return true}}):null},
  getNthFieldName(i){return __host.names[i]},calculateNow:__host.calculateNow,
  resetForm(list){for(const n of __host.names){if(!list||list.some(x=>n===x||n.startsWith(x+'.')))__host.fields[n].value=__host.fields[n].defaultValue;}},
  getTemplate(n){return __host.data.templates&&__host.data.templates[n]?{name:n,spawn(index,rename,overlay){return __host.spawn(n,index,rename,overlay)}}:null},
  get templates(){return Object.keys(__host.data.templates||{}).map(n=>getTemplate(n))},
  removeField:__host.removeField,deletePages:__host.deletePages,
  getPrintParams(){return {firstPage:0,lastPage:numPages-1,interactive:0,DuplexType:1,constants:{interactionLevel:{full:0,automatic:1,silent:2},duplexTypes:{Simplex:1,DuplexFlipLongEdge:2,DuplexFlipShortEdge:3}}}},
  print(params){if(!params||typeof params!=='object')return __host.unsupported('Doc.print legacy arguments');return __host.print(params)},
});

function AFRange_Validate(lower,minimum,upper,maximum){let n=Number(event.value);if(event.value!==''&&((lower&&n<minimum)||(upper&&n>maximum)))event.rc=false;}
function AFDate_Format(format){if(event.value){let d=util.scand(format,event.value);if(d)event.value=util.printd(format,d);}}

function __bookmark(node,parent){
  function changed(){__host.data.bookmarksChanged=true;globalThis.dirty=true;}
  const children=(node.children||[]).map(child=>__bookmark(child,node));node.children=children;
  for(const property of ['name','open','style','color']){let value=node[property];if(value===undefined)value=({name:'',open:false,style:0,color:['RGB',0,0,0]})[property];Object.defineProperty(node,property,{enumerable:true,get(){return value},set(v){if(JSON.stringify(v)!==JSON.stringify(value)){value=v;changed()}}});}
  node.execute=function(){const previous=globalThis.event;globalThis.event={type:'Bookmark',name:'Mouse Up',target:this,rc:true};try{if(this.code)return (0,eval)(this.code);if(this.destinationPage!==undefined){if(this.destinationApproximate)__host.gap('Bookmark destination zoom/position');pageNum=this.destinationPage;}else if(this.unsupportedAction)return __host.unsupported('Bookmark action '+this.unsupportedAction);}finally{globalThis.event=previous}};
  node.setAction=function(code){this.code=String(code);this.actionChanged=true;delete this.destinationPage;changed()};
  node.createChild=function(o,expr,index){if(typeof o==='string')o={cName:o,cExpr:expr,nIndex:index};const at=o.nIndex===undefined?0:Number(o.nIndex);if(!Number.isInteger(at)||at<0||at>this.children.length)throw Error('Invalid bookmark insertion index');this.children.splice(at,0,__bookmark({name:String(o.cName||''),code:o.cExpr===undefined?'':String(o.cExpr),actionChanged:true,children:[]},this));changed()};
  node.remove=function(){if(!parent)throw Error('Cannot remove bookmark root');const index=parent.children.indexOf(this);if(index>=0){parent.children.splice(index,1);changed()}};
  return node;
}
var bookmarkRoot=__bookmark(JSON.parse(__initial).bookmarks);
function AFNumber_Format(decimals,sepStyle,negStyle,currStyle,currency,prepend){
  if(event.value===''||event.value===null){event.value='';return}
  let numeric=typeof event.value==='number'?event.value:Number(String(event.value).replace(/,/g,''));
  if(!Number.isFinite(numeric))throw Error('AFNumber_Format requires a finite number');
  const negative=numeric<0;let text=Math.abs(numeric).toFixed(Math.max(0,Math.min(20,Math.trunc(decimals))));
  let parts=text.split('.');if(sepStyle===0||sepStyle===2)parts[0]=parts[0].replace(/\B(?=(\d{3})+(?!\d))/g,sepStyle===0?',':'.');
  text=parts.join(sepStyle===2||sepStyle===3?',':'.');
  if(currency)text=prepend?currency+text:text+currency;
  if(negative)text=negStyle===2||negStyle===3?'('+text+')':negStyle===1?text:'-'+text;
  if(negStyle===1||negStyle===3)event.target.textColor=negative?color.red:color.black;
  event.value=text;
}
