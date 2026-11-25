#!/usr/bin/env python3
"""Qualified Reader print-dialog cancellation and native print-state roundtrip.

Never invokes a Print button or submits a physical printer job. Output rendering
comparison against a Reader-printed file remains a separate qualification gap.
"""
import argparse, json, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
from verify import inspect, script_hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_report', type=Path)
    parser.add_argument('--readiness', type=Path, required=True)
    args = parser.parse_args()
    native = json.loads(args.native_report.read_text()); readiness = json.loads(args.readiness.read_text())
    assert native['passed'] and readiness['passed'] and len(readiness['cases']) == 24
    folder = args.native_report.resolve().parent / ('reader-printing-' + str(time.time_ns())); folder.mkdir()
    report = {'passed': False, 'readiness': str(args.readiness.resolve()), 'scope': __doc__, 'cases': []}
    print(folder, flush=True)
    try:
        with c.desktop_lock():
            for case in native['cases']:
                label = case['fixture']; source = Path(case['interactive_output']); remote_name = 'print-' + str(time.time_ns()) + '-' + label + '.pdf'; remote = c.remote_path('runs/' + remote_name)
                subprocess.run(c.SCP + [str(source), c.SCP_TARGET + ':MPMB-Testing/runs/' + remote_name], check=True, capture_output=True)
                expected = {'PC Name': 'PRINTVISIBLE', 'Attack.1.Description': 'PRINTVISIBLE', 'Attack.2.Description': 'PRINTHIDDEN', 'Attack.3.Description': 'PRINTSCREENONLY', 'Attack.4.Description': 'PRINTONLY'}
                fields = c.script('read', path=remote, fields=list(expected))
                assert fields['fields'] == expected, fields
                params = c.script('print_params', path=remote)
                ident = c.script_submit('call', path=remote, name='PrintTheSheet', args=[])
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    elements = c.command('inspect')
                    roots = [e for e in elements if e['name'] == 'Print' and e['class'] == '#32770']
                    if roots:
                        root = roots[0]; break
                    time.sleep(.1)
                else:
                    raise RuntimeError('Reader print dialog not found: ' + json.dumps(elements))
                screenshot = c.command('screenshot'); local_screenshot = c.fetch(screenshot['path'], folder / (label + '-print-dialog.png'))
                names = [e['name'] for e in elements if e.get('owner') == root['handle'] and e['name']]
                assert 'Cancel' in names and any('Print' in n for n in names), names
                c.command('invoke', name='Cancel', owner=root['handle'])
                result = c.script_result(ident)
                saved = remote[:-4] + '-saved.pdf'
                c.script('save', path=remote, output=saved); c.script('close', path=saved)
                local = c.fetch(saved, folder / (label + '-reader-saved.pdf'))
                independent = inspect(local, expected); assert independent['passed'], independent
                assert script_hashes(local) == script_hashes(source)
                comparison = folder / (label + '-comparison.json')
                with (folder / (label + '-comparison.log')).open('w') as log:
                    subprocess.run([sys.executable, str(ROOT / 'tools/native/compare.py'), str(source), str(local), str(comparison)], stdout=log, stderr=log, check=True)
                report['cases'].append({'fixture': label, 'passed': True, 'reader_print_params': params, 'print_dialog_names': names, 'screenshot': str(local_screenshot), 'result': result, 'reader_saved': str(local), 'comparison': str(comparison)})
                (folder / 'reader-printing.json').write_text(json.dumps(report, indent=2))
                print(label, 'Reader print cancel/save PASS', flush=True)
            report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        try:
            screenshot = c.command('screenshot'); c.fetch(screenshot['path'], folder / 'failure.png')
        except Exception as screenshot_error:
            report['screenshot_error'] = str(screenshot_error)
        raise
    finally:
        (folder / 'reader-printing.json').write_text(json.dumps(report, indent=2)); print(folder / 'reader-printing.json', flush=True)

if __name__ == '__main__':
    main()
