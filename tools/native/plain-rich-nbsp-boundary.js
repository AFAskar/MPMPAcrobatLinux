// Isolated untouched fields: separate action installation from style assignment.
var iFileName = 'NBSP action and style boundary.js';
Value('User Script', '');
(function (d) {
    var result = {cases: [], errors: [], sentinel: '\u00a0\u2028\ud83d\ude00'}, trace = [];
    d.__nbspBoundaryObserve = function (e) { trace.push({name: e.name, value: e.value}); };
    var specs = [
        ['Player Name', '', null], ['Hair colour', 'Keystroke', null],
        ['Eyes colour', 'Validate', null], ['Sex', 'Format', null],
        ['Skin colour', '', false], ['Faith/Deity', 'Keystroke', false],
        ['Height', '', true], ['Weight', 'Keystroke', true]
    ];
    specs.forEach(function (spec) {
        try {
            var f = d.getField(spec[0]);
            var row = {field: spec[0], action: spec[1], assignedRichText: spec[2], initialRichText: f.richText};
            ['Keystroke', 'Validate', 'Calculate', 'Format'].forEach(function (kind) { f.setAction(kind, ''); });
            if (spec[2] !== null) f.richText = spec[2];
            if (spec[1]) f.setAction(spec[1], '__nbspBoundaryObserve(event)');
            trace = []; f.value = 'a\u00a0b\tc\r\u00a0\u00a0z';
            row.richText = f.richText; row.multiline = f.multiline;
            row.value = f.valueAsString; row.events = trace.slice(0);
            result.cases.push(row);
            if (spec[1]) f.setAction(spec[1], '');
        } catch (error) { result.errors.push({field: spec[0], name: error.name, message: error.message}); }
    });
    Value('PC Name', JSON.stringify(result).replace(/[\u007f-\uffff]/g, function (ch) {
        return '\\u' + ('0000' + ch.charCodeAt(0).toString(16)).slice(-4);
    }));
})(tDoc);
