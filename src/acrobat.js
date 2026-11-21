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
  const timers=new Map(), menus={}, gaps=[], errors=[], repairs=[], printJobs=[], attachmentExports=[], xfdfImports=[], launchedUrls=[], assigning=new Set(), formatDirty=new Set(), formatting=new Set();
  let clock=0, timerId=0, calculating=false, pending=false, revision=0, importBatch=0, importActive=0, paneState='';
  const applicationState=globalThis.__nativeApplicationState||(globalThis.__nativeApplicationState={});
  const iconTokens=applicationState.iconTokens||(applicationState.iconTokens=new WeakSet());
  const iconImports=[];
  const consoleState=applicationState.console||(applicationState.console={visible:false,messages:[]});
  const unsupportedErrors=globalThis.__nativeApplicationState?(globalThis.__nativeApplicationState.unsupportedErrors||(globalThis.__nativeApplicationState.unsupportedErrors=new WeakSet())):new WeakSet();
  function unsupported(name) { gaps.push(name);const error=Error('Unsupported Acrobat API: '+name);unsupportedErrors.add(error);throw error; }
  function safeExceptionText(value){try{return String(value)}catch(_){return '[unprintable thrown value]'}}
  function gap(name) { if(gaps.indexOf(name)<0)gaps.push(name); }
  // Serialized state is stored in PDF text fields, which normalize literal
  // NBSP and line separators. Quote UTF-16 units so evaluating saved state
  // restores string values and property names without transport damage.
  function sourceString(value){return JSON.stringify(value).replace(/[\u007f-\uffff]/g,ch=>'\\u'+ch.charCodeAt(0).toString(16).padStart(4,'0'));}
  function source(v, seen) {
    if(v===undefined)return 'undefined'; if(v===null)return 'null';
    if(typeof v==='string')return sourceString(v);
    if(typeof v==='function')return v.toString();
    if(v instanceof RegExp)return v.toString();
    if(v instanceof Error){errors.push({stage:'original-caught-exception',error:String(v),stack:v.stack});return '(new '+v.name+'('+sourceString(v.message)+'))'}
    if(typeof v!=='object')return JSON.stringify(v);
    seen=seen||[];if(seen.indexOf(v)>=0)throw Error('cyclic toSource');
    seen.push(v);let s=Array.isArray(v)?'['+v.map(x=>source(x,seen)).join(',')+']':'({'+Object.keys(v).map(k=>sourceString(k)+':'+source(v[k],seen)).join(',')+'})';seen.pop();return s;
  }
  Object.defineProperty(Object.prototype,'toSource',{value:function(){return source(this)},configurable:true});
  function displayFlags(value,old){value=Number(value);if(![0,1,2,3].includes(value))throw Error('Invalid field display');return (old&~(2|4|32))|({0:4,1:6,2:0,3:36})[value];}
  function widgetDisplay(f,index){const w=f._widgets[index];if(!w||w.flags===undefined)return f._fallbackDisplay;const flags=w.flags;return flags&2?1:flags&32?3:flags&4?0:2;}
  function setWidgetDisplay(f,index,value){const w=f._widgets[index];if(!w)throw Error('Invalid widget index');const next=displayFlags(value,w.flags===undefined?displayFlags(f._fallbackDisplay,4):w.flags);if(next!==w.flags){w.flags=next;revision++;}}
  function widgetRect(f,index){const w=f._widgets[index],r=w&&w.rect;if(!w||w.page<0||!r||r.length!==4)return invalidFieldGet();const fixed=v=>Math.round(v*65536)/65536;return [fixed(r[0]),fixed(Math.max(r[1],r[3])),fixed(r[2]),fixed(Math.min(r[1],r[3]))];}
  function setWidgetRect(f,index,r){if(!Array.isArray(r)||r.length!==4||r.some(v=>!Number.isFinite(Number(v))))throw Error('Invalid field rectangle');const w=f._widgets[index];if(!w)throw Error('Invalid widget index');if(w.page<0){const e=new Error('Set not possible, invalid or unknown.');e.name='InvalidSetError';throw e;}const next=[Number(r[0]),Math.min(Number(r[1]),Number(r[3])),Number(r[2]),Math.max(Number(r[1]),Number(r[3]))];if(JSON.stringify(w.rect)!==JSON.stringify(next)){w.rect=next;revision++;}}
  function copyData(v){return v===undefined?undefined:JSON.parse(JSON.stringify(v));}
  function sameRich(a,b){
    function normalized(spans){return (spans||[]).map(span=>{const result={};for(const key of Object.keys(span).sort()){const value=span[key];result[key]=key==='text'?String(value).replace(/\r\n|\r|\n/g,'\r'):value;}return result;});}
    return JSON.stringify(normalized(a))===JSON.stringify(normalized(b));
  }
  function invalidFieldGet(){const e=new Error('Get not possible, invalid or unknown.');e.name='InvalidGetError';throw e;}
  function richStyleColor(value){if(!Array.isArray(value))throw Error('Invalid text color');let rgb;if(value[0]==='RGB'&&value.length===4)rgb=value.slice(1);else if(value[0]==='G'&&value.length===2)rgb=[value[1],value[1],value[1]];else return unsupported('Field.defaultStyle color '+value[0]);if(rgb.some(v=>!Number.isFinite(Number(v))))throw Error('Invalid text color');return ['RGB',...rgb.map(v=>Math.round(Math.round(Math.max(0,Math.min(1,Number(v)))*255)/255*65536)/65536)];}
  function textValue(f,value){let text=String(value);if(/[\u00a0\ufb01\ufb02]/.test(text))text=__normalizePdfText(text);return text.replace(/\r\n|\r|\n/g,f.multiline?'\r':' ');}
  function richChanges(value){return (String(value).match(/[^\r]*\r|[^\r]+$/g)||[]).map(text=>({changeMarker:true,text}));}
  function richImportText(spans){return spans.map(span=>String(span.text||'')+(span.endParagraph&&!/[\r\n]$/.test(span.text)?'\r':'')).join('');}
  function richText(spans){return (spans||[]).map(span=>span.text===undefined?'':String(span.text)).join('');}
  function richDecorations(span){
    // Reader accepts literal booleans and its named underline modes, rather
    // than generic truthiness. Explicit none retains an empty-string property.
    if(span.underline===true)span.underline='underline';
    else if(span.underline==='none'){span.underline='';span.strikethrough=span.strikethrough===true;}
    else if(!['underline','double','word'].includes(span.underline))delete span.underline;
    if(span.strikethrough!==true&&span.underline!=='')delete span.strikethrough;
    return span;
  }
  function normalizeRich(f,input){
    if(!Array.isArray(input))return [];
    const result=[];
    for(let i=0;i<input.length;i++){
      const item=input[i];if(!item||typeof item!=='object'||Array.isArray(item))throw Error('Invalid rich span');
      const span=Object.assign(copyData(f._defaultStyle),richDecorations(copyData(item)));delete span.changeMarker;
      for(const key of ['textSize','linespacing'])if(typeof span[key]==='number'&&Number.isFinite(span[key]))span[key]=__roundRichMetric(span[key]);
      span.text=textValue(f,item.text===undefined?'':item.text);
      if(!span.endParagraph||i===input.length-1)delete span.endParagraph;
      if(item.textColor){let rgb;if(item.textColor[0]==='RGB')rgb=item.textColor.slice(1);else if(item.textColor[0]==='G')rgb=[item.textColor[1],item.textColor[1],item.textColor[1]];else return unsupported('Field.richValue color '+item.textColor[0]);span.textColor=['RGB',...rgb.map(v=>Math.round(Math.floor(Math.floor(Math.max(0,Math.min(1,Number(v)))*65536)/65536*255)/255*65536)/65536)];}
      if(span.text||span.endParagraph){const previous=result[result.length-1];const style=s=>{const v=copyData(s);delete v.text;return v;};if(previous&&!previous.endParagraph&&!span.endParagraph&&sameRich([style(previous)],[style(span)]))previous.text+=span.text;else result.push(span);}
    }
    return result;
  }
  function formatResult(f,e){
    const rich=f.richText?(e._valueWritten?null:e._richWritten?normalizeRich(f,e._richData):copyData(e._richData)):undefined;
    const signature=JSON.stringify([String(e.value),rich]);
    // Retain the last display signature across value commits, which invalidate
    // the Format cache even when the canonical value itself is unchanged.
    if(f._formatSignature!==undefined&&f._formatSignature!==signature||rich==null&&String(e.value)!==f.valueAsString)f._appearanceDirty=true;
    if(JSON.stringify(f._formatted)!==JSON.stringify(e.value)||JSON.stringify(f._formattedRichValue)!==JSON.stringify(rich))revision++;
    f._formatSignature=signature;f._formatted=e.value;f._formattedRichValue=rich;
  }
  function reformat(f,duringCalculation=false){if(!f._actions.F||(calculating&&!duringCalculation)||formatting.has(f.name))return;formatting.add(f.name);try{formatResult(f,eventRun(f,'F',f.value));}finally{formatting.delete(f.name);}}
  function addField(n,x) {
    const f={name:n,value:x.value,defaultValue:x.default_value,userName:x.user_name,submitName:x.submit_name,_exportFlags:x.flags,
      type:({Tx:'text',Ch:x.flags&131072?'combobox':'listbox',Btn:x.flags&65536?'button':x.flags&32768?'radiobutton':'checkbox'})[x.kind],
      readonly:!!(x.flags&1),display:x.display,textSize:x.text_size,textFont:x.text_font||'Helvetica',multiline:!!(x.flags&4096),
      richText:x.kind==='Tx'&&!!(x.flags&33554432),richValue:x.rich_value||[],textColor:copyData(x.text_color)||['G',0],fillColor:['T'],strokeColor:['G',0],
      alignment:['left','center','right'][x.alignment||0],lineWidth:1,borderStyle:'solid',buttonPosition:0,buttonAlignX:50,buttonAlignY:50,
      calcOrderIndex:data.order.indexOf(n),items:x.items,exportValues:x.export_values||['Yes'],currentValueIndices:-1,
      page:x.widgets.length===1?x.widgets[0].page:x.widgets.map(w=>w.page),
      rect:x.widgets.length?x.widgets[0].rect:[],_widgets:x.widgets.map(w=>Object.assign({flags:displayFlags(x.display,4)},w)),_fallbackDisplay:x.display,_actions:Object.assign({},x.actions),
      get valueAsString(){return String(this.value)}, get numItems(){return this.items.length},
      getItemAt(i,exportValue){let v=this.items[i];return Array.isArray(v)?v[exportValue?0:1]:v},
      setItems(items){this.items=items.slice()}, clearItems(){this.items=[]},
      insertItemAt(label,exp,i){this.items.splice(i===undefined?this.items.length:i,0,exp===undefined?label:[exp,label])},
      deleteItemAt(i){this.items.splice(i,1)},
      checkThisBox(i,on){this.value=on?(this.exportValues[i]||'Yes'):'Off'},isBoxChecked(i){return String(this.value)===(this.exportValues[i]||'Yes')?1:0},
      setAction(type,code){const key=({Calculate:'C',Validate:'V',Keystroke:'K',Format:'F',MouseUp:'U',MouseDown:'D',OnFocus:'Fo',OnBlur:'Bl'})[type];if(!key)return unsupported('Field.setAction '+type);code=String(code);if(key==='C'){const index=data.order.indexOf(n);if(code&&index<0){data.order.push(n);revision++;}else if(!code&&index>=0){data.order.splice(index,1);revision++;}}if(this._actions[key]!==code){this._actions[key]=code;this._modifiedActions=this._modifiedActions||{};this._modifiedActions[key]=code;revision++;}},
      setFocus(){focusField(n);},getArray(){return [this]},
      browseForFileToSubmit(){if(this.type!=='text'||!(x.flags&1048576))throw Error('File selection requires a file-select text field');if(typeof __browsePdf!=='function')return unsupported('Field.browseForFileToSubmit');const path=__browsePdf();if(path!==null)this.value=path;},
      buttonGetIcon(face=0){if(face!==0)return unsupported('Field.buttonGetIcon non-normal face');return this._icon?Object.assign({},this._icon):{field:n,face:0}},
      buttonSetIcon(icon,face=0){if(face!==0)return unsupported('Field.buttonSetIcon non-normal face');if(icon&&icon.asset&&iconTokens.has(icon.asset)){this._icon={asset:icon.asset};globalThis.dirty=true;revision++;return;}if(!icon||typeof icon.field!=='string')return unsupported('Field.buttonSetIcon external icon');this._icon=Object.assign({},icon);revision++},
      buttonImportIcon(cPath,nPage=0){if(this.type!=='button')return unsupported('Field.buttonImportIcon on non-pushbutton');if(typeof __iconImport!=='function')return unsupported('Field.buttonImportIcon');if(cPath&&typeof cPath==='object'){nPage=cPath.nPage===undefined?0:cPath.nPage;cPath=cPath.cPath;}const result=JSON.parse(__iconImport(JSON.stringify({path:cPath===undefined?null:String(cPath),page:Number(nPage)})));iconImports.push({field:n,code:result.code,reason:result.reason});if(result.code===0){const asset=Object.freeze(result.asset);iconTokens.add(asset);this._icon={asset};globalThis.dirty=true;revision++;}return result.code;},
      buttonSetCaption(c,face=0){if(![0,1,2].includes(face))throw Error('Invalid button face');this._captions=this._captions||{};this._captions[face]=String(c);if(face===0)this._caption=String(c);revision++},buttonGetCaption(face=0){return this._captions&&this._captions[face]!==undefined?this._captions[face]:this._caption===undefined?(x.caption||''):this._caption},
    };
    const initialStyle=copyData(x.rich_metadata&&x.rich_metadata.defaultStyle)||{alignment:f.alignment,fontFamily:[f.textFont,'sans-serif'],fontStretch:'normal',fontStyle:'normal',fontWeight:400,textColor:['RGB',0,0,0],textSize:f.textSize};
    f._defaultStyle=copyData(initialStyle);let styleBatch=false;
    function fontInfo(font){if(font===(x.text_font||'Helvetica'))return {family:initialStyle.fontFamily[0],weight:initialStyle.fontWeight,style:initialStyle.fontStyle};const suffix=/(?:-)?(BoldItalic|BoldOblique|Bold|Italic|Oblique)$/.exec(font);let family=suffix?font.slice(0,suffix.index):font;family=({'SegoeUI':'Segoe UI','Times-Roman':'Times'})[family]||family;return {family,weight:suffix&&/Bold/.test(suffix[1])?700:400,style:suffix&&/Italic|Oblique/.test(suffix[1])?'italic':'normal'};}
    function fontName(style){const family=style.fontFamily[0],bold=Number(style.fontWeight)>=600,italic=/italic|oblique/i.test(style.fontStyle);if(family===initialStyle.fontFamily[0]&&Number(style.fontWeight)===Number(initialStyle.fontWeight)&&style.fontStyle===initialStyle.fontStyle)return x.text_font||'Helvetica';if(family==='Helvetica'||family==='Courier')return family+(bold||italic?'-'+(bold?'Bold':'')+(italic?'Oblique':''):'');if(family==='Times')return 'Times-'+(bold?(italic?'BoldItalic':'Bold'):(italic?'Italic':'Roman'));const base=family==='Segoe UI'?'SegoeUI':family;if(bold||italic)gap('Field.defaultStyle nonstandard font face mapping');return base+(bold||italic?'-'+(bold?'Bold':'')+(italic?'Italic':''):'');}
    Object.defineProperty(f,'defaultStyle',{enumerable:true,get(){if(x.kind!=='Tx'||!f.richText)return invalidFieldGet();return copyData(f._defaultStyle)},set(v){if(x.kind!=='Tx'||!f.richText)return unsupported('Field.defaultStyle assignment on plain field');if(!v||typeof v!=='object'||Array.isArray(v))throw Error('Invalid default style');const next=Object.assign({alignment:'left',fontFamily:['Helvetica'],fontStretch:'normal',fontStyle:'normal',fontWeight:400,textColor:['RGB',0,0,0],textSize:12},copyData(v));if(!Array.isArray(next.fontFamily)||!next.fontFamily.length||!Number.isFinite(Number(next.textSize))||Number(next.textSize)<0||!['left','center','right'].includes(next.alignment))throw Error('Invalid default style');next.textColor=richStyleColor(next.textColor);for(const key of ['underline','strikethrough']){if(next[key]===true||typeof next[key]==='number'&&next[key]!==0||next[key]==='true'||next[key]==='1')next[key]=key==='underline'?'underline':true;else delete next[key];}const font=fontName(next);styleBatch=true;try{f.textSize=Object.prototype.hasOwnProperty.call(v,'textSize')?Number(next.textSize):0;f.textFont=font;f.textColor=Object.prototype.hasOwnProperty.call(v,'textColor')?next.textColor:['G',0];f.alignment=next.alignment;f._defaultStyle=next;}finally{styleBatch=false;}reformat(f);}});
    for(const prop of ['textSize','textFont','richText','textColor','fillColor','strokeColor','alignment','lineWidth','borderStyle']){

      let stored=f[prop];Object.defineProperty(f,prop,{enumerable:true,get(){return prop==='textColor'?copyData(stored):stored},set(v){let next=prop==='richText'?!!v:v;let styleUpdate=null;if(prop==='textSize'){next=Number(v);if(!Number.isFinite(next)||next<0)throw Error('Invalid text size');styleUpdate={textSize:next};}else if(prop==='textFont'){next=String(v);const info=fontInfo(next);styleUpdate={fontFamily:[info.family,...f._defaultStyle.fontFamily.slice(1)],fontWeight:info.weight,fontStyle:info.style};}else if(prop==='textColor'){next=copyData(v);styleUpdate={textColor:richStyleColor(next)};}else if(prop==='alignment'){next=String(v);if(!['left','center','right'].includes(next))throw Error('Invalid alignment');styleUpdate={alignment:next};}if(JSON.stringify(next)!==JSON.stringify(stored)){gap('Field.'+prop+' appearance/persistence');revision++;}stored=next;if(styleUpdate){Object.assign(f._defaultStyle,styleUpdate);if(!styleBatch)reformat(f);}if(prop==='richText'){if(stored)f.value=f.valueAsString;else reformat(f);}}});
    }
    for(const prop of ['userName','submitName']){let stored=f[prop];Object.defineProperty(f,prop,{enumerable:true,get(){return stored},set(v){stored=String(v)}})}
    Object.defineProperty(f,'display',{enumerable:true,get(){return widgetDisplay(f,0)},set(v){displayFlags(v,4);f._fallbackDisplay=Number(v);for(let i=0;i<f._widgets.length;i++)setWidgetDisplay(f,i,v);}});
    for(const prop of ['readonly']){let stored=f[prop];Object.defineProperty(f,prop,{enumerable:true,get(){return stored},set(v){if(stored!==v)revision++;stored=v}})}
    Object.defineProperty(f,'editable',{enumerable:true,get(){return this.type==='combobox'&&!!(this._exportFlags&262144)},set(v){if(this.type!=='combobox')return unsupported('Field.editable on non-combobox');const next=v?(this._exportFlags|262144):(this._exportFlags&~262144);if(next!==this._exportFlags){this._exportFlags=next;revision++;}}});
    let raw=x.value,richInput,settingRich=false,importInput;
    f._richRaw=copyData(x.rich_value||(x.rich_metadata&&x.rich_metadata.spans)||[]);if(f.richText&&!f._richRaw.length&&String(raw))f._richRaw=normalizeRich(f,[{text:String(raw)}]);
    f._initialRichRaw=copyData(f._richRaw);
    Object.defineProperty(f,'richValue',{enumerable:true,get(){if(x.kind!=='Tx'||!f.richText)return invalidFieldGet();return copyData(f._richRaw)},set(v){if(x.kind!=='Tx'||!f.richText)return unsupported('Field.richValue assignment on plain field');if(typeof v==='string'){reformat(f);return;}if(!Array.isArray(v))return unsupported('Field.richValue non-array assignment');const previous=richInput,wasSetting=settingRich;richInput=copyData(v);settingRich=true;try{f.value=v.map(span=>textValue(f,span.text===undefined?'':span.text)).join('');}finally{richInput=previous;settingRich=wasSetting;}}});
    Object.defineProperty(f,'value',{enumerable:true,get(){return x.kind!=='Btn'&&typeof raw==='string'&&/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(raw)?Number(raw):raw},set(v){
      // Reader converts null/undefined to text, then runs the commit keystroke
      // and validation actions. Numeric MPMB fields reject that text themselves.
      // Text fields stringify arrays as comma-separated text, never JSON.
      if(v===undefined||v===null||(typeof v==='object'&&!(x.kind==='Ch'&&x.flags&2097152&&Array.isArray(v))))v=String(v);
      if(x.kind==='Btn'&&!(x.flags&65536)&&v==='')v='Off';
      if(typeof v==='string'&&x.kind==='Tx')v=textValue(f,v);
      // Explicit unchanged assignments to another field inside Calculate still
      // run its Format action synchronously in Reader (e.g. CalcAC display).
      // Internal calculation commits retain the existing end-of-pass refresh.
      if(!f.richText&&!importInput&&String(raw)===String(v)){reformat(f,calculating&&globalThis.event&&event.name==='Calculate'&&event.target!==f);return;}
      if(data.trace&&data.trace.includes(n))__log(n+': '+String(raw)+' -> '+String(v)+'\n'+new Error().stack);
      // Calculated mirrors can validate back into an active primary setter.
      // Preserve its guard until the outer commit returns, but run nested K/V/F.
      const nested=assigning.has(n),crossCalculation=calculating&&globalThis.event&&event.type==='Field'&&event.target!==f;
      if(nested&&!crossCalculation){raw=v;if(f.richText)f._richRaw=normalizeRich(f,[{text:String(v)}]);return}
      assigning.add(n);
      try {const original=v,text=String(v),input=settingRich?copyData(richInput):null;let k=eventRun(f,'K',text,undefined,f.richText?(importInput?(importInput.spans!==null?copyData(importInput.spans):(text?richChanges(text):null)):(settingRich?copyData(f._richRaw):(text?richChanges(text):null))):null);if(!k.rc){reformat(f);return;}let e=eventRun(f,'V',k.value,undefined,k._richData);if(e.rc){let committed=(f.type==='text'&&!f.richText&&f._actions.V&&!e._valueWritten)||String(e.value)===text?original:e.value;let spans;if(f.richText){if(e._valueWritten||k._valueWritten){spans=normalizeRich(f,[{text:String(e.value)}]);}else if(e._richWritten){spans=normalizeRich(f,e._richData);committed=textValue(f,richText(spans));}else if(importInput&&importInput.spans!==null){spans=copyData(importInput.spans);committed=textValue(f,richImportText(spans));}else {spans=normalizeRich(f,settingRich?input:[{text:String(e.value)}]);if(settingRich)committed=textValue(f,richText(spans));}}if(String(raw)!==String(committed))formatDirty.add(n);if(raw!==committed||spans&&JSON.stringify(spans)!==JSON.stringify(f._richRaw))revision++;if(spans&&JSON.stringify(spans)!==JSON.stringify(f._richRaw))gap('Field.richValue appearance/persistence');raw=committed;if(spans)f._richRaw=spans;f._formatted=undefined;f._formattedRichValue=undefined;if(globalThis.event&&event.target===f&&event.name==='Calculate')event.value=committed;if(globalThis.calculate&&globalThis.app&&app.calculate&&!calculating&&!importBatch)calculateNow();reformat(f,nested&&crossCalculation);}} finally{if(!nested)assigning.delete(n)}
    }});
    Object.defineProperty(f,'_importValue',{value(value,spans){const previous=importInput;importInput={spans};try{f.value=value}finally{importInput=previous}}});
    Object.defineProperty(f,'valueAsString',{get(){return String(raw)}});
    Object.defineProperty(f,'rect',{get(){return widgetRect(f,0)},set(r){setWidgetRect(f,0,r)}});
    Object.defineProperty(f,'currentValueIndices',{get(){const values=Array.isArray(f.value)?f.value:[f.value];const found=f.items.map((_,i)=>i).filter(i=>values.some(v=>String(v)===String(f.getItemAt(i,true))));return x.flags&2097152?found:found.length?found[0]:-1},set(v){const ids=Array.isArray(v)?v:[v];if(ids.some(i=>!Number.isInteger(Number(i))||Number(i)<0||Number(i)>=f.items.length))throw Error('Invalid choice index');f.value=x.flags&2097152?ids.map(i=>f.getItemAt(Number(i),true)):f.getItemAt(Number(ids[0]),true)}});
    Object.defineProperty(f,'page',{get(){const pages=f._widgets.map(w=>w.page);return pages.length>1?pages:pages.length?pages[0]:-1}});
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
      if(base){x.value=base.valueAsString;x.user_name=base.userName;x.submit_name=base.submitName;x.display=base.display;x.text_color=copyData(base.textColor);x.rich_value=copyData(base._richRaw);x.rich_metadata=Object.assign({},x.rich_metadata,{defaultStyle:copyData(base._defaultStyle),spans:copyData(base._richRaw)});}
      for(const w of x.widgets){if(base){const live=base._widgets.filter(source=>JSON.stringify(source.id)===JSON.stringify(w.id))[0];if(live&&live.flags!==undefined)w.flags=live.flags;}w.page=index;}
      if(rename){
        addField(prefix+n,x);
        if(base){fields[prefix+n]._formatted=base._formatted;fields[prefix+n]._formattedRichValue=copyData(base._formattedRichValue);}
      }else{if(!fields[n])throw Error('Missing shared template field '+n);fields[n]._widgets.push(...x.widgets);}
      // A template AP may predate its live value, including after reopening.
      // New widgets need appearances from the authoritative current display.
      fields[prefix+n]._appearanceDirty=true;

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
  function choiceEventFields(f,value){
    if(f.type!=='combobox'&&f.type!=='listbox')return {};
    const target=String(value);
    for(const item of f.items){
      if(Array.isArray(item)){
        const exp=String(item[0]),label=String(item.length>1?item[1]:item[0]);
        if(exp===target||label===target)return {change:label,changeEx:exp};
      }else if(String(item)===target){
        return {change:target,changeEx:target};
      }
    }
    return {};
  }
  function eventRun(f,key,value,extra,richInput) {
    let previous=globalThis.event;
    const choice=key==='K'?choiceEventFields(f,value):{};
    let e=Object.assign({target:f,targetName:f.name,source:importActive?null:(fields[data.focus]||f),name:({C:'Calculate',V:'Validate',K:'Keystroke',F:'Format',U:'Mouse Up',D:'Mouse Down',Fo:'Focus',Bl:'Blur'})[key]||key,type:'Field',value:['K','V','C','F'].includes(key)?String(value):value,rc:true,willCommit:key==='K',change:'',selStart:0,selEnd:0},choice,extra||{});
    let eventValue=e.value,valueWritten=false,richWritten=false;
    let richData=richInput===undefined?((key==='K'||key==='V')?(String(value)?richChanges(value):null):copyData(f._richRaw||[])):copyData(richInput);
    Object.defineProperty(e,'value',{enumerable:true,get(){return eventValue},set(v){if(['K','V','C','F'].includes(key)){if(typeof v!=='string'&&typeof v!=='number'){const error=new Error('Set not possible, invalid or unknown.');error.name='InvalidSetError';throw error;}v=String(v);}eventValue=v;valueWritten=true;}});
    Object.defineProperty(e,'richValue',{enumerable:true,get(){if(f.type!=='text'||!f.richText||!['K','V','C','F'].includes(key))return invalidFieldGet();return copyData(richData)},set(v){if(f.type!=='text'||!f.richText)return unsupported('Event.richValue on plain field');if(v!==null&&!Array.isArray(v))return unsupported('Event.richValue non-array assignment');richData=copyData(v);richWritten=true;}});
    Object.defineProperties(e,{_valueWritten:{get(){return valueWritten}},_richWritten:{get(){return richWritten}},_richData:{get(){return copyData(richData)}}});
    globalThis.event=e;
    try {if(f._actions[key]) (0,eval)(f._actions[key]);return e;}
    catch(err){let stack;try{stack=err==null?undefined:err.stack}catch(error){stack={getter_error:safeExceptionText(error)}}errors.push({stage:'field',field:f.name,event:key,error:safeExceptionText(err),stack:stack});if(['K','V','F'].includes(key)&&!unsupportedErrors.has(err))return e;throw err}
    finally {globalThis.event=previous;}
  }
  function calculateNow() {
    // Explicit calls do not override either calculation-enable flag. Display
    // delay is independent: enabled calculations still run while drawing waits.
    if(!globalThis.calculate||!app.calculate)return;
    if(calculating){pending=true;return}
    calculating=true;
    // A setter refreshes its own Format action. Calculation commits defer that
    // refresh until the pass finishes; unchanged fields do not run commit hooks.
    try {let passes=0; do {pending=false;for(const n of data.order){if(n&&typeof n==='object'&&Array.isArray(n.reference))continue;let f=fields[n];if(!f)throw Error('Missing calculation target '+n);if(f._actions.C){const e=eventRun(f,'C',f.value);if(e.rc)f.value=e.value;}}if(++passes>8)throw Error('calculation did not settle');}while(pending);for(const n of names.slice()){const f=fields[n];if(f&&f._actions.F&&(data.order.includes(n)||(formatDirty.has(n)&&typeof f.value==='number'&&!f.richText)))formatResult(f,eventRun(f,'F',f.value));}formatDirty.clear();}finally{calculating=false}
  }
  // XFDF supplies incoming spans to K/V; direct richValue assignments expose
  // the previous spans instead. Validate each input shape before committing,
  // then defer automatic calculations until the document import is finished.
  function importXFDF(document) {
    if(document.cancelled){xfdfImports.push({cancelled:true});return;}
    const plan=[],ignored=[];
    for(const imported of document.fields){
      const f=fields[imported.name];if(!f){ignored.push(imported.name);continue;}
      if(!imported.values.length&&imported.rich_xml===null){if(f.type==='combobox'){plan.push({f,refresh:true});continue;}return unsupported('XFDF import field without a value: '+imported.name);}
      const spans=imported.rich_xml===null?null:JSON.parse(__xfdfRich(JSON.stringify({xml:imported.rich_xml,defaults:f._defaultStyle})));
      if(spans!==null&&!f.richText)return unsupported('XFDF rich import into a plain field: '+imported.name);
      if(imported.values.length>1&&!(f._exportFlags&2097152))return unsupported('XFDF multiple values for a single-value field: '+imported.name);
      const value=spans!==null?richImportText(spans):imported.values.length>1?imported.values:imported.values[0];
      plan.push({f,value,spans});
    }
    const before=revision,job={path:document.path,sha256:document.sha256,requested:document.fields.length,processed:0,ignored:ignored.length};
    xfdfImports.push(job);importActive++;importBatch++;let batchHeld=true;
    try{
      for(const item of plan){if(item.refresh)reformat(item.f);else item.f._importValue(item.value,item.spans);job.processed++;}
      importBatch--;batchHeld=false;
      if(!importBatch&&plan.length&&globalThis.calculate&&app.calculate&&!globalThis.delay)calculateNow();
      if(revision!==before)globalThis.dirty=true;
      job.changed=revision!==before;
    }catch(error){job.error=String(error);throw error;}
    finally{if(batchHeld)importBatch--;importActive--;}
  }
  function edit(n,v) {
    let f=fields[n];if(!f)throw Error('Unknown field '+n);if(f.readonly)throw Error('Read-only field '+n);
    data.focus=n;
    f.value=v;
    globalThis.dirty=true;return true;
  }
  function focusField(n,index){
    const f=n===null?null:fields[n];if(n!==null&&!f)throw Error('Unknown field '+n);
    if(f&&index===undefined){index=f._widgets.map(w=>w.page>=0).indexOf(true);if(index<0)index=0;}
    if(data.focus===n&&(!f||(data.focusWidget||0)===index))return;
    const previous=fields[data.focus];data.focus=null;data.focusWidget=0;
    if(previous)eventRun(previous,'Bl',previous.value);
    if(f){data.focus=n;data.focusWidget=index;const page=f._widgets[index]&&f._widgets[index].page;if(page>=0)globalThis.pageNum=page;eventRun(f,'Fo',f.value);}
  }
  // Applying the desktop editor completes a user edit, including leaving the
  // field. Programmatic edit/value assignment remains a separate operation.
  function userEdit(n,v){
    const index=data.focus===n?(data.focusWidget||0):undefined;
    focusField(n,index);edit(n,v);focusField(null);
    if(globalThis.calculate&&app.calculate)calculateNow();return true;
  }
  function activate(n,index=0,modifiers={}){
    const f=fields[n];if(!f)throw Error('Unknown field '+n);focusField(n,index);
    const mouse={shift:!!modifiers.shift,modifier:!!modifiers.modifier};
    eventRun(f,'D',f.value,mouse);
    if(!f.readonly&&(f.type==='checkbox'||f.type==='radiobutton'))f.checkThisBox(index,f.type==='radiobutton'||!f.isBoxChecked(index));
    eventRun(f,'U',f.value,mouse);if(globalThis.calculate&&app.calculate)calculateNow();
  }
  function pageWidgets(page){const result=[];for(const n of names){const f=fields[n];f._widgets.forEach((w,index)=>{const display=widgetDisplay(f,index);if(w.page===page&&display!==1&&display!==3)result.push({name:n,index,rect:w.rect,type:f.type,readonly:f.readonly})})}return result;}
  function advance(ms) {
    const target=clock+ms;let count=0;
    while(true){let due=Array.from(timers.values()).filter(t=>t.at<=target).sort((a,b)=>a.at-b.at||a.id-b.id)[0];if(!due)break;
      clock=due.at;timers.delete(due.id);if(++count>100)throw Error('timer budget exceeded');
      try{(0,eval)(due.code)}catch(e){errors.push({stage:'timer',code:due.code,error:String(e),stack:e.stack});throw e}
    }clock=target;
  }
  function execDialog(def) {

    const store={},enabled={},visible={},red={},controls=[];let ended=null,focus=null;
    // Acrobat popup-edit combos retain an option map for display, but store()
    // returns the selected key as text. Ordinary popups/lists return maps.
    function storedValues(){const result=JSON.parse(JSON.stringify(store));for(const c of controls){if(c.type==='edit_text'&&c.PopupEdit){const v=result[c.item_id];if(v&&typeof v==='object'){result[c.item_id]=c.SpinEdit?(Object.keys(v).filter(k=>Number(v[k])>0)[0]||''):'';}}}return result;}
    const dialog={load(x){for(const key of Object.keys(x)){const c=controls.filter(c=>c.item_id===key)[0],v=x[key];if(c&&c.type==='edit_text'&&c.PopupEdit&&((c.SpinEdit&&typeof v==='string')||(!c.SpinEdit&&v&&typeof v==='object'))){if(store[key]===undefined)store[key]='';continue;}store[key]=v;}},store:storedValues,enable(x){Object.assign(enabled,x)},visible(x){Object.assign(visible,x)},end(x){ended=x},
      setForeColorRed(id){red[String(id)]=true},focus(id){focus=id},setFocus(id){focus=id},insertEntryInList(o){for(const id of Object.keys(o))store[id]=Object.assign(store[id]||{},o[id])},removeAllEntriesFromList(id){store[id]={}},
    };
    // Reader constructs control values before initialize runs. Spin edits have
    // an intrinsic zero; plain/readonly edits ignore the descriptor's name.
    function collect(e){if(e.item_id){controls.push(e);if(e.type==='edit_text')store[e.item_id]=e.SpinEdit&&!e.PopupEdit&&!e.readonly?'0':'';else if(e.type==='static_text'||e.type==='link_text')store[e.item_id]=e.name===undefined?'':String(e.name);else if(e.type==='radio'||e.type==='check_box')store[e.item_id]=false;}(e.elements||[]).forEach(collect)}collect(def.description||{});
    if(def.initialize)def.initialize(dialog);
    function finish(result){if(def.destroy)def.destroy(dialog);return result;}
    for(let i=0;i<1000;i++) {
      const rendered=Object.assign({},store);
      for(const key of Object.keys(rendered)){const icon=iconData(rendered[key]);if(icon)rendered[key]=icon;}
      const reply=JSON.parse(__dialog(JSON.stringify({description:def.description,values:rendered,enabled,visible,red,focus})));
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
    def.description.elements=items.map(build).filter(Boolean);const result=execDialog(def);return Object.prototype.hasOwnProperty.call(choices,result)?choices[result]:null;
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
  return {activate,focusField,userEdit,pageWidgets,widgetDisplay,setWidgetDisplay,widgetRect,setWidgetRect,menuItems,popup,applyQualifiedRepairs,get revision(){return revision},recordError(e){errors.push(e)},fields,names,data,menus,gaps,errors,source,unsupported,gap,calculateNow,edit,advance,execDialog,invokeMenu,command,spawn,removeField,deletePages,importXFDF,
    consoleView(){return copyData(consoleState)},
    consoleVisible(visible){consoleState.visible=!!visible},
    consolePrint(message){consoleState.messages.push({document:data.file,text:message});__log(message)},
    consoleClear(){consoleState.messages.length=0},
    dataObjects(){return JSON.parse(JSON.stringify(data.attachments||[]))},
    exportDataObject(params){if(typeof params==='string')params={cName:params};const result=JSON.parse(__attachment(JSON.stringify(params)));attachmentExports.push(result);},
    print(params){const result=JSON.parse(__print(JSON.stringify({params,state:JSON.parse(__host.snapshot())})));printJobs.push(result);return undefined},
    ready(){let n=0;while(!globalThis.calculate||!app.calculate||globalThis.delay){let t=Array.from(timers.values()).sort((a,b)=>a.at-b.at)[0];if(!t||++n>100)throw Error('Document calculations suspended without a resumable timer');advance(Math.max(0,t.at-clock));}return true},
    snapshot(){let o={__structure:journal,__order:data.order},assets={};if(data.bookmarksChanged)o.__bookmarks=bookmarkRoot;for(const n of names){let f=fields[n];o[n]={value:Array.isArray(f.value)?f.value:f.valueAsString,icon:f._icon&&f._icon.asset?{asset:f._icon.asset.id}:f._icon,caption:f._caption,captions:f._captions,actions:f._modifiedActions,widgets:f._widgets,currentValueIndices:f.currentValueIndices,textSize:f.textSize,alignment:f.alignment,multiline:f.multiline,textColor:f.textColor,textFont:f.textFont,richText:f.richText,rawRichValue:copyData(f._richRaw),richValueChanged:!sameRich(f._richRaw,f._initialRichRaw),appearanceDirty:!!f._appearanceDirty,richValue:f.richText?(f._formattedRichValue===null?[]:copyData(f._formattedRichValue===undefined?f._richRaw:f._formattedRichValue)):[],richRenderActive:!!f.richText&&f._formattedRichValue!==null,defaultStyle:copyData(f._defaultStyle),formatted:f._formatted===undefined?f.valueAsString:f._formatted,display:f.display,userName:f.userName,submitName:f.submitName,readonly:f.readonly,editable:f.editable,items:f.items};if(f._icon&&f._icon.asset)assets[f._icon.asset.id]=f._icon.asset;}if(Object.keys(assets).length)o.__iconAssets=assets;return JSON.stringify(o)},
    timer(code,ms){let id=++timerId;timers.set(id,{id,code:String(code),at:clock+Math.max(1,Number(ms)||1)});return id},clear(id){timers.delete(id)},
    launchURL(url,newFrame=false){const target=String(url||'');if(!/^https?:\/\/[^\s\x00-\x1f]{1,4080}$/i.test(target))throw Error('Unsupported URL scheme: '+target);const record=typeof __launchUrl==='function'?JSON.parse(__launchUrl(target,!!newFrame)):{url:target,new_frame:!!newFrame,launched:false};launchedUrls.push(record);return undefined;},
    get pane(){return paneState},set pane(v){const next=String(v||'').toLowerCase();if(!['','bookmarks','thumbnails','layers','attachments','signatures'].includes(next))throw Error('Invalid document pane: '+v);paneState=next;},
    diagnostics(){return JSON.stringify({gaps,errors,repairs,printJobs,attachmentExports,xfdfImports,iconImports,launchedUrls,pane:paneState,console:consoleState,timers:timers.size,field_count:names.length,menus:Object.keys(menus)})}
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
var console={println(s){__host.consolePrint(String(s));return true},show(){__host.consoleVisible(true)},clear(){__host.consoleClear()}};
var global=globalThis.__nativeApplicationGlobal||{};
var __appState=globalThis.__nativeApplicationState||{};
var __monitors=(function(){
  const list=[{rect:[0,0,1920,1080],workRect:[0,0,1920,1040],isPrimary:true,colorDepth:32}];
  const copy=()=>list.map(m=>({rect:m.rect.slice(),workRect:m.workRect.slice(),isPrimary:m.isPrimary,colorDepth:m.colorDepth}));
  for(const fn of ['primary','desktop','largest','tallest','widest','bestColor'])Object.defineProperty(list,fn,{value:copy});
  Object.defineProperty(list,'nonDesktop',{value:()=>[]});
  return list;
})();
var app={viewerType:'Reader',viewerVersion:26,formsVersion:26,platform:'UNIX',language:'ENU',calculate:true,runtimeHighlight:false,monitors:__monitors,
  execDialog:__host.execDialog,
  launchURL(url,newFrame=false){return __host.launchURL(url,newFrame)},
  listMenuItems(){return [{cName:'File',oChildren:[{cName:'Open'},{cName:'Save'},{cName:'SaveAs'},{cName:'Close'}]},{cName:'Edit',oChildren:[]},{cName:'View',oChildren:[]},{cName:'Window',oChildren:[]},{cName:'Help',oChildren:[]}];},
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
  openDoc(request){
    if(typeof __openDocument!=='function')return __host.unsupported('app.openDoc');
    const o=typeof request==='string'?{cPath:request}:request;
    if(!o||typeof o.cPath!=='string'||!o.cPath)throw Error('openDoc requires a PDF path');
    for(const key of Object.keys(o))if(!['cPath','oDoc','bHidden'].includes(key))return __host.unsupported('app.openDoc '+key);
    const opened=__openDocument(o.cPath,o.oDoc||null);
    if(!o.bHidden)__host.gap('Additional PDF documents currently open in the background; separate document windows are unsupported');
    return opened;
  },
  browseForDoc(o={}){if(o.bSave)return __host.unsupported('app.browseForDoc save picker');if(typeof __browsePdf!=='function')return __host.unsupported('app.browseForDoc');const path=__browsePdf();return path===null?null:{cPath:path}},
  get activeDocs(){return typeof __activeDocuments==='function'?__activeDocuments():[globalThis]},
};
for(const name of ['calculate','runtimeHighlight','runtimeHighlightColor']){
  if(!(name in __appState))__appState[name]=app[name];
  Object.defineProperty(app,name,{enumerable:true,get(){return __appState[name]},set(value){__appState[name]=name==='runtimeHighlightColor'?value:!!value}});
}
if(!__appState.thermometer)__appState.thermometer=app.thermometer;
app.thermometer=__appState.thermometer;
var MPMBImportFunctions_isInstalled=typeof __openDocument==='function';
function MPMBOpenFile(doc,path,relative){
  if(!MPMBImportFunctions_isInstalled)return __host.unsupported('MPMBOpenFile');
  global.docTo=doc;global.docFrom=app.openDoc(relative?{cPath:path,oDoc:doc}:path);doc.bringToFront();
}
function MPMBImportPage(){return __host.unsupported('MPMBImportPage');}
var util={
  printf(fmt,...args){let i=0;return fmt.replace(/%([+0 ,]*)(\d*)(?:\.(\d+))?([dfsxX])/g,(m,flags,width,prec,type)=>{let v=args[i++];let s=type==='s'?String(v):type==='d'?String(Math.trunc(Number(v))):type==='f'?Number(v).toFixed(prec===undefined?6:Number(prec)):Number(v).toString(16);if(flags.includes('+')&&Number(v)>=0)s='+'+s;return s.padStart(Number(width)||0,flags.includes('0')?'0':' ')})},
  printd(fmt,date){let d=date||new Date();return String(fmt).replace(/yyyy|yy|mmmm|mmm|mm|dd|HH|MM|ss/g,t=>({yyyy:d.getFullYear(),yy:String(d.getFullYear()).slice(-2),mmmm:d.toLocaleString('en',{month:'long'}),mmm:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getMonth()],mm:String(d.getMonth()+1).padStart(2,'0'),dd:String(d.getDate()).padStart(2,'0'),HH:d.getHours(),MM:d.getMinutes(),ss:d.getSeconds()})[t])},
  scand(fmt,s){let d=new Date(s);return isNaN(d)?null:d},
  readFileIntoStream(path){return JSON.parse(__file(path||''))},stringFromStream(stream){if(!stream||typeof stream.data!=='string')throw Error('Invalid text stream');return stream.data},
  iconStreamFromIcon(icon){if(!icon||typeof icon!=='object')throw Error('Invalid icon');if(typeof __iconStream!=='function')return __host.unsupported('util.iconStreamFromIcon');const data=JSON.parse(__iconStream(JSON.stringify(icon)));return {count:0,width:data.width,height:data.height,read(n){const start=this.count,end=n===undefined?data.argb.length:Math.min(data.argb.length,start+Math.max(0,Number(n)||0));this.count=end;return data.argb.slice(start,end);}};},
};
function __pdfInfoDate(value){
  const m=/^(?:D:)?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?(?:([Z+-])(\d{2})?'?(\d{2})?'?)?$/.exec(String(value));
  if(!m)return new Date(NaN);
  const year=Number(m[1]),month=Number(m[2]||1)-1,day=Number(m[3]||1),hour=Number(m[4]||0),minute=Number(m[5]||0),second=Number(m[6]||0),zh=Number(m[8]||0),zm=Number(m[9]||0);
  if(month<0||month>11||day<1||day>31||hour>23||minute>59||second>59||zh>23||zm>59||(m[7]==='Z'&&(zh||zm)))return new Date(NaN);
  const date=new Date(0);
  if(m[7]){date.setUTCFullYear(year,month,day);date.setUTCHours(hour,minute,second,0);if(date.getUTCFullYear()!==year||date.getUTCMonth()!==month||date.getUTCDate()!==day)return new Date(NaN);return new Date(date.getTime()-(m[7]==='-'?-1:1)*(zh*60+zm)*60000)}
  date.setFullYear(year,month,day);date.setHours(hour,minute,second,0);return date;
}
function __docInfo(data){
  const standard=['Title','Author','Authors','ContactEmail','Subject','Keywords','Creator','Producer','CreationDate','ModDate','Trapped'];
  return new Proxy(data,{get(target,key,receiver){
    if(typeof key!=='string')return Reflect.get(target,key,receiver);
    const normalized=key.toLowerCase();
    for(const candidate of standard)if(candidate.toLowerCase()===normalized){const value=Object.prototype.hasOwnProperty.call(target,candidate)?target[candidate]:'';return value!==''&&(candidate==='CreationDate'||candidate==='ModDate')?__pdfInfoDate(value):Array.isArray(value)?value.slice():value}
    const value=Reflect.has(target,key)?Reflect.get(target,key,receiver):'';
    if(value==='true'||value==='false')return value==='true';
    // Reader accepts plain decimal metadata, but keeps exponents/whitespace text.
    // The final guard also rejects the trailing line terminators accepted by $.
    return typeof value==='string'&&/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$(?![\s\S])/.test(value)?Number(value):value;
  },set(){return __host.unsupported('Doc.info metadata mutation/persistence')},deleteProperty(){return __host.unsupported('Doc.info metadata mutation/persistence')},defineProperty(){return __host.unsupported('Doc.info metadata mutation/persistence')}});
}
Object.assign(globalThis,{
  toString(){return '[object Doc]'},
  closeDoc(discard=false){if(typeof __closeDocument!=='function')return __host.unsupported('Doc.closeDoc');return __closeDocument(!!discard)},
  bringToFront(){if(typeof __frontDocument!=='function')return __host.unsupported('Doc.bringToFront');return __frontDocument()},
  info:__docInfo(JSON.parse(__initial).info),documentFileName:JSON.parse(__initial).file,path:JSON.parse(__initial).path,
  numPages:JSON.parse(__initial).pages,numFields:__host.names.length,calculate:true,delay:false,dirty:false,pageNum:0,
  getField(n){if(globalThis.__nativeDocumentClosed)throw Error('Document is closed');n=String(n).replace(/\.{2,}/g,'.');if(__host.fields[n])return __host.fields[n];const selected=/^(.*)\.(\d+)$/.exec(n);if(selected&&__host.fields[selected[1]]){const base=__host.fields[selected[1]],index=Number(selected[2]);if(!base._widgets[index])return null;return new Proxy(base,{get(target,key){if(key==='page')return target._widgets[index].page;if(key==='display')return __host.widgetDisplay(target,index);if(key==='rect')return __host.widgetRect(target,index);if(key==='setFocus')return function(){__host.focusField(target.name,index);};return target[key]},set(target,key,value){if(key==='display')__host.setWidgetDisplay(target,index,value);else if(key==='rect')__host.setWidgetRect(target,index,value);else target[key]=value;return true}})}const prefix=String(n)+'.';let children=__host.names.filter(x=>x.startsWith(prefix));return children.length?new Proxy({name:n,getArray(){return children.map(x=>__host.fields[x])}},{get(o,k){return k in o?o[k]:__host.fields[children[0]][k]},set(o,k,v){for(const child of children)__host.fields[child][k]=v;return true}}):null},
  getDataObject(name){const found=__host.dataObjects().filter(d=>d.name===name);if(!found.length)throw Error('Unknown data object '+name);return found[0]},
  exportDataObject:__host.exportDataObject,
  exportAsXFDFStr(options={}){if(globalThis.__nativeDocumentClosed)throw Error('Document is closed');if(!options||typeof options!=='object'||Array.isArray(options))return __host.unsupported('Doc.exportAsXFDFStr positional options');return __xfdfExport(JSON.stringify({options,href:String(path||documentFileName||''),fields:__host.names.map(name=>{const f=__host.fields[name];return {name,type:f.type,flags:f._exportFlags,value:Array.isArray(f.value)?f.value:f.valueAsString,rich:f.richText?f._richRaw:null,defaultStyle:f._defaultStyle}})}))},
  importAnXFDF(path){if(globalThis.__nativeDocumentClosed)throw Error('Document is closed');if(path&&typeof path==='object')path=path.cPath;return __host.importXFDF(JSON.parse(__xfdfRead(path===undefined?'':String(path))))},
  importDataObject(){return __host.unsupported('Doc.importDataObject')},
  getNthFieldName(i){return __host.names[i]},calculateNow:__host.calculateNow,
  resetForm(list){if(typeof list==='string')list=[list];for(const n of __host.names){if(!list||list.some(x=>n===x||n.startsWith(x+'.')))__host.fields[n].value=__host.fields[n].defaultValue;}},
  getTemplate(n){return __host.data.templates&&__host.data.templates[n]?{name:n,spawn(index,rename,overlay){return __host.spawn(n,index,rename,overlay)}}:null},
  get templates(){return Object.keys(__host.data.templates||{}).map(n=>getTemplate(n))},
  removeField:__host.removeField,deletePages:__host.deletePages,
  getPrintParams(){return {firstPage:0,lastPage:numPages-1,interactive:0,DuplexType:1,constants:{interactionLevel:{full:0,automatic:1,silent:2},duplexTypes:{Simplex:1,DuplexFlipLongEdge:2,DuplexFlipShortEdge:3}}}},
  print(params){if(!params||typeof params!=='object')return __host.unsupported('Doc.print legacy arguments');return __host.print(params)},
});

Object.defineProperty(globalThis,'dataObjects',{get:__host.dataObjects});
Object.defineProperty(globalThis,'pane',{enumerable:true,get(){return __host.pane},set(v){__host.pane=v}});

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
