var iFileName = 'Fighter table observer.js';
(function (d) {
    var k = classes.known.fighter;
    var r = {identity: {level: k.level, subclass: k.subclass},
        choice: GetFeatureChoice('classes', 'fighter', 'fighting style'),
        extraChoices: GetFeatureChoice('classes', 'fighter', 'fighting style', true),
        additional: GetFeatureChoice('classes', 'fighter', 'additional fighting style'),
        fields: {}, resources: {}, errors: d.__styleErrors || [],
        sentinel: '\u00a0\u2028\ud83d\ude00'};
    ['Class and Levels', 'Character Level', 'Proficiency Bonus', 'HP Max', 'Con',
     'Str', 'Dex', 'Str Mod', 'Dex Mod', 'AC', 'AC Armor Bonus',
     'AC Armor Description', 'AC Dexterity Modifier', 'AC Shield Bonus',
     'AC Shield Bonus Description', 'AC Magic', 'AC Magic Description',
     'AC Misc Mod 1', 'AC Misc Mod 1 Description', 'AC Misc Mod 2',
     'AC Misc Mod 2 Description', 'Attack.1.Weapon Selection', 'Attack.1.Weapon',
     'Attack.1.Proficiency', 'Attack.1.Mod', 'Attack.1.Range', 'Attack.1.To Hit',
     'Attack.1.Damage', 'Attack.1.Damage Type', 'Attack.1.Description'].forEach(function (n) {
        r.fields[n] = d.getField(n).valueAsString;
    });
    for (var i = 0; i < d.numFields; i++) {
        var n = d.getNthFieldName(i);
        if (/^Limited Feature(?: Max Usages| Recovery| Used)? \d+$/.test(n)) {
            r.resources[n] = d.getField(n).valueAsString;
        }
    }
    Value('PC Name', JSON.stringify(r).replace(/[\u007f-\uffff]/g, function (c) {
        return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4);
    }));
})(tDoc);
