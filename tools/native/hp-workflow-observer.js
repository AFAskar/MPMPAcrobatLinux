var iFileName = 'HP workflow observer.js';
(function (d) {
    var r = {fields: {}, mapping: d.getField('HP Max').submitName,
        totals: calcHPtotals(''), feats: {known: CurrentFeats.known, choices: CurrentFeats.choices},
        trace: d.__hpTrace || [], errors: d.__hpErrors || [], sentinel: '\u00a0\u2028\ud83d\ude00'};
    ['HP Max', 'HP Current', 'HP Temp', 'HD1 Level', 'HD1 Die', 'HD1 Used',
     'Con', 'Con Mod', 'Character Level', 'Proficiency Bonus', 'Class and Levels', 'Feat Name 1'].forEach(function (n) {
        r.fields[n] = d.getField(n).valueAsString;
    });
    Value('PC Name', JSON.stringify(r).replace(/[\u007f-\uffff]/g, function (c) {
        return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4);
    }));
})(tDoc);
