(function(d){
 d.__fighterAdditionalCapture=function(){
  if(!d.__bodyMindConsoleSeen){console.println('MPMB 2024 Monk Body and Mind workflow sentinel');d.__bodyMindConsoleSeen=true;}
  var names=['Character Level','Dex','Wis','Dex Mod','Wis Mod','AC','Attack.1.To Hit','Attack.1.Damage'],fields={};
  for(var i=0;i<names.length;i++)fields[names[i]]=d.getField(names[i]).valueAsString;
  var r={fields:fields,stats:CurrentStats,calculation:{app:app.calculate,doc:d.calculate,delay:d.delay},errors:d.__styleErrors||[],scriptFiles:typeof CurrentScriptFiles==='object'?Object.keys(CurrentScriptFiles):[],sentinel:'\u00a0\u2028\ud83d\ude00'};
  Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4);}));
 };
})(tDoc);
