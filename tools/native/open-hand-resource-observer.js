(function(d){
 d.__fighterAdditionalCapture=function(){
 if(!d.__openHandConsoleSeen){console.println('2024 Open Hand resource sentinel');d.__openHandConsoleSeen=true;}
 var k=classes.known.monk;
 var r={identity:k?{level:k.level,subclass:k.subclass}:null,fields:{},rows:[],resources:{},calculation:{app:app.calculate,doc:d.calculate,delay:d.delay},errors:d.__styleErrors||[],sentinel:'\u00a0\u2028\ud83d\ude00'};
 ['Class and Levels','Character Level','Proficiency Bonus','Wis','Wis Mod','Dex','Dex Mod','AC','HP Max'].forEach(function(n){r.fields[n]=d.getField(n).valueAsString;});
 for(var i=0;i<d.numFields;i++){var n=d.getNthFieldName(i),m=/^Limited Feature (\d+)$/.exec(n);if(!m)continue;var row=m[1];['Limited Feature '+row,'Limited Feature Max Usages '+row,'Limited Feature Used '+row,'Limited Feature Recovery '+row].forEach(function(n){r.resources[n]=d.getField(n).valueAsString;});var label=r.resources[n];if(label)r.rows.push({row:row,name:label,max:r.resources['Limited Feature Max Usages '+row],used:r.resources['Limited Feature Used '+row],recovery:r.resources['Limited Feature Recovery '+row],calcOrderIndex:d.getField('Limited Feature Max Usages '+row).calcOrderIndex});}
 Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4);}));
 };
})(tDoc);
