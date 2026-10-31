// Isolated value encoding boundary; no field style assignments or commit actions.
var iFileName = 'NBSP character encoding boundary.js';
Value('User Script', '');
(function (d) {
    var result = {cases: [], errors: [], sentinel: '\u00a0\u2028\ud83d\ude00'};
    var inputs = ['A\u00a0B', 'A\u00a0', '\u00a0A', '\u00e9\u00a0B', '\u03a9\u00a0B', '\u0100\u00a0B', '\u20ac\u00a0B', '\u0153\u00a0B', 'A\u00a0\u03a9', 'A\u00a0\u00e9', 'A\u00a0B\u00a0', 'A\u00a0 \u03a9\u00a0'];
    ['Player Name', 'Notes.Left'].forEach(function (name) {
        try {
            var f = d.getField(name);
            ['Keystroke', 'Validate', 'Calculate', 'Format'].forEach(function (kind) { f.setAction(kind, ''); });
            inputs.forEach(function (input) {
                f.value = input;
                result.cases.push({field: name, richText: f.richText, input: input, value: f.valueAsString});
            });
        } catch (error) { result.errors.push({field: name, name: error.name, message: error.message}); }
    });
    Value('PC Name', JSON.stringify(result).replace(/[\u007f-\uffff]/g, function (ch) {
        return '\\u' + ('0000' + ch.charCodeAt(0).toString(16)).slice(-4);
    }));
})(tDoc);
