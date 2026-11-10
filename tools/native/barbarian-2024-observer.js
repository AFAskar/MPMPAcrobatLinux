// Diagnostic observer; installation must not re-run the all-sources add-on.
(function (d) {
    if(!d.__barbarian2024ConsoleSeen){console.println('MPMB 2024 Barbarian workflow console sentinel');d.__barbarian2024ConsoleSeen=true;}
    var k = classes.known.barbarian;
    var r = {identity: {level:k.level, subclass:k.subclass},
        subclassDefinition: {name:ClassSubList[k.subclass].subname, source:ClassSubList[k.subclass].source},
        choices:CurrentFeatureChoices, fields:{}, resources:{}, reactions:{},
        calculation:{app:app.calculate, doc:d.calculate, delay:d.delay},
        errors:d.__styleErrors || [], sentinel:'\u00a0\u2028\ud83d\ude00'};
    ['Class and Levels','Character Level','Proficiency Bonus','HP Max',
     'Str','Dex','Con','Str Mod','Dex Mod','Con Mod','AC',
     'AC Armor Bonus','AC Armor Description','AC Dexterity Modifier',
     'AC Shield Bonus','AC Shield Bonus Description',
     'Attack.1.Weapon Selection','Attack.1.To Hit','Attack.1.Damage',
     'Attack.1.Description','Class Features','Extra.Notes'].forEach(function(n){r.fields[n]=d.getField(n).valueAsString;});
    for(var i=0;i<d.numFields;i++){
        var n=d.getNthFieldName(i);
        if(/^Limited Feature(?: Max Usages| Recovery| Used)? \d+$/.test(n))r.resources[n]=d.getField(n).valueAsString;
        if(/^Reaction \d+$/.test(n))r.reactions[n]=d.getField(n).valueAsString;
    }
    Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(ch){return '\\u'+('0000'+ch.charCodeAt(0).toString(16)).slice(-4);}));
})(tDoc);
