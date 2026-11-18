(function(d){
 d.__fighterAdditionalCapture=function(){
  if(!d.__shadowSpellsConsoleSeen){console.println('MPMB 2024 Shadow Monk spells workflow sentinel');d.__shadowSpellsConsoleSeen=true;}
  var prefixes=What('Template.extras.SSfront').split(',').filter(Boolean),more=What('Template.extras.SSmore').split(',').filter(Boolean),r={fields:{},resources:{},spells:CurrentSpells,spellPages:[],diagnosticExclusions:['zAdvLog.PC Name'],rawPrefixes:prefixes.concat(more),pages:d.numPages,calculation:{app:app.calculate,doc:d.calculate,delay:d.delay},errors:d.__styleErrors||[],scriptFiles:Object.keys(CurrentScriptFiles),sentinel:'\u00a0\u2028\ud83d\ude00'};
  ['Class and Levels','Character Level','Proficiency Bonus','Dex','Wis','Dex Mod','Wis Mod','AC'].forEach(function(n){r.fields[n]=d.getField(n).valueAsString;});
  for(var j=0;j<r.rawPrefixes.length;j++)r.spellPages.push({fields:{},page:d.getField(r.rawPrefixes[j]+'spells.name.0').page});
  for(var i=0;i<d.numFields;i++){
   var n=d.getNthFieldName(i),f=d.getField(n);
   if(/^Limited Feature (\d+|Max Usages \d+|Used \d+|Recovery \d+)$/.test(n))r.resources[n]=f.valueAsString;
   for(var p=0;p<r.rawPrefixes.length;p++)if(n.indexOf(r.rawPrefixes[p])===0&&f.type!=='button'&&n!==r.rawPrefixes[p]+'zAdvLog.PC Name')r.spellPages[p].fields[n.slice(r.rawPrefixes[p].length)]=f.valueAsString;
  }
  Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4);}));
 };
})(tDoc);
