// Isolated default-style and immediate event decoration conversion.
var iFileName='Rich decoration boundaries.js';
Value('User Script','');
(function(d){
 var f=d.getField('Extra.Notes'),r={defaults:[],events:[],errors:[],sentinel:'\u00a0\u2028\ud83d\ude00'};
 ['Keystroke','Validate','Format','Calculate'].forEach(function(k){f.setAction(k,'')});f.richText=true;f.multiline=true;
 var base=f.defaultStyle;
 var defaultModes=[true,false,0,1,2,-1,0.5,'1','2','true','underline','none',null,undefined,[1],{}];
 var modes=[true,false,'underline','none','double','word','',1];
 for(var i=0;i<defaultModes.length;i++){
  var style={};for(var k in base)style[k]=base[k];style.underline=defaultModes[i];style.strikethrough=defaultModes[i];
  var row={index:i,input:defaultModes[i],error:null};
  try{f.defaultStyle=style;row.style=f.defaultStyle;f.richValue=[{text:'inherited'}];row.inherited=f.richValue;f.richValue=[{text:'overridden',underline:false,strikethrough:false}];row.overridden=f.richValue}catch(e){row.error={name:e.name,message:String(e)}}r.defaults.push(row);
 }
 f.defaultStyle=base;
 r.combinations=[];
 ['none','',false,'double','word'].forEach(function(mode){[true,false].forEach(function(strike){
  f.richValue=[{text:'combination',underline:mode,strikethrough:strike}];r.combinations.push({underline:mode,strikethrough:strike,spans:f.richValue});
 })});
 d.__decorationTrace=r.events;
 ['Keystroke','Validate','Format','Calculate'].forEach(function(kind){
  for(var i=0;i<modes.length;i++){
   ['Keystroke','Validate','Format','Calculate'].forEach(function(k){f.setAction(k,'')});
   f.richValue=[{text:'seed'}];d.__decorationMode=modes[i];
   f.setAction(kind,"var row={kind:event.name,input:tDoc.__decorationMode,before:event.richValue};event.richValue=[{text:'event',underline:tDoc.__decorationMode,strikethrough:tDoc.__decorationMode}];row.after=event.richValue;tDoc.__decorationTrace.push(row);");
   if(kind==='Calculate'){f.calcOrderIndex=0;d.calculateNow();}else f.value='trigger';
  }
 });
 ['Keystroke','Validate','Format','Calculate'].forEach(function(k){f.setAction(k,'')});
 Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));
})(tDoc);
