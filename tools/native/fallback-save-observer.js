// Original field actions after reopening a native save from another Linux host.
var iFileName = 'Cross-distribution native save observation.js';
Value('User Script', '');
(function (d) {
    var names = ['Class and Levels', 'Character Level', 'Proficiency Bonus',
        'Str', 'Str Mod', 'Player Name'];
    function capture() {
        var fields = {};
        names.forEach(function (name) { fields[name] = d.getField(name).valueAsString; });
        return fields;
    }
    var result = {before: capture(), sentinel: '\u00a0\u2028\ud83d\ude00'};
    Value('Str', '20');
    Value('Player Name', 'Compatibility \u03a9 \u2014 &');
    d.calculateNow();
    result.after = capture();
    if (result.after['Str Mod'] !== '5' || result.after.Str !== '20') {
        throw Error('Original strength calculation did not update');
    }
    if (result.after['Class and Levels'] !== result.before['Class and Levels'] ||
        result.after['Character Level'] !== result.before['Character Level'] ||
        result.after['Proficiency Bonus'] !== result.before['Proficiency Bonus']) {
        throw Error('Saved class/progression state changed');
    }
    Value('PC Name', JSON.stringify(result).replace(/[\u007f-\uffff]/g, function (ch) {
        return '\\u' + ('0000' + ch.charCodeAt(0).toString(16)).slice(-4);
    }));
})(tDoc);
