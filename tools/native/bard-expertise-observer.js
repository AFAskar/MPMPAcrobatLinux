// Keep this diagnostic entry identical in native and Reader RunUserScript.
var iFileName = 'Bard expertise observation.js';
Value('User Script', '');
(function (d) {
    var bard = classes.known.bard;
    var result = {
        identity: {level: bard.level, subclass: bard.subclass},
        choices: GetFeatureChoice('classes', 'bard', 'expertise', true),
        fields: {}, offers: [], sentinel: '\u00a0\u2028\ud83d\ude00'
    };
    var names = ['Class and Levels', 'Character Level', 'Proficiency Bonus',
        'Class Features', 'Jack of All Trades', 'Dex', 'Dex Mod', 'Int', 'Int Mod',
        'Wis', 'Wis Mod', 'Cha', 'Cha Mod'];
    ['Acr', 'Arc', 'Perc', 'Pers', 'His'].forEach(function (skill) {
        names.push(skill, skill + ' Prof', skill + ' Exp', skill + ' Bonus');
    });
    names.forEach(function (name) { result.fields[name] = d.getField(name).valueAsString; });
    MakeClassMenu();
    function walk(items, parents) {
        items.forEach(function (item) {
            var path = parents.concat(item.cName);
            if (item.oSubMenu) walk(item.oSubMenu, path);
            else if (typeof item.cReturn === 'string' && item.cReturn.indexOf('bard#expertise#') === 0) {
                result.offers.push({path: path, enabled: item.bEnabled !== false,
                    marked: !!item.bMarked, result: item.cReturn});
            }
        });
    }
    walk(Menus.classfeatures, []);
    Value('PC Name', JSON.stringify(result).replace(/[\u007f-\uffff]/g, function (ch) {
        return '\\u' + ('0000' + ch.charCodeAt(0).toString(16)).slice(-4);
    }));
})(tDoc);
