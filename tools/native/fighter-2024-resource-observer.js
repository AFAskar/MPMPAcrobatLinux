// Diagnostic only; install once at startup, without rerunning imported add-ons.
(function (d) {
    if (!d.__fighter2024ResourceConsoleSeen) {
        console.println('MPMB 2024 Fighter resource workflow console sentinel');
        d.__fighter2024ResourceConsoleSeen = true;
    }
    var known = classes.known.fighter;
    if (!known || ClassList.fighter.features['second wind'].usages[8] !== 3) {
        throw Error('Expected original 2024 Fighter definition');
    }
    var r = {identity: {level: known.level, subclass: known.subclass},
        source: ClassList.fighter.source, fields: {}, resources: {}, rows: [],
        calculation: {app: app.calculate, doc: d.calculate, delay: d.delay},
        errors: d.__styleErrors || [], sentinel: '\u00a0\u2028\ud83d\ude00'};
    ['Class and Levels', 'Character Level', 'Proficiency Bonus', 'Con', 'HP Max'].forEach(function (name) {
        r.fields[name] = d.getField(name).valueAsString;
    });
    for (var i = 0; i < d.numFields; i++) {
        var name = d.getNthFieldName(i), match = /^Limited Feature (\d+)$/.exec(name);
        if (!match) continue;
        var row = match[1], label = d.getField(name).valueAsString;
        ['Limited Feature ' + row, 'Limited Feature Max Usages ' + row,
            'Limited Feature Used ' + row, 'Limited Feature Recovery ' + row].forEach(function (key) {
            r.resources[key] = d.getField(key).valueAsString;
        });
        if (label) r.rows.push({name: label, row: row,
            max: r.resources['Limited Feature Max Usages ' + row],
            used: r.resources['Limited Feature Used ' + row],
            recovery: r.resources['Limited Feature Recovery ' + row]});
    }
    Value('PC Name', JSON.stringify(r).replace(/[\u007f-\uffff]/g, function (c) {
        return '\\u' + ('0000' + c.charCodeAt(0).toString(16)).slice(-4);
    }));
})(tDoc);
