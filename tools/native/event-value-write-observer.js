// Isolated event-value setter API diagnostic; original actions restored.
var iFileName='Event value write types.js';Value('User Script','');
(function(d){
 var r={cases:[],errors:[],sentinel:'\u00a0\u2028\ud83d\ude00'},player=d.getField('Player Name'),calc=d.getField('Str Mod');
 var original=d.__eventWriteOriginal,trace=[];
 d.__eventWriteObserve=function(){var row={trigger:d.__eventWriteTrigger,label:d.__eventWriteLabel,beforeType:typeof event.value,before:event.value};try{event.value=d.__eventWriteCandidate;row.afterType=typeof event.value;row.after=event.value}catch(e){row.error={name:e.name,message:String(e)};row.afterType=typeof event.value;row.after=event.value}trace.push(row)};
 try {
  var cases=[['negative',-1],['zero',0],['true',true],['false',false],['null',null],['undefined',undefined],['array',['A','Ω']],['object',{toString:function(){return 'object Ω'}}],['unicode-string','A\u00a0Ω'],['ascii-nbsp','A\u00a0B'],['decimal',1.25],['nan',NaN],['infinity',Infinity],['negative-infinity',-Infinity],['number-object',new Number(3)],['string-object',new String('Ω')],['throwing-object',{toString:function(){throw Error('conversion-called')}}]];
  ['Keystroke','Validate','Format','Calculate'].forEach(function(trigger){
   ['Keystroke','Validate','Format'].forEach(function(kind){player.setAction(kind,'')});calc.setAction('Calculate','');
   var f=trigger==='Calculate'?calc:player;f.setAction(trigger,'__eventWriteObserve()');
   cases.forEach(function(item,index){d.__eventWriteTrigger=trigger;d.__eventWriteLabel=item[0];d.__eventWriteCandidate=item[1];trace=[];if(trigger==='Calculate')d.calculateNow();else player.value='candidate '+trigger+' '+index;r.cases.push({trigger:trigger,label:item[0],trace:trace.slice(0)})});
  });
 }catch(e){r.errors.push({name:e.name,message:String(e)})}
 finally{['Keystroke','Validate','Format'].forEach(function(kind){player.setAction(kind,original.player[kind])});calc.setAction('Calculate',original.calc);delete d.__eventWriteObserve;delete d.__eventWriteOriginal;delete d.__eventWriteCandidate;delete d.__eventWriteTrigger;delete d.__eventWriteLabel;}
 Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(ch){return '\\u'+('0000'+ch.charCodeAt(0).toString(16)).slice(-4)}));
})(tDoc);
