var iFileName = 'Resilient workflow observer.js';
(function (d) {
    var r = {feats: {known: CurrentFeats.known, choices: CurrentFeats.choices},
        stats: typeof CurrentStats === 'undefined' ? null : CurrentStats,
        errors: d.__featErrors || [], fields: {}, sentinel: '\u00a0\u2028\ud83d\ude00'};
    ['Feat Name 1', 'Feat Note 1', 'Feat Description 1', 'Wis', 'Wis Mod',
     'Wis ST Prof', 'Wis ST Mod', 'Perc', 'Perc Prof', 'Perc Exp',
     'Character Level', 'Proficiency Bonus', 'Class and Levels'].forEach(function (n) {
        r.fields[n] = d.getField(n).valueAsString;
    });
    Value('PC Name', JSON.stringify(r).replace(/[\u007f-\uffff]/g, function (c) {
        return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4);
    }));
})(tDoc);
