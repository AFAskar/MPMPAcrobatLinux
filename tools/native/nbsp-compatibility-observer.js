// Check whether narrow-string conversion applies compatibility normalization.
var iFileName = 'PDFDocEncoding compatibility text boundary.js';
Value('User Script', '');
(function (d) {
    var result = {cases: [], eventCases: [], errors: [], sentinel: '\u00a0\u2028\ud83d\ude00'};
    var codes = [0xaa, 0xba, 0xb2, 0xb3, 0xb9, 0xb5, 0xbc, 0xbd, 0xbe, 0xa8, 0xaf, 0xb4, 0xb8, 0xfb01, 0xfb02];
    ['Player Name', 'Notes.Left'].forEach(function (name) {
        try {
            var f = d.getField(name);
            ['Keystroke', 'Validate', 'Calculate', 'Format'].forEach(function (kind) { f.setAction(kind, ''); });
            codes.forEach(function (code) {
                ['', '\u03a9'].forEach(function (suffix) {
                    var input = String.fromCharCode(code) + '\u00a0B' + suffix; f.value = input;
                    result.cases.push({field: name, code: code, input: input, value: f.valueAsString});
                });
            });
            f.value = 'A\u00a0\u03a9';
        } catch (error) { result.errors.push({field: name, name: error.name, message: error.message}); }
    });
    var trace = [], notes = d.getField('Notes.Left');
    d.__encodingEventObserve = function (e) {
        var rich;
        try { rich = e.richValue; rich = rich ? rich.map(function (span) { return span.text; }) : rich; }
        catch (error) { rich = {getterError: error.name}; }
        trace.push({name: e.name, value: e.value, rich: rich});
    };
    notes.setAction('Keystroke', '__encodingEventObserve(event)');
    notes.setAction('Validate', '__encodingEventObserve(event)');
    [
        [{text: 'A\u00a0B'}, {text: '\u03a9'}],
        [{text: 'A\u00a0 \u03a9'}],
        [{text: 'A\u00a0B', fontWeight: 700}, {text: '\u03a9', fontWeight: 400}]
    ].forEach(function (spans) {
        try {
            trace = []; notes.richValue = spans;
            result.eventCases.push({input: spans, value: notes.valueAsString, events: trace.slice(0)});
        } catch (error) { result.errors.push({richInput: spans, name: error.name, message: error.message}); }
    });
    notes.setAction('Keystroke', ''); notes.setAction('Validate', '');
    Value('PC Name', JSON.stringify(result).replace(/[\u007f-\uffff]/g, function (ch) {
        return '\\u' + ('0000' + ch.charCodeAt(0).toString(16)).slice(-4);
    }));
})(tDoc);
