// Isolated rich-span property conversion; target K/V/F/C actions are cleared.
var iFileName='Rich decoration property types.js';
Value('User Script','');
(function(d){
  var f=d.getField('Extra.Notes'),r={cases:[],errors:[],sentinel:'\u00a0\u2028\ud83d\ude00'};
  ['Keystroke','Validate','Format','Calculate'].forEach(function(kind){f.setAction(kind,'')});f.richText=true;f.multiline=true;
  var variants=[['true',true],['false',false],['zero',0],['one',1],['two',2],['empty',''],['underline','underline'],['none','none'],['double','double'],['word','word'],['string_false','false'],['string_true','true'],['null',null],['undefined',undefined],['array',['underline']],['object',{}]];
  function read(){try{return {value:f.valueAsString,spans:f.richValue}}catch(e){return {getter_error:String(e)}}}
  ['underline','strikethrough'].forEach(function(property){
    for(var i=0;i<variants.length;i++){
      f.richValue=[{text:'seed'}];
      var row={property:property,label:variants[i][0],input_type:typeof variants[i][1],before:read(),error:null};
      try{var span={text:'probe '+i};span[property]=variants[i][1];f.richValue=[span]}catch(e){row.error={name:e.name,message:String(e)}}
      row.after=read();r.cases.push(row);
    }
  });
  Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(ch){return '\\u'+('0000'+ch.charCodeAt(0).toString(16)).slice(-4)}));
})(tDoc);
