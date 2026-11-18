(function(d){
 if(!d.__monk2024ConsoleSeen){console.println('MPMB 2024 Monk resource workflow console sentinel');d.__monk2024ConsoleSeen=true;}
 var known=classes.known.monk;
 if(!known||!ClassList.monk.features["monk's focus"]||ClassList.monk.features["monk's focus"].usages[8]!==9)throw Error('Expected original2024 Monk');
 var r={identity:{level:known.level,subclass:known.subclass},source:ClassList.monk.source,fields:{},resources:{},rows:[],calculation:{app:app.calculate,doc:d.calculate,delay:d.delay},errors:d.__styleErrors||[],weaponTrace:d.__monkWeaponTrace||[],weaponTraceOverflow:!!d.__monkWeaponTraceOverflow,sentinel:'\u00a0\u2028\ud83d\ude00'};
 ['Class and Levels','Character Level','Proficiency Bonus','Con','HP Max','Dex','Dex Mod','Wis','Wis Mod','AC','AC Armor Description','Attack.1.Weapon Selection','Attack.1.To Hit','Attack.1.Damage','Attack.1.Damage Type'].forEach(function(n){r.fields[n]=d.getField(n).valueAsString;});
 for(var i=0;i<d.numFields;i++){var name=d.getNthFieldName(i),m=/^Limited Feature (\d+)$/.exec(name);if(!m)continue;var row=m[1],label=d.getField(name).valueAsString;['Limited Feature '+row,'Limited Feature Max Usages '+row,'Limited Feature Used '+row,'Limited Feature Recovery '+row].forEach(function(k){r.resources[k]=d.getField(k).valueAsString;});if(label)r.rows.push({name:label,row:row,max:r.resources['Limited Feature Max Usages '+row],used:r.resources['Limited Feature Used '+row],recovery:r.resources['Limited Feature Recovery '+row]});}
 Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4);}));
})(tDoc);
