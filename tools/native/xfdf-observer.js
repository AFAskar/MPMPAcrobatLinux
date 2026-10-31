// Isolated exportAsXFDFStr API observation, invoked through RunUserScript.
var iFileName = 'Isolated XFDF string export.js';
Value('User Script', '');
(function (d) {
    var result = {cases: [], errors: [], metadata: [], sentinel: '\u00a0\u2028\ud83d\ude00'};
    var field = d.getField('Player Name');
    ['Keystroke', 'Validate', 'Calculate', 'Format'].forEach(function (kind) { field.setAction(kind, ''); });
    field.value = 'A & <B> "C" \'D\'\r\u00e9 \u03a9\u00a0';
    var notes = d.getField('Notes.Left');
    ['Keystroke', 'Validate', 'Calculate', 'Format'].forEach(function (kind) { notes.setAction(kind, ''); });
    notes.richValue = [{text: 'First & <line>\r', textSize: 9, fontWeight: 700}, {text: 'Second \u00e9', textSize: 7}];
    ['Player Name', 'Hair colour', 'Notes.Left', 'Attack.1.Weapon Selection', 'Attack.1.Proficiency'].forEach(function (name) {
        var f = d.getField(name);
        result.metadata.push({name: name, type: f.type, value: f.value, text: f.valueAsString});
    });
    var specs = [
        ['empty-selection', {aFields: []}],
        ['single-name', {aFields: 'Player Name'}],
        ['selection', {aFields: ['Player Name', 'Hair colour', 'No Such Field']}],
        ['selection-including-empty', {aFields: ['Player Name', 'Hair colour', 'No Such Field'], bAllFields: true}],
        ['subtree', {aFields: ['Attack.1']}],
        ['subtree-including-empty', {aFields: ['Attack.1'], bAllFields: true}],
        ['rich', {aFields: ['Notes.Left']}]
    ];
    specs.forEach(function (spec) {
        spec[1].cHRef = 'urn:mpmb:qualification';
        try { result.cases.push({label: spec[0], options: spec[1], xml: d.exportAsXFDFStr(spec[1])}); }
        catch (error) { result.errors.push({label: spec[0], name: error.name, message: error.message}); }
    });
    Value('PC Name', JSON.stringify(result).replace(/[\u007f-\uffff]/g, function (ch) {
        return '\\u' + ('0000' + ch.charCodeAt(0).toString(16)).slice(-4);
    }));
})(tDoc);
