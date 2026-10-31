// Distinguish PDFDocEncoding from Latin-1/Windows encoding and span boundaries.
var iFileName = 'NBSP PDF text encoding and rich span boundary.js';
Value('User Script', '');
(function (d) {
    var result = {cases: [], richCases: [], errors: [], sentinel: '\u00a0\u2028\ud83d\ude00'};
    var codes = [0x141, 0x131, 0xfb01, 0x2212, 0x2d8, 0x153, 0x20ac, 0xad, 0x100, 0x3a9];
    ['Player Name', 'Notes.Left'].forEach(function (name) {
        try {
            var f = d.getField(name);
            ['Keystroke', 'Validate', 'Calculate', 'Format'].forEach(function (kind) { f.setAction(kind, ''); });
            codes.forEach(function (code) {
                var input = String.fromCharCode(code) + '\u00a0B'; f.value = input;
                result.cases.push({field: name, richText: f.richText, code: code, input: input, value: f.valueAsString});
            });
        } catch (error) { result.errors.push({field: name, name: error.name, message: error.message}); }
    });
    [
        [{text: 'A\u00a0B'}, {text: '\u03a9'}],
        [{text: '\u03a9'}, {text: 'A\u00a0B'}],
        [{text: 'A\u00a0\u03a9'}],
        [{text: 'A\u00a0\u20ac'}],
        [{text: 'A\u00a0B'}, {text: '\u00e9'}],
        [{text: 'A\u00a0B', fontWeight: 700}, {text: '\u03a9', fontWeight: 400}],
        [{text: 'A\u00a0B'}]
    ].forEach(function (spans) {
        try {
            var f = d.getField('Notes.Left'); f.richValue = spans;
            result.richCases.push({input: spans, value: f.valueAsString, texts: f.richValue.map(function (span) { return span.text; })});
        } catch (error) { result.errors.push({richInput: spans, name: error.name, message: error.message}); }
    });
    Value('PC Name', JSON.stringify(result).replace(/[\u007f-\uffff]/g, function (ch) {
        return '\\u' + ('0000' + ch.charCodeAt(0).toString(16)).slice(-4);
    }));
})(tDoc);
