// Isolated plain-field commit behavior with explicit action/flag combinations.
// Original actions are restored; this is not an original MPMB workflow pass.
var iFileName='Post-event field commit observation.js';Value('User Script','');
(function(d){
 var original=d.__eventWriteOriginal,field=d.getField('Player Name'),calc=d.getField('Str Mod'),trace=[],r={cases:[],errors:[],sentinel:'\u00a0\u2028\ud83d\ude00'},appBefore=app.calculate,docBefore=d.calculate,oldPlayer=field.valueAsString,options=d.__eventProbeOptions||{},enabled=options.calculations===true,readStored=options.readStored===true;
 d.__postCommitObserve=function(phase){var row=[phase,event.name,event.value];if(readStored)row.push(event.target.valueAsString);trace.push(row)};
 d.__postCommitCalc=function(phase){trace.push([phase,'Calculate',event.value])};
 d.__postCommitAction=function(){var mode=d.__postCommitMode;
  if(event.name==='Keystroke'){if(mode.kWrite)event.value=d.__postCommitCandidate;if(mode.kReject)event.rc=false;}
  if(event.name==='Validate'){if(mode.v==='same')event.value=event.value;else if(mode.v==='replace')event.value='V '+d.__postCommitCandidate;else if(mode.v==='reject')event.rc=false;}
  if(event.name==='Format'&&mode.f==='write')event.value='display '+d.__postCommitCandidate;
 };
 try{
  var candidates=[['plain','K changed'],['ascii-nbsp','A\u00a0B'],['unicode-nbsp','A\u00a0Ω'],['linebreak','A\nB'],['ligatures','Aﬁﬂ']];
  var modes=[{name:'K-only',kWrite:true},{name:'K-V-observe',kWrite:true,v:'observe'},{name:'K-V-same',kWrite:true,v:'same'},{name:'K-V-replace',kWrite:true,v:'replace'},{name:'K-V-reject',kWrite:true,v:'reject'},{name:'K-F-observe',kWrite:true,f:'observe'},{name:'K-VF-observe',kWrite:true,v:'observe',f:'observe'},{name:'K-V-same-F',kWrite:true,v:'same',f:'observe'},{name:'V-write',v:'replace'},{name:'V-write-F',v:'replace',f:'observe'},{name:'K-reject',kWrite:true,kReject:true},{name:'F-write',v:'observe',f:'write'}];
   if(Array.isArray(options.modes))modes=modes.filter(function(mode){return options.modes.indexOf(mode.name)!==-1});
   if(Array.isArray(options.labels))candidates=candidates.filter(function(item){return options.labels.indexOf(item[0])!==-1});
   if(options.observeCalculation)calc.setAction('Calculate',"__postCommitCalc('before');"+original.calc+";__postCommitCalc('after');");
   modes.forEach(function(mode){candidates.forEach(function(candidate,index){
    ['Keystroke','Validate','Format'].forEach(function(kind){field.setAction(kind,'')});app.calculate=enabled;d.calculate=enabled;field.value='seed '+mode.name+' '+index;
    d.__postCommitMode=mode;d.__postCommitCandidate=candidate[1];
    ['Keystroke','Validate','Format'].forEach(function(kind){var installed=kind==='Keystroke'||kind==='Validate'&&mode.v||kind==='Format'&&mode.f;field.setAction(kind,installed?"__postCommitObserve('before');__postCommitAction();__postCommitObserve('after');":'')});
    trace=[];field.value='candidate '+mode.name+' '+index;
    r.cases.push({calculations:enabled,readStored:readStored,mode:mode.name,label:candidate[0],trace:trace.slice(0),stored:field.valueAsString});
   })});
 }catch(e){r.errors.push({name:e.name,message:String(e)})}
 finally{if(options.observeCalculation)calc.setAction('Calculate',original.calc);['Keystroke','Validate','Format'].forEach(function(kind){field.setAction(kind,original.player[kind])});field.value=oldPlayer;app.calculate=appBefore;d.calculate=docBefore;if(appBefore&&docBefore)d.calculateNow();delete d.__postCommitCalc;delete d.__postCommitObserve;delete d.__postCommitAction;delete d.__postCommitMode;delete d.__postCommitCandidate;delete d.__eventWriteOriginal;delete d.__eventProbeOptions;}
 Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(ch){return '\\u'+('0000'+ch.charCodeAt(0).toString(16)).slice(-4)}));
})(tDoc);
