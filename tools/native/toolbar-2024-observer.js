(function(d){
 if(!d.__toolbar2024ConsoleSeen){console.println('MPMB 2024 toolbar parity console sentinel');d.__toolbar2024ConsoleSeen=true;}
 function safe(fn){try{return fn();}catch(e){return {__error:String(e)};}}
 function codeUnits(s){var out=[];s=String(s||'');for(var i=0;i<s.length;i++)out.push(s.charCodeAt(i));return out;}
 var alList=(d.getField('Template.extras.ALlog')?d.getField('Template.extras.ALlog').valueAsString:'').split(',').slice(1);
 var alPre=alList.length?alList[0]:'';
 var preMobile={
  active:!!(typeof CurrentVars==='object'&&CurrentVars&&CurrentVars.mobileset&&CurrentVars.mobileset.active),
  pcNameReadonly:safe(function(){return d.getField('PC Name').readonly;})
 };
 if(d.getField('Notes.Left')&&!d.getField('Notes.Left').valueAsString){
  safe(function(){ColoryOptions(['color','highlights','adobe default']);});
  d.getField('Notes.Left').value=toUni('Bold2024','bold')+' \ud83d\udd25';
  safe(function(){MakeMobileReady(true);});
 }else if(preMobile.active){
  safe(function(){MakeMobileReady(false);});
 }
 var notesVal=safe(function(){return d.getField('Notes.Left')?d.getField('Notes.Left').valueAsString:'';});
 var d1=safe(function(){var dt=util.scand('yyyy-mm-dd hh:MM tt','2024-03-05 01:30 pm');return dt?util.printd('yyyy-mm-dd HH:MM',dt):null;});
 var d2=safe(function(){var dt=util.scand('ddd, d mmm yyyy','Tue, 5 Mar 2024');return dt?util.printd('yyyy-mm-dd',dt):null;});
 var refDt=new Date(2024,2,5,13,30,0);
 var r={
  apis:{
   printf:[
    safe(function(){return util.printf('%,0.2f',1234.5);}),
    safe(function(){return util.printf('%,2.1f',1234.5);}),
    safe(function(){return util.printf('%,0+08.2f',1234.5);}),
    safe(function(){return util.printf('%#.0f',1);})
   ],
   scand:{ampm:d1,weekday:d2},
   dateToSourceRoundtrip:safe(function(){var rt=eval_ish(refDt.toSource());return rt instanceof Date&&rt.getTime()===refDt.getTime();}),
   monitorsPrimaryValid:safe(function(){var mp=app.monitors.primary();return !!(mp&&mp[0]&&mp[0].rect&&mp[0].rect.length===4&&mp[0].rect[3]>0);}),
   iconStreamValid:safe(function(){var ic=d.getField('SaveIMG.Patreon').buttonGetIcon();var st=util.iconStreamFromIcon(ic);var hex=st&&typeof st.read==='function'?st.read(16):'';return typeof hex==='string'&&hex.length>0;}),
   factionEditable:safe(function(){return d.getField('Background_Faction.Text').editable;})
  },
  alLog:{
   prefix:alPre,
   dateFormat:safe(function(){return What('DateFormat_Remember');}),
   decimalSep:safe(function(){return What('Decimal Separator');}),
   dateValue:alPre?safe(function(){return d.getField(alPre+'AdvLog.1.date').valueAsString;}):'',
   goldValue:alPre?safe(function(){return d.getField(alPre+'AdvLog.1.gold.gain').valueAsString;}):''
  },
  highlightingFill:safe(function(){
   var c=d.getField('Highlighting').fillColor;
   if(!Array.isArray(c))return c;
   return c.map(function(x){return typeof x==='number'?Math.round(x*10000)/10000:x;});
  }),
  notesLeft:{
   value:notesVal,
   codeUnits:typeof notesVal==='string'?codeUnits(notesVal):[]
  },
  preMobile:preMobile,
  mobile:{
   active:!!(typeof CurrentVars==='object'&&CurrentVars&&CurrentVars.mobileset&&CurrentVars.mobileset.active),
   pcNameReadonly:safe(function(){return d.getField('PC Name').readonly;})
  },
  pages:d.numPages,
  calculation:{app:app.calculate,doc:d.calculate,delay:d.delay},
  errors:d.__workflowErrors||[],
  sentinel:'\u00a0\u2028\ud83d\ude00'
 };
 Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4);}));
})(tDoc);
