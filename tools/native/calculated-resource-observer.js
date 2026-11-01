// Original AddFeature/RemoveFeature persistence; never installs expected maxima.
var iFileName='Calculated resource persistence.js';
Value('User Script','');
(function(d){
 var label='Compatibility Calculated Resource',phase=d.__resourcePhase||'create';
 var r={phase:phase,before:null,after:null,errors:[],sentinel:'\u00a0\u2028\ud83d\ude00'};
 function locate(){for(var i=1;i<=FieldNumbers.limfea;i++)if(What('Limited Feature '+i)===label)return i;return 0}
 function capture(){
  var row=locate(),fields={},names=['Class and Levels','Character Level','Proficiency Bonus','Wis','Wis Mod'];
  for(var i=1;i<=FieldNumbers.limfea;i++)if(What('Limited Feature '+i))['Limited Feature ','Limited Feature Max Usages ','Limited Feature Recovery ','Limited Feature Used '].forEach(function(prefix){names.push(prefix+i)});
  for(var n=0;n<names.length;n++)fields[names[n]]=d.getField(names[n]).valueAsString;
  var usage=row?d.getField('Limited Feature Max Usages '+row):null;
  return {row:row,fields:fields,calculation:usage?usage.submitName:null,index:usage?usage.calcOrderIndex:-1};
 }
 try{
  r.before=capture();var row=locate();
  if(phase==='create'||phase==='readd'){
   if(row)throw Error('Resource already exists');
   AddFeature(label,0,'','long rest','Compatibility persistence','replace',"event.value=Number(What('Wis Mod'))+2;");
   row=locate();if(!row)throw Error('Original AddFeature did not add the resource');
   Value('Wis',phase==='create'?18:16);Value('Limited Feature Used '+row,phase==='create'?1:0);
  }else{
   if(!row)throw Error('Saved resource missing');
   if(d.getField('Limited Feature Max Usages '+row).calcOrderIndex<0)throw Error('Saved calculation is not registered');
   if(phase==='edit')Value('Wis',12);
   else if(phase==='edit-high'){Value('Wis',20);d.calculateNow();r.rests=[capture()];resetLimFeaUsed('short rest');r.rests.push(capture());resetLimFeaUsed('long rest');r.rests.push(capture());}
   else if(phase==='remove')RemoveFeature(label);
   else if(phase!=='read')throw Error('Unknown phase');
  }
  d.calculateNow();r.after=capture();
 }catch(e){r.errors.push({name:e.name,message:String(e)})}
 Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));
})(tDoc);
