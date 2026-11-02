#!/usr/bin/env python3
"""Compare original native spell-button operations with an actual Reader trace.

Fresh native and Reader-saved reopens execute another original activation.
Requires all modified activations to produce actual nonempty menu traces.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import canonical_fields, script_hashes, inspect


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reader', type=Path, required=True)
    p.add_argument('--binary', type=Path, default=ROOT / 'target/debug/mpmb-reader')
    a = p.parse_args()
    reader = json.loads(a.reader.read_text())
    assert reader['passed']
    source = Path(reader['input'])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == reader['input_sha256']
    folder = ROOT / 'output/testing' / ('spell-modifiers-comparison-' + str(time.time_ns()))
    folder.mkdir()
    binary = folder / 'mpmb-reader'
    shutil.copy2(a.binary, binary)
    report = {'passed': False, 'scope': __doc__, 'reader': str(a.reader.resolve()),
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'phases': [], 'reopens': []}
    print(folder, flush=True)
    phases = {row['label']: row for row in reader['phases']}
    names = reader['names']
    first_row = int(reader['button'].rsplit('.', 1)[1])
    row_prefix = reader['button'].split('spells.checkbox.')[0] + 'spells.'
    visible_names = [row_prefix + kind + '.' + str(row) for row in [first_row, first_row + 1]
                     for kind in ['name', 'description']]
    read = '(function(){var r={};' + json.dumps(names) + '.forEach(function(n){r[n]=getField(n).valueAsString});return r})()'
    steps = [{'op': 'advance', 'ms': 4100}]
    captures = []
    dialogs = []
    activations = []

    def capture(label):
        index = len(steps)
        steps.append({'op': 'eval', 'code': read})
        output = folder / (label + '.pdf')
        steps.append({'op': 'save', 'path': str(output)})
        captures.append((label, index, output))

    def run(label, input_pdf, steps, dialogs):
        scenario = folder / (label + '-scenario.json')
        scenario.write_text(json.dumps({'steps': steps, 'dialogs': dialogs, 'alerts': []}))
        trace = folder / (label + '-dialogs')
        env = dict(os.environ, MPMB_DIALOG_TRACE_DIR=str(trace))
        output = folder / (label + '-probe.json')
        with (folder / (label + '.log')).open('w') as log:
            result = subprocess.run([str(binary), str(input_pdf), '--probe', str(scenario), str(output)],
                                    env=env, stdout=log, stderr=log, timeout=480)
        data = json.loads(output.read_text())
        assert result.returncode == 0 and data['passed'] and not data['diagnostics']['errors'], data.get('error')
        return data, sorted(trace.glob('dialog-*.json'))

    try:
        capture('loaded')
        for i, event in enumerate(reader['activations'][:-1]):
            key = event['key']
            modifiers = {'shift': key == '+ ', 'modifier': key == '^ '}
            steps.append({'op': 'eval', 'code': '__host.activate(' + json.dumps(event['button']) + ',0,' + json.dumps(modifiers) + ')'})
            index = len(steps)
            steps.append({'op': 'eval', 'code': read})
            activations.append((event, index))
            if key != ' ':
                reply = {'title': 'MPMB menu'}
                if event['selection']:
                    reply['button_path'] = [event['selection']]
                else:
                    reply['result'] = 'cancel'
                dialogs.append(reply)
            if i in [2, 3, 4]:
                capture({2: 'prepared', 3: 'moved-down', 4: 'restored'}[i])
        data, traces = run('main', source, steps, dialogs)
        assert len(traces) == 4, ('Missing original modified-click menus', len(traces))
        for path in traces:
            menu = json.loads(path.read_text())
            assert menu['description']['name'] == 'MPMB menu' and menu['description']['elements']
            assert 'Move row down' in json.dumps(menu['description'])
        for event, index in activations:
            assert data['stages'][index]['result'] == event['after'], (event['key'], event['selection'], data['stages'][index]['result'], event['after'])
        for label, index, output in captures:
            expected = phases[label]['fields']
            assert data['stages'][index]['result'] == expected
            fields = canonical_fields(PdfReader(output))
            assert {n: fields[n]['/V'] for n in names} == expected
            assert script_hashes(output) == script_hashes(source)
            reference_fields = canonical_fields(PdfReader(phases[label]['pdf']))
            visible = {n: reference_fields[n]['/V'] for n in visible_names}
            assert {n: fields[n]['/V'] for n in visible_names} == visible
            appearances = {}
            for engine, path in [('native', output), ('reader', Path(phases[label]['pdf']))]:
                checked = inspect(path, visible)
                appearances[engine] = {n: [w['appearance_text'] for w in checked['widgets']
                                           if w['name'] == n and w['visible']] for n in visible_names}
                assert all(texts and all(text.strip() for text in texts)
                           for texts in appearances[engine].values())
            for n in visible_names:
                if '.spells.name.' in n:
                    assert appearances['native'][n] == appearances['reader'][n]
            report['phases'].append({'label': label, 'pdf': str(output), 'fields': expected,
                                     'visible_fields': visible, 'appearance_text': appearances})
        # Both actual saved engines must support a subsequent plain activation.
        for label, input_pdf in [('native', folder / 'restored.pdf'), ('reader', Path(phases['restored']['pdf']))]:
            output = folder / (label + '-reopened-edited.pdf')
            reopen_steps = [{'op': 'advance', 'ms': 4100}, {'op': 'eval', 'code': read},
                            {'op': 'eval', 'code': '__host.activate(' + json.dumps(reader['button']) + ')'},
                            {'op': 'eval', 'code': read}, {'op': 'save', 'path': str(output)}]
            reopened, unexpected = run(label + '-reopen', input_pdf, reopen_steps, [])
            assert not unexpected
            assert reopened['stages'][1]['result'] == phases['reopened']['fields']
            assert reopened['stages'][3]['result'] == phases['edited-reopen']['fields']
            fields = canonical_fields(PdfReader(output))
            assert {n: fields[n]['/V'] for n in names} == phases['edited-reopen']['fields']
            assert script_hashes(output) == script_hashes(source)
            report['reopens'].append({'engine': label, 'pdf': str(output), 'fields': phases['edited-reopen']['fields']})
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        path = folder / 'comparison.json'
        path.write_text(json.dumps(report, indent=2) + '\n')
        print(path, flush=True)


if __name__ == '__main__':
    main()
