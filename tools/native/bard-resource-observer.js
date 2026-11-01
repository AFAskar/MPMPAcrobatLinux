// Original Bard class and ability-dependent inspiration with retained choices.
var iFileName='Bard instrument and resource behavior.js';
Value('User Script','');
(function(d){
 var phase=d.__bardPhase||'create',r={phase:phase,states:[],errors:[],sentinel:'\u00a0\u2028\ud83d\ude00'};
 function capture(label){
  var names=['Class and Levels','Character Level','Proficiency Bonus','Cha','Cha Mod','MoreProficiencies'],fields={},resource=null,tools=[];
  for(var i=1;i<=6;i++){names.push('Tool '+i);tools.push(d.getField('Tool '+i).valueAsString)}
  for(var i=1;i<=9;i++)names.push('SpellSlots.CheckboxesSet.lvl'+i);
  for(var i=1;i<=FieldNumbers.limfea;i++)if(/bardic inspiration/i.test(What('Limited Feature '+i))){
   ['Limited Feature ','Limited Feature Max Usages ','Limited Feature Recovery ','Limited Feature Used '].forEach(function(prefix){names.push(prefix+i)});
   var f=d.getField('Limited Feature Max Usages '+i);resource={row:i,index:f.calcOrderIndex,calculation:f.submitName,maximum:f.valueAsString,used:d.getField('Limited Feature Used '+i).valueAsString};
  }
  for(var i=0;i<names.length;i++){var f=d.getField(names[i]);if(f)fields[names[i]]=f.valueAsString}
  var state={label:label,fields:fields,tools:tools,resource:resource};r.states.push(state);return state;
 }
 try{
  capture('before');
  if(phase==='create'){
   Value('Cha',18);ApplyClasses('Bard 1',false);
   // The caller yields the document menu and waits for original calcCont.
   // Intermediate class state is recorded without forcing pending calculations.
   capture('class update submitted');
  }else if(phase==='edit'){
   Value('Cha',16);d.calculateNow();capture('Charisma16');
  }else if(phase!=='read')throw Error('Unknown Bard phase');
  var state=capture('final'),all=state.tools.join('|').toLowerCase();
  r.assertions={levelOne:state.fields['Character Level']==='1',registered:!!state.resource&&state.resource.index>=0,flute:all.indexOf('flute')>=0,lute:all.indexOf('lute')>=0,drum:all.indexOf('drum')>=0};
 }catch(e){r.errors.push({name:e.name,message:String(e)})}
 Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));
})(tDoc);
