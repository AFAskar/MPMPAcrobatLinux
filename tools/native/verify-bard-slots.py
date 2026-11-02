#!/usr/bin/env python3
"""Match Reader Bard slot spending, original rests and fresh native persistence."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import script_hashes
spec = importlib.util.spec_from_file_location('field_state', ROOT / 'tools/native/field-state-comparison.py')
field_state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(field_state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader', type=Path, required=True)
    args = parser.parse_args()
    reference = json.loads(args.reader.read_text())
    assert reference['passed']
    source = Path(reference['input'])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == reference['input_sha256']
    folder = ROOT / 'output/testing' / ('bard-slot-comparison-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'reader': str(args.reader),
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'phases': []}
    names = reference['names']
    read = "(function(){var r={};" + json.dumps(names) + ".forEach(function(n){r[n]=getField(n).valueAsString});return r})()"
    captures = []

    def capture(steps, label, suffix=''):
        steps.append({'op': 'advance', 'ms': 1000})
        index = len(steps)
        steps.append({'op': 'eval', 'code': read})
        output = folder / (label + suffix + '.pdf')
        steps.append({'op': 'save', 'path': str(output)})
        captures.append((index, label, output))

    def run(label, pdf, steps):
        scenario = folder / (label + '.json')
        evidence = folder / (label + '-probe.json')
        scenario.write_text(json.dumps({'dialogs': [], 'alerts': [1] * 20, 'steps': steps}))
        with (folder / (label + '.log')).open('w') as log:
            process = subprocess.run([str(binary), str(pdf), '--probe', str(scenario), str(evidence)],
                                     stdout=log, stderr=log, timeout=300)
        data = json.loads(evidence.read_text())
        assert process.returncode == 0 and data['passed'] and not data['diagnostics']['errors']
        for index, phase_label, output in captures:
            expected = next(p['fields'] for p in reference['phases'] if p['label'] == phase_label)
            actual = data['stages'][index]['result']
            record = {'label': phase_label, 'run': label, 'equal': actual == expected,
                      'differences': {n: {'native': actual.get(n), 'reader': expected.get(n)}
                                      for n in names if actual.get(n) != expected.get(n)}, 'pdf': str(output)}
            report['phases'].append(record)
            assert record['equal'], ('Slot state differs', phase_label)
            record['api_raw_comparison'] = field_state.compare(output, actual)
            assert script_hashes(output) == script_hashes(source)
            print(phase_label, 'PASS', flush=True)
        captures.clear()

    try:
        steps = [{'op': 'advance', 'ms': 4100}]
        capture(steps, 'loaded')
        for name in reference['selected']:
            steps.append({'op': 'eval', 'code': '__host.activate(' + json.dumps(name) + ')'})
        capture(steps, 'spent')
        steps.append({'op': 'eval', 'code': "__host.command(\"resetLimFeaUsed('short rest')\")"})
        capture(steps, 'short-rest')
        run('workflow', source, steps)
        steps = [{'op': 'advance', 'ms': 4100}]
        capture(steps, 'reopened-spent')
        steps.append({'op': 'eval', 'code': "__host.command(\"resetLimFeaUsed('long rest')\")"})
        capture(steps, 'long-rest')
        run('reopen', folder / 'short-rest.pdf', steps)
        # The independent Reader-saved spent file must also retain its selections
        # and support the original long-rest action after a fresh native reopen.
        steps = [{'op': 'advance', 'ms': 4100}]
        capture(steps, 'reopened-spent', '-reader-source')
        steps.append({'op': 'eval', 'code': "__host.command(\"resetLimFeaUsed('long rest')\")"})
        capture(steps, 'long-rest', '-reader-source')
        run('reader-saved-reopen', Path(next(p['pdf'] for p in reference['phases'] if p['label'] == 'reopened-spent')), steps)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == reference['input_sha256']
        assert len(report['phases']) == 7
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        target = folder / 'comparison.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
