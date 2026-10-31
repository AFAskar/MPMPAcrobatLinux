// Isolated Field.rect diagnostic. Run through the original RunUserScript entry.
// Inactive widget zero is deliberately addressed through parent and index.
// All accepted active writes are restored; this is not an MPMB workflow pass.
var iFileName = 'Isolated inactive widget rectangle setter.js';
Value('User Script', '');
(function (d) {
    var result = {cases: [], errors: [], sentinel: '\u00a0\u2028\ud83d\ude00'};
    function attempt(field, rect) {
        try { field.rect = rect; return {ok: true}; }
        catch (error) { return {ok: false, name: error.name, message: error.message}; }
    }
    ['Age', 'Height'].forEach(function (name) {
      try {
        var base = d.getField(name), row = {field: name, page: base.page};
        var active = d.getField(name + '.1'), before = active ? active.rect : null;
        if (active) row.activeBefore = before;
        row.parent = attempt(base, [100, 700, 200, 680]);
        row.inactive = attempt(d.getField(name + '.0'), [100, 700, 200, 680]);
        if (active) {
        row.activeAfterRejected = active.rect;
        var changed = before.slice(0);
        changed[0] += 1; changed[2] += 1;
        row.activeSet = attempt(active, changed);
        row.activeChanged = active.rect;
        row.activeRestore = attempt(active, before);
        row.activeRestored = active.rect;
        } else row.activeAbsent = true;
        result.cases.push(row);
      } catch (error) {
        result.errors.push({field: name, name: error.name, message: error.message});
      }
    });
    Value('PC Name', JSON.stringify(result).replace(/[\u007f-\uffff]/g, function (ch) {
        return '\\u' + ('0000' + ch.charCodeAt(0).toString(16)).slice(-4);
    }));
})(tDoc);
