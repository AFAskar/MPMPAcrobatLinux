var iFileName = 'Swords definition observation.js';
(function (d) {
    var f = ClassSubList['bard-college of swords'].features['subclassfeature3.1'];
    var r = {keys: Object.keys(f), choices: f.choices,
        styleChoice: f.choicesFightingStyles, styleKeys: Object.keys(FightingStyles),
        dueling: typeof f.dueling, source: f.source, choicesFound: [],
        excluded: !!testSource('bard-college of swords', ClassSubList['bard-college of swords'], 'classExcl'),
        sentinel: '\u00a0\u2028\ud83d\ude00'};
    f.choices.forEach(function (n) { r.choicesFound.push({name: n, exists: typeof f[n.toLowerCase()] !== 'undefined'}); });
    Value('PC Name', JSON.stringify(r).replace(/[\u007f-\uffff]/g, function (c) {
        return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4);
    }));
})(tDoc);
