#!/usr/bin/env python3
"""Match Reader's complete HP/feat removal/cold reopen/progression sequence.

Also compare all actual limited-feature resource rows in each saved phase. Field
values are compared as strings; raw PDF value types and complete pixels are not
claimed equal. Every native phase executes original actions, not expected writes.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import re
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import canonical_fields, inspect, script_hashes


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/native' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reader', type=Path, required=True)
    a = p.parse_args()
    reference = json.loads(a.reader.read_text())
    assert reference['passed'] and len(reference['phases']) == 5
    source = Path(reference['input'])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == reference['input_sha256']
    profile = module('profile', 'reader-hp-workflow.py')
    style = module('style', 'default-style-persistence.py')
    fields = module('fields', 'field-state-comparison.py')
    code = profile.original_blur(source)
    observer = (ROOT / 'tools/native/hp-workflow-observer.js').read_text()
    folder = ROOT / 'output/testing' / ('hp-progression-comparison-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'reader': str(a.reader.resolve()),
              'input': str(source), 'input_sha256': reference['input_sha256'], 'phases': [],
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
    summary = "(function(){var s=getField('PC Name').valueAsString,a=1,b=0;for(var i=0;i<s.length;i++){a=(a+s.charCodeAt(i))%65521;b=(b+a)%65521}return {code_units:s.length,adler32_utf16:String((b*65536+a)>>>0)}})()"
    def script(text):
        return {'op': 'eval', 'code': "Value('User Script'," + json.dumps(text) + ");__host.command('RunUserScript(false)')"}
    restore = "var iFileName='Restore HP action.js';tDoc.getField('Con').setAction('OnBlur'," + json.dumps(code) + ');'
    captures = []
    def capture(steps, index):
        steps.append(script(observer))
        at = len(steps)
        label = reference['phases'][index]['label']
        diagnostic = folder / (label + '-diagnostic.pdf')
        steps.extend([{'op': 'eval', 'code': summary}, {'op': 'save', 'path': str(diagnostic)}])
        captures.append((index, at, diagnostic))
    def finish(steps, saved):
        steps.extend([script(restore), {'op': 'eval', 'code': "Value('User Script','');Value('PC Name','HP compatibility')"},
                      {'op': 'save', 'path': str(saved)}])
    def run(input_pdf, label, steps, dialogs):
        scenario = folder / (label + '-scenario.json')
        scenario.write_text(json.dumps({'steps': steps, 'dialogs': dialogs}))
        target = folder / (label + '-probe.json')
        with (folder / (label + '.log')).open('w') as log:
            proc = subprocess.run([str(binary), str(input_pdf), '--probe', str(scenario), str(target)],
                                  stdout=log, stderr=log, timeout=480, env=dict(os.environ))
        data = json.loads(target.read_text())
        assert proc.returncode == 0 and data['passed'], data.get('error')
        assert not data['diagnostics']['errors'] and not data['diagnostics']['console']['messages']
        for index, at, diagnostic in captures:
            expected = reference['phases'][index]
            state = style.saved_capture(diagnostic, data['stages'][at]['result'], source)
            assert state == expected['state'], (expected['label'], state, expected['state'])
            fields.compare(diagnostic, state['fields'])
            reader_fields = canonical_fields(PdfReader(expected['diagnostic']))
            native_fields = canonical_fields(PdfReader(diagnostic))
            resource_names = sorted(n for n in reader_fields if re.fullmatch(r'Limited Feature(?: Max Usages| Recovery| Used)? \d+', n))
            assert resource_names and resource_names == sorted(n for n in native_fields if re.fullmatch(r'Limited Feature(?: Max Usages| Recovery| Used)? \d+', n))
            resources = {n: str(reader_fields[n].get('/V', '')) for n in resource_names}
            assert resources == {n: str(native_fields[n].get('/V', '')) for n in resource_names}
            visible = inspect(diagnostic, resources)
            assert visible['passed'], visible
            report['phases'].append({'label': expected['label'], 'state': state, 'pdf': str(diagnostic),
                                     'resource_fields': resources, 'resource_visible': visible})
    try:
        feat_field = reference.get('feat_field', 'Feat Name 1')
        first_con = reference['first_con_edit']['paste']['value']
        second_con = reference['second_con_edit']['paste']['value']
        steps = [{'op': 'advance', 'ms': 4100}, script(profile.setup(code)),
                 {'op': 'user-edit', 'field': 'Con', 'value': first_con}, {'op': 'advance', 'ms': 1000}]
        capture(steps, 0)
        steps.extend([{'op': 'edit', 'field': feat_field, 'value': ''}, {'op': 'advance', 'ms': 1000}])
        capture(steps, 1)
        steps.extend([{'op': 'user-edit', 'field': 'Con', 'value': second_con}, {'op': 'advance', 'ms': 1000}])
        capture(steps, 2)
        saved = folder / 'native-before-reopen.pdf'
        finish(steps, saved)
        run(source, 'before-reopen', steps, [])
        captures.clear()
        steps = [{'op': 'advance', 'ms': 4100}, script(profile.setup(code)),
                 {'op': 'user-edit', 'field': 'Con', 'value': first_con}, {'op': 'advance', 'ms': 1000}]
        capture(steps, 3)
        class_input = reference.get('progression_input', 'Bard (College of Lore) 10')
        steps.extend([{'op': 'eval', 'code': '__host.command(' + json.dumps('ApplyClasses(' + json.dumps(class_input) + ',false)') + ')'},
                      {'op': 'advance', 'ms': 1000}])
        capture(steps, 4)
        final = folder / 'native-final.pdf'
        finish(steps, final)
        run(saved, 'after-reopen', steps, [{'title': 'CHANGES ALERT DIALOG', 'result': 'ok'}])
        assert profile.original_blur(final) == code and script_hashes(final) == script_hashes(source)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == reference['input_sha256']
        report.update(passed=True, pdf=str(final))
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        target = folder / 'comparison.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
