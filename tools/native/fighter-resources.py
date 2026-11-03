#!/usr/bin/env python3
"""Bounded native Champion resource progression, spending and original rest reset.

Previously qualified Fighter6 input. Additional Champion style and new feats/ASIs
are intentionally unselected; this is resource coverage, not complete Champion
progression. Reader comparison is a separate required gate.
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


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/native' / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True)
    a = p.parse_args()
    source = a.input.resolve()
    profile = module('profile', 'fighter-styles.py')
    style = module('style', 'default-style-persistence.py')
    fields = module('fields', 'field-state-comparison.py')
    observer = (ROOT / 'tools/native/fighter-style-observer.js').read_text()
    folder = ROOT / 'output/testing' / ('native-fighter-resources-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'input': str(source), 'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'observer_sha256': hashlib.sha256(observer.encode()).hexdigest(), 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
              'phases': [], 'reader': 'not run', 'full_class_coverage': False}
    def script(text):
        return {'op': 'eval', 'code': "Value('User Script'," + json.dumps(text) + ");__host.command('RunUserScript(false)')"}
    def run(label, source, steps, captures):
        spec = folder / (label + '-scenario.json')
        evidence = folder / (label + '-probe.json')
        spec.write_text(json.dumps({'steps': steps, 'dialogs': [{'result': 'ok'}] * 100, 'alerts': [1] * 100}))
        with (folder / (label + '.log')).open('w') as log:
            proc = subprocess.run([str(binary), str(source), '--probe', str(spec), str(evidence)], stdout=log, stderr=log,
                                  timeout=480, env=dict(os.environ, MPMB_DIALOG_TRACE_DIR=str(folder / (label + '-dialogs'))))
        data = json.loads(evidence.read_text())
        assert proc.returncode == 0 and data['passed'], data.get('error')
        assert not data['diagnostics']['errors'] and not data['diagnostics']['console']['messages']
        for label, index, pdf, level, used in captures:
            state = style.saved_capture(pdf, data['stages'][index]['result'], source)
            assert not state['errors'] and state['identity'] == {'level': level, 'subclass': 'fighter-champion'}
            assert state['choice'] == 'archery' and state['additional'] == '', 'This profile deliberately leaves additional style unqualified'
            assert len(state['resources']) == 64
            resource = state['resources']
            maxima = ['1', '2' if level >= 17 else '1'] + (['3' if level >= 17 else '1'] if level >= 9 else [])
            names = ['Second Wind (1d10+' + str(level) + ')', 'Action Surge'] + (['Indomitable'] if level >= 9 else [])
            assert [resource['Limited Feature ' + str(i)] for i in range(1, len(names) + 1)] == names
            assert [resource['Limited Feature Max Usages ' + str(i)] for i in range(1, len(names) + 1)] == maxima
            assert [resource['Limited Feature Recovery ' + str(i)] for i in range(1, len(names) + 1)] == ['short rest', 'short rest'] + (['long rest'] if level >= 9 else [])
            assert [resource['Limited Feature Used ' + str(i)] for i in range(1, len(names) + 1)] == used
            canonical = fields.compare(pdf, dict(state['fields'], **resource))
            visible = inspect(pdf, {k: v for k, v in resource.items() if v})
            assert visible['passed'] and script_hashes(pdf) == script_hashes(source)
            report['phases'].append({'label': label, 'state': state, 'pdf': str(pdf), 'summary': data['stages'][index]['result'],
                                      'canonical': canonical, 'visible': visible, 'probe': str(evidence)})
    def capture(steps, captures, label, level, used):
        steps.append(script(observer))
        index = len(steps)
        pdf = folder / (label + '-diagnostic.pdf')
        steps.extend([{'op': 'eval', 'code': profile.SUMMARY}, {'op': 'save', 'path': str(pdf)}])
        captures.append((label, index, pdf, level, used))
    try:
        steps = [{'op': 'advance', 'ms': 4100}, script(profile.SETUP)]
        captures = []
        capture(steps, captures, 'loaded-6', 6, ['', ''])
        for level in [9, 11, 17]:
            steps.extend([{'op': 'eval', 'code': "__host.command(\"ApplyClasses('Fighter (Champion) " + str(level) + "',false)\")"}, {'op': 'advance', 'ms': 1000}])
            capture(steps, captures, 'level-' + str(level), level, ['', '', ''])
        for row, value in [(1, '1'), (2, '2'), (3, '2')]:
            steps.extend([{'op': 'user-edit', 'field': 'Limited Feature Used ' + str(row), 'value': value}, {'op': 'advance', 'ms': 1000}])
        capture(steps, captures, 'spent-17', 17, ['1', '2', '2'])
        steps.extend([{'op': 'eval', 'code': "__host.command(\"resetLimFeaUsed('short rest')\")"}, {'op': 'advance', 'ms': 1000}])
        capture(steps, captures, 'short-rest', 17, ['', '', '2'])
        spent = folder / 'native-spent.pdf'
        steps.extend([{'op': 'eval', 'code': "Value('User Script','');Value('PC Name','Fighter resource compatibility')"}, {'op': 'save', 'path': str(spent)}])
        run('workflow', source, steps, captures)
        steps = [{'op': 'advance', 'ms': 4100}, script(profile.SETUP)]
        captures = []
        capture(steps, captures, 'cold-spent', 17, ['', '', '2'])
        steps.extend([{'op': 'eval', 'code': "__host.command(\"resetLimFeaUsed('long rest')\")"}, {'op': 'advance', 'ms': 1000}])
        capture(steps, captures, 'long-rest', 17, ['', '', ''])
        output = folder / 'native-rested.pdf'
        steps.extend([{'op': 'eval', 'code': "Value('User Script','');Value('PC Name','Fighter resource compatibility')"}, {'op': 'save', 'path': str(output)}])
        run('reopen', spent, steps, captures)
        assert script_hashes(output) == script_hashes(source)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == report['input_sha256']
        report.update(passed=True, spent_pdf=str(spent), pdf=str(output))
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        target = folder / 'resources.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
