#!/usr/bin/env python3
"""Load the actual Reader-edited cross-distribution save, edit again and resave.

The loaded state is compared with Reader's post-edit snapshot. It is not compared
with the earlier pre-edit observation, and no expected values are written to a
Reader output.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import inspect, script_hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader', type=Path, required=True)
    args = parser.parse_args()
    reference = json.loads(args.reader.read_text())
    assert reference['passed']
    source = args.reader.parent / 'reader.pdf'
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    expected = reference['captured']['after']
    folder = ROOT / 'output/testing' / ('fallback-native-reopen-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'reader': str(args.reader),
              'source_sha256': before, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
    output = folder / 'native.pdf'
    read = "(function(){var r={};" + json.dumps(list(expected)) + ".forEach(function(n){r[n]=getField(n).valueAsString});return r})()"
    scenario = folder / 'scenario.json'
    evidence = folder / 'probe.json'
    scenario.write_text(json.dumps({'dialogs': [], 'alerts': [1] * 20, 'steps': [
        {'op': 'advance', 'ms': 4100}, {'op': 'eval', 'code': read},
        {'op': 'edit', 'field': 'Str', 'value': '16'},
        {'op': 'edit', 'field': 'Player Name', 'value': 'Reopened \u03a9 \u2014 &'},
        {'op': 'advance', 'ms': 1000}, {'op': 'eval', 'code': read},
        {'op': 'save', 'path': str(output)}]}))
    try:
        with (folder / 'probe.log').open('w') as log:
            process = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(evidence)],
                                     stdout=log, stderr=log, timeout=300)
        data = json.loads(evidence.read_text())
        assert process.returncode == 0 and data['passed'] and not data['diagnostics']['errors']
        report['loaded'] = data['stages'][1]['result']
        report['edited'] = data['stages'][-2]['result']
        assert report['loaded'] == expected
        wanted = {**expected, 'Str': '16', 'Str Mod': '3', 'Player Name': 'Reopened \u03a9 \u2014 &'}
        assert report['edited'] == wanted
        checked = inspect(output, wanted)
        assert checked['actual'] == wanted and checked['widgets'] and all(w['matches'] for w in checked['widgets'])
        assert script_hashes(output) == script_hashes(source)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
        report['output'] = str(output)
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        target = folder / 'reopen.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
