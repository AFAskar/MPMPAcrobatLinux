#!/usr/bin/env python3
"""2024 Lore Bard calculated Inspiration maxima and Font/rest transitions.

Requires a disclosed startup observer on the qualified Lore9/Cha20 input.
Native-only until separately compared with Reader; no complete class claim.
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import inspect, script_hashes
import fighter_additional_diagnostics as diagnostics
import subclass_audit_qualification as qualification


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/native' / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--instrumentation', type=Path, required=True)
    parser.add_argument('--binary', type=Path, default=ROOT / 'target/debug/mpmb-reader')
    args = parser.parse_args()
    source = args.input.resolve()
    manifest = json.loads(args.instrumentation.read_text())
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    assert manifest['passed'] and manifest['mode'] == 'startup-script-timer'
    assert source == Path(manifest['input']).resolve()
    assert digest(source) == manifest['input_sha256']
    assert manifest['observer_sha256'] == digest(ROOT / 'tools/native/bard-2024-resource-observer.js')
    assert manifest['diagnostic_helper_sha256'] == digest(Path(diagnostics.__file__))
    folder = ROOT / 'output/testing' / ('native-bard-2024-resources-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    binary = folder / 'mpmb-reader'
    shutil.copy2(args.binary.resolve(), binary)
    report = {'passed': False, 'scope': __doc__, 'input': str(source),
              'input_sha256': digest(source), 'binary_sha256': digest(binary),
              'instrumentation': str(args.instrumentation.resolve()), 'phases': [],
              'probe_qualifications': [], 'reader_qualified': False}
    style = module('style', 'default-style-persistence.py')
    fields = module('fields', 'field-state-comparison.py')
    profile = module('profile', 'fighter-styles.py')

    def start():
        return [{'op': 'advance', 'ms': 5100}, {'op': 'assert', 'values': {
            'User Script': '// MPMB workflow observer installed'}}], []

    def call(steps, code):
        steps.extend([{'op': 'eval', 'code': '__host.command(' + json.dumps(code) + ')'},
                      {'op': 'advance', 'ms': 1000}])

    def edit(steps, field, value):
        steps.extend([{'op': 'user-edit', 'field': field, 'value': value},
                      {'op': 'advance', 'ms': 1000}])

    def capture(steps, captures, label, level=9, cha='20', used=''):
        steps.extend([{'op': 'eval', 'code': diagnostics.native_request()},
                      {'op': 'eval', 'code': profile.SUMMARY}])
        pdf = folder / (label + '.pdf')
        captures.append((label, len(steps) - 1, pdf, level, cha, used))
        steps.append({'op': 'save', 'path': str(pdf)})
        return pdf

    def run(label, pdf, steps, captures, dialogs):
        scenario = folder / (label + '-scenario.json')
        evidence = folder / (label + '-probe.json')
        scenario.write_text(json.dumps({'steps': steps, 'dialogs': dialogs}))
        with (folder / (label + '.log')).open('w') as log:
            proc = subprocess.run([str(binary), str(pdf), '--probe', str(scenario), str(evidence)],
                                  stdout=log, stderr=log, timeout=600,
                                  env=dict(os.environ, MPMB_DIALOG_TRACE_DIR=str(folder / (label + '-dialogs'))))
        data = json.loads(evidence.read_text())
        # The observer's one positive sentinel is expected, not an ignored warning.
        messages = data['diagnostics']['console']['messages']
        assert [m['text'] for m in messages] == ['MPMB 2024 Bard resource workflow console sentinel'], messages
        strict = json.loads(json.dumps(data))
        strict['diagnostics']['console']['messages'] = []
        checked = qualification.qualify_probe(proc.returncode, strict)
        report['probe_qualifications'].append(dict(checked, probe=str(evidence), expected_console_sentinel=messages))
        assert checked['passed'], checked
        markers = [s['result'] for s in data['stages'] if isinstance(s.get('result'), str)
                   and s['result'].startswith(diagnostics.DONE)]
        assert markers == [diagnostics.DONE + str(i + 1) for i in range(len(captures))]
        for name, index, saved, level, cha, used in captures:
            state = style.saved_capture(saved, data['stages'][index]['result'], pdf)
            assert not state['errors'], state['errors']
            assert state['identity'] == {'level': level, 'subclass': 'bard-lore'}
            assert state['calculation'] == {'app': True, 'doc': True, 'delay': False}
            assert state['fields']['Cha'] == cha
            resources = state['resources']
            expected = {'Limited Feature 1': 'Bardic Inspiration (d6)' if level < 5 else 'Bardic Inspiration (d8)',
                        'Limited Feature Max Usages 1': str((int(cha) - 10) // 2),
                        'Limited Feature Recovery 1': 'long rest' if level < 5 else 'SR/SS 1+',
                        'Limited Feature Used 1': used}
            assert all(resources[n] == v for n, v in expected.items()), (name, expected, resources)
            canonical = fields.compare(saved, dict(state['fields'], **resources, **state['reactions']))
            visible = inspect(saved, resources)
            assert visible['passed'] and script_hashes(saved) == script_hashes(source)
            rows = [w for w in visible['widgets'] if w['name'] == 'Limited Feature Used 1' and w['visible'] and w['page'] is not None]
            assert rows and all((w['appearance_text'] or '').strip() == used for w in rows), (name, rows)
            report['phases'].append({'label': name, 'state': state, 'pdf': str(saved),
                                     'summary': data['stages'][index]['result'], 'canonical': canonical,
                                     'visible': visible, 'probe': str(evidence)})

    try:
        steps, captures = start()
        capture(steps, captures, 'baseline9')
        edit(steps, 'Cha', '14'); capture(steps, captures, 'cha14', cha='14')
        edit(steps, 'Cha', '20'); capture(steps, captures, 'cha20')
        edit(steps, 'Limited Feature Used 1', '4'); capture(steps, captures, 'spent9', used='4')
        call(steps, "resetLimFeaUsed('short rest')"); capture(steps, captures, 'short9')
        edit(steps, 'Limited Feature Used 1', '3')
        spent = capture(steps, captures, 'spent-again9', used='3')
        run('maxima-rest', source, steps, captures, [])
        steps, captures = start()
        capture(steps, captures, 'cold-spent9', used='3')
        call(steps, "resetLimFeaUsed('long rest')"); capture(steps, captures, 'cold-long9')
        call(steps, "ApplyClasses('Bard (College of Lore) 4',false)")
        capture(steps, captures, 'lore4', level=4)
        edit(steps, 'Limited Feature Used 1', '3')
        call(steps, "resetLimFeaUsed('short rest')"); capture(steps, captures, 'short4', level=4, used='3')
        call(steps, "resetLimFeaUsed('long rest')"); capture(steps, captures, 'long4', level=4)
        call(steps, "ApplyClasses('Bard (College of Lore) 5',false)")
        capture(steps, captures, 'font5', level=5)
        edit(steps, 'Limited Feature Used 1', '2')
        call(steps, "resetLimFeaUsed('short rest')"); capture(steps, captures, 'short5', level=5)
        run('cold-progression', spent, steps, captures,
            [{'title': 'CHANGES ALERT DIALOG', 'result': 'ok'}] * 2)
        assert digest(source) == report['input_sha256']
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (folder / 'resources.json').write_text(json.dumps(report, indent=2) + '\n')
        print(folder / 'resources.json', flush=True)


if __name__ == '__main__':
    main()
