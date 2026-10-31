// Read retained canonical values and raw rich state; mutate only the carrier.
var iFileName = 'Read retained whitespace and rich spans.js';
Value('User Script', '');
(function (d) {
    var result = {fields: [], errors: [], sentinel: '\u00a0\u2028\ud83d\ude00'};
    ['Player Name', 'Notes.Left'].forEach(function (name) {
        try {
            var f = d.getField(name), row = {name: name, value: f.valueAsString, richText: f.richText, multiline: f.multiline};
            if (f.richText) { row.richValue = f.richValue; row.defaultStyle = f.defaultStyle; }
            result.fields.push(row);
        } catch (error) { result.errors.push({field: name, name: error.name, message: error.message}); }
    });
    Value('PC Name', JSON.stringify(result).replace(/[\u007f-\uffff]/g, function (ch) {
        return '\\u' + ('0000' + ch.charCodeAt(0).toString(16)).slice(-4);
    }));
})(tDoc);
