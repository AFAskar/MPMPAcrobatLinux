// Read the actual picker-imported fields through the original RunUserScript entry.
var iFileName='XFDF picker retained state.js';
Value('User Script','');
(function(d){
  var r={fields:[],errors:[],sentinel:'\u00a0\u2028\ud83d\ude00'};
  var names=['Player Name','Notes.Left'];
  for(var i=0;i<names.length;i++){
    try {
      var f=d.getField(names[i]);
      r.fields.push({name:f.name,type:f.type,value:f.valueAsString,rich:f.richText?f.richValue:null});
    } catch(e) {r.errors.push({field:names[i],name:e.name,message:String(e)});}
  }
  Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(ch){return '\\u'+('0000'+ch.charCodeAt(0).toString(16)).slice(-4)}));
})(tDoc);
