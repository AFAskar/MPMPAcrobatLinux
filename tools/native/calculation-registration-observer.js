// Calculate action lifecycle, followed by original MPMB resource operations.
var iFileName='Calculation registration behavior.js';
Value('User Script','');
(function(d){
 var a=d.getField('Extra.Notes'),b=d.getField('Player Name');
 var r={states:[],events:[],resource:[],errors:[],sentinel:'\u00a0\u2028\ud83d\ude00'};
 d.__registrationEvents=r.events;
 function state(label){r.states.push({label:label,a:{index:a.calcOrderIndex,value:a.valueAsString},b:{index:b.calcOrderIndex,value:b.valueAsString},events:r.events.slice()})}
 function step(label,fn){try{fn();state(label)}catch(e){r.errors.push({phase:label,name:e.name,message:String(e)})}}
 ['Keystroke','Validate','Format','Calculate'].forEach(function(k){a.setAction(k,'');b.setAction(k,'')});a.richText=false;a.value='seed A';b.value='seed B';state('cleared');
 step('register A',function(){a.setAction('Calculate',"tDoc.__registrationEvents.push('A');event.value='calculated A';")});
 step('register B',function(){b.setAction('Calculate',"tDoc.__registrationEvents.push('B');event.value='calculated B';")});
 step('calculate A B',function(){d.calculateNow()});
 step('remove A',function(){a.setAction('Calculate','')});
 step('calculate B',function(){d.calculateNow()});
 step('readd A',function(){a.setAction('Calculate',"tDoc.__registrationEvents.push('A2');event.value='readded A';")});
 step('replace B',function(){b.setAction('Calculate',"tDoc.__registrationEvents.push('B2');event.value='replaced B';")});
 step('calculate B A',function(){d.calculateNow()});
 step('clear both',function(){a.setAction('Calculate','');b.setAction('Calculate','')});
 // Exercise the original AddFeature path, which installs a Calculate action.
 var label='Compatibility Calculation Resource',number=0;
 for(var n=1;n<=FieldNumbers.limfea;n++)if(!What('Limited Feature '+n)){number=n;break}
 function resource(phase){r.resource.push({phase:phase,row:number,label:What('Limited Feature '+number),maximum:What('Limited Feature Max Usages '+number),index:d.getField('Limited Feature Max Usages '+number).calcOrderIndex,wisdom:What('Wis'),modifier:What('Wis Mod')})}
 try{
  if(!number)throw Error('No empty resource row');resource('before');
  AddFeature(label,0,'','long rest','Compatibility probe','replace',"event.value=Number(What('Wis Mod'))+2;");
  for(var n=1;n<=FieldNumbers.limfea;n++)if(What('Limited Feature '+n)===label){number=n;break}
  Value('Wis',18);d.calculateNow();resource('Wisdom18');
  Value('Wis',12);d.calculateNow();resource('Wisdom12');
  RemoveFeature(label);d.calculateNow();resource('removed');
 }catch(e){r.errors.push({phase:'original resource',name:e.name,message:String(e)})}
 r.assertions={newCalculateExecuted:r.events.indexOf('A')>=0&&r.events.indexOf('B')>=0,replacedCalculateExecuted:r.events.indexOf('A2')>=0&&r.events.indexOf('B2')>=0,resourceDerived:r.resource.length===4&&String(r.resource[1].maximum)==='6'&&String(r.resource[2].maximum)==='3',resourceRemoved:r.resource.length===4&&r.resource[3].label!==label,noErrors:r.errors.length===0};
 Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));
})(tDoc);
