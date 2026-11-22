(function(d){
 if(!d.__class2014ConsoleSeen){console.println('MPMB 2014 comprehensive class workflow console sentinel');d.__class2014ConsoleSeen=true;}
 var known={};
 for(var ck in classes.known){if(Object.prototype.hasOwnProperty.call(classes.known,ck))known[ck]={level:classes.known[ck].level,subclass:classes.known[ck].subclass||''};}
 var r={
  identity:known,
  race:{known:(typeof CurrentRace==='object'&&CurrentRace&&CurrentRace.known)||'',name:d.getField('Race')?d.getField('Race').valueAsString:''},
  background:{known:(typeof CurrentBackground==='object'&&CurrentBackground&&CurrentBackground.known)||'',name:d.getField('Background')?d.getField('Background').valueAsString:''},
  choices:(typeof CurrentFeatureChoices==='object'&&CurrentFeatureChoices)?JSON.parse(JSON.stringify(CurrentFeatureChoices)):{},
  fields:{},
  resources:{},
  rows:[],
  spells:{},
  spellSlots:{},
  notesAndActions:{},
  pages:d.numPages,
  templates:{
   SSfront:d.getField('Template.extras.SSfront')?d.getField('Template.extras.SSfront').valueAsString:'',
   SSmore:d.getField('Template.extras.SSmore')?d.getField('Template.extras.SSmore').valueAsString:'',
   WSfront:d.getField('Template.extras.WSfront')?d.getField('Template.extras.WSfront').valueAsString:'',
   AScomp:d.getField('Template.extras.AScomp')?d.getField('Template.extras.AScomp').valueAsString:''
  },
  calculation:{app:app.calculate,doc:d.calculate,delay:d.delay},
  errors:d.__workflowErrors||[],
  unavailable:[],
  sentinel:'\u00a0\u2028\ud83d\ude00'
 };
 function readField(map,name){
  var f=d.getField(name);
  if(!f)return;
  try{map[name]=f.valueAsString;}catch(e){r.unavailable.push({field:name,error:String(e)});}
 }
 ['Class and Levels','Character Level','Proficiency Bonus','Race','Background',
  'Str','Str Mod','Dex','Dex Mod','Con','Con Mod','Int','Int Mod','Wis','Wis Mod','Cha','Cha Mod',
  'HP Max','HD1 Level','HD1 Die','HD2 Level','HD2 Die','AC','AC Armor Description','Initiative bonus','Speed',
  'Str ST Mod','Dex ST Mod','Con ST Mod','Int ST Mod','Wis ST Mod','Cha ST Mod',
  'Attack.1.Weapon Selection','Attack.1.To Hit','Attack.1.Damage','Attack.1.Damage Type',
  'Attack.2.Weapon Selection','Attack.2.To Hit','Attack.2.Damage','Attack.2.Damage Type',
  'Feat Name 1','Feat Name 2','Feat Name 3','Background_Faction.Text',
  'Stealth','Perception','Arcana','Athletics','Acrobatics','Sleight of Hand'
 ].forEach(function(n){readField(r.fields,n);});
 ['Class Features','Racial Traits','Background Feature','Extra.Notes'
 ].forEach(function(n){readField(r.notesAndActions,n);});
 var wsParts=(r.templates.WSfront||'').split(',');
 if(wsParts.length>1){var wsPre=wsParts[1];['Wildshape.Race.1','Wildshape.1.AC','Wildshape.1.Ability.Str.Score'].forEach(function(n){readField(r.notesAndActions,wsPre+n);});}
 var compParts=(r.templates.AScomp||'').split(',').slice(1);
 if(compParts.length){var compPre=compParts[compParts.length-1];['Comp.Race','Comp.Desc.Name','Comp.Use.AC','Comp.Use.HP.Max'].forEach(function(n){readField(r.notesAndActions,compPre+n);});}
 for(var i=0;i<d.numFields;i++){
  var name=d.getNthFieldName(i);
  var m=/^Limited Feature (\d+)$/.exec(name);
  if(m){
   var row=m[1],label=d.getField(name).valueAsString;
   ['Limited Feature '+row,'Limited Feature Max Usages '+row,'Limited Feature Used '+row,'Limited Feature Recovery '+row].forEach(function(k){readField(r.resources,k);});
   if(label)r.rows.push({name:label,row:row,max:r.resources['Limited Feature Max Usages '+row],used:r.resources['Limited Feature Used '+row],recovery:r.resources['Limited Feature Recovery '+row]});
  }
 }
 ['Pact Magic','SpellSlots.CheckboxesSet.lvl1','SpellSlots.CheckboxesSet.lvl2','SpellSlots.CheckboxesSet.lvl3','SpellSlots.CheckboxesSet.lvl4','SpellSlots.CheckboxesSet.lvl5','SpellSlots.CheckboxesSet.lvl6','SpellSlots.CheckboxesSet.lvl7','SpellSlots.CheckboxesSet.lvl8','SpellSlots.CheckboxesSet.lvl9'].forEach(function(n){readField(r.spellSlots,n);});
 if(typeof CurrentSpells==='object'&&CurrentSpells){
  for(var sk in CurrentSpells){
   if(!Object.prototype.hasOwnProperty.call(CurrentSpells,sk))continue;
   var cs=CurrentSpells[sk];
   if(!cs||typeof cs!=='object')continue;
   r.spells[sk]={
    name:cs.name||'',
    ability:cs.ability||0,
    knownCantrips:Array.isArray(cs.selectCa)?cs.selectCa.length:0,
    knownSpells:Array.isArray(cs.selectSp)?cs.selectSp.length:0,
    bonusCount:cs.bonus?Object.keys(cs.bonus).length:0
   };
  }
 }
 Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4);}));
})(tDoc);
