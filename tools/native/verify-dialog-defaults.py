#!/usr/bin/env python3
"""Compare complete dialog default/store captures with the actual Reader control.

This is isolated host API qualification; original class/feat workflows are separate.
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


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/native' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reader', type=Path, required=True)
    p.add_argument('--binary', type=Path, default=ROOT / 'target/debug/mpmb-reader')
    a = p.parse_args()
    reference = json.loads(a.reader.read_text())
    assert reference['passed']
    observer = module('observer', 'reader-dialog-defaults.py').OBSERVER
    assert hashlib.sha256(observer.encode()).hexdigest() == reference['observer_sha256']
    style = module('style', 'default-style-persistence.py')
    source = Path(reference['input'])
    folder = ROOT / 'output/testing' / ('dialog-defaults-comparison-' + str(time.time_ns()))
    folder.mkdir()
    binary = folder / 'mpmb-reader'
    shutil.copy2(a.binary, binary)
    print(folder, flush=True)
    output = folder / 'native.pdf'
    summary = "(function(){var s=getField('PC Name').valueAsString,a=1,b=0;for(var i=0;i<s.length;i++){a=(a+s.charCodeAt(i))%65521;b=(b+a)%65521}return {code_units:s.length,adler32_utf16:String((b*65536+a)>>>0)}})()"
    steps = [{'op': 'advance', 'ms': 4100},
             {'op': 'eval', 'code': "Value('User Script'," + json.dumps(observer) + ");__host.command('RunUserScript(false)')"},
             {'op': 'eval', 'code': summary}, {'op': 'save', 'path': str(output)}]
    scenario = folder / 'scenario.json'
    scenario.write_text(json.dumps({'steps': steps, 'dialogs': [{'title': 'DIALOG DEFAULTS QUALIFICATION', 'result': 'ok'}]}))
    report = {'passed': False, 'scope': __doc__, 'reader': str(a.reader.resolve()),
              'observer_sha256': reference['observer_sha256'], 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
    try:
        with (folder / 'probe.log').open('w') as log:
            result = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(folder / 'probe.json')],
                                    stdout=log, stderr=log, timeout=300,
                                    env=dict(os.environ, MPMB_DIALOG_TRACE_DIR=str(folder / 'dialogs')))
        data = json.loads((folder / 'probe.json').read_text())
        assert result.returncode == 0 and data['passed'] and not data['diagnostics']['errors']
        assert list((folder / 'dialogs').glob('dialog-*.json')), 'Diagnostic dialog was not executed'
        report['state'] = style.saved_capture(output, data['stages'][2]['result'], source)
        assert report['state'] == reference['state'], (report['state'], reference['state'])
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
