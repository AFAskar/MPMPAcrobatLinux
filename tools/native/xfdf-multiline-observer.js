// Plain multiline values must survive XML line-ending normalization.
var iFileName = 'XFDF plain multiline boundary.js';
Value('User Script', '');
(function (d) {
    var result = {cases: [], metadata: [], errors: [], sentinel: '\u00a0\u2028\ud83d\ude00'};
    [['Notes.Left', 'first\rsecond\t<&>\r\u03a9\u00a0'], ['Notes.Right', '\rleading\r\rtrailing\r']].forEach(function (spec) {
        try {
            var f = d.getField(spec[0]);
            ['Keystroke', 'Validate', 'Calculate', 'Format'].forEach(function (kind) { f.setAction(kind, ''); });
            f.richText = false; f.value = spec[1];
            result.metadata.push({name: spec[0], type: f.type, value: f.value, text: f.valueAsString, multiline: f.multiline, richText: f.richText});
            var options = {aFields: [spec[0]], cHRef: 'urn:mpmb:qualification'};
            result.cases.push({label: spec[0] === 'Notes.Left' ? 'multiline' : 'empty-lines', options: options, xml: d.exportAsXFDFStr(options)});
        } catch (error) { result.errors.push({field: spec[0], name: error.name, message: error.message}); }
    });
    Value('PC Name', JSON.stringify(result).replace(/[\u007f-\uffff]/g, function (ch) {
        return '\\u' + ('0000' + ch.charCodeAt(0).toString(16)).slice(-4);
    }));
})(tDoc);
