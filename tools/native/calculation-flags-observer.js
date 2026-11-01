// Isolated explicit calculateNow behavior under application/document/delay flags.
var iFileName='Explicit calculation flags.js';
Value('User Script','');
(function(d){
 var f=d.getField('Extra.Notes'),r={cases:[],errors:[],sentinel:'\u00a0\u2028\ud83d\ude00'};
 var before={app:app.calculate,doc:d.calculate,delay:d.delay};
 ['Keystroke','Validate','Format','Calculate'].forEach(function(k){f.setAction(k,'')});f.richText=false;f.value='seed';
 d.__calculationFlagCount=0;f.setAction('Calculate',"tDoc.__calculationFlagCount++;event.value=String(tDoc.__calculationFlagCount);");
 try{
  for(var appFlag=0;appFlag<2;appFlag++)for(var docFlag=0;docFlag<2;docFlag++)for(var delayFlag=0;delayFlag<2;delayFlag++){
   app.calculate=!!appFlag;d.calculate=!!docFlag;d.delay=!!delayFlag;d.__calculationFlagCount=0;
   var row={app:app.calculate,doc:d.calculate,delay:d.delay,before:f.valueAsString};
   d.calculateNow();row.count=d.__calculationFlagCount;row.after=f.valueAsString;r.cases.push(row);
  }
 }catch(e){r.errors.push({name:e.name,message:String(e)})}
 f.setAction('Calculate','');app.calculate=before.app;d.calculate=before.doc;d.delay=before.delay;
 Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));
})(tDoc);
