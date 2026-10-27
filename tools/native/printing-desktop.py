#!/usr/bin/env python3
"""Inspect and cancel the real Linux print destination dialog using AT-SPI.

Run with Fedora's system Python (PyGObject + Atspi). No print job is submitted.
"""
import json, os, subprocess, time
from pathlib import Path
import gi
gi.require_version('Atspi', '2.0')
from gi.repository import Atspi
ROOT = Path(__file__).resolve().parents[2]


def walk(node):
    yield node
    for index in range(node.get_child_count()):
        child = node.get_child_at_index(index)
        if child is not None:
            yield from walk(child)


def main():
    folder = ROOT / 'output/testing' / ('native-print-desktop-' + str(time.time_ns()))
    folder.mkdir(parents=True)
    report = {'passed': False, 'cases': []}
    print(folder, flush=True)
    try:
        for fixture in ['2014', '2024']:
            source = next((ROOT / 'Testing').glob('*_' + fixture + '_*.pdf'))
            directory = folder / fixture
            env = os.environ.copy(); env['MPMB_UI_SMOKE_PRINT'] = '1'
            with (folder / (fixture + '.log')).open('w') as log:
                process = subprocess.Popen([str(ROOT / 'target/debug/mpmb-reader'), str(source), '--desktop-smoke', str(directory)], env=env, cwd=ROOT, stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 100
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            raise RuntimeError('Reader exited before print dialog: ' + str(process.returncode))
                        desktop = Atspi.get_desktop(0)
                        found = None
                        for index in range(desktop.get_child_count()):
                            app = desktop.get_child_at_index(index)
                            if app is not None and app.get_name() == 'zenity':
                                for node in walk(app):
                                    if node.get_name() == 'Print MPMB sheet':
                                        found = node; break
                            if found is not None:
                                break
                        if found is not None:
                            nodes = list(walk(found))
                            names = [node.get_name() for node in nodes if node.get_name()]
                            assert 'Save print PDF' in names, names
                            cancel = next(node for node in nodes if node.get_name() == 'Cancel')
                            subprocess.run(['spectacle', '--background', '--nonotify', '--activewindow', '--output', str(directory / 'print-destination.png')], check=True, timeout=10)
                            assert cancel.get_action_iface().do_action(0)
                            break
                        time.sleep(.25)
                    else:
                        raise RuntimeError('Native print destination dialog not found')
                    assert process.wait(timeout=30) == 0
                    data = json.loads((directory / 'desktop-result.json').read_text())
                    assert data['passed'] and data['diagnostics']['printJobs'] == [{'status': 'cancelled'}], data
                    report['cases'].append({'fixture': fixture, 'passed': True, 'dialog_names': names, 'evidence': str(directory / 'desktop-result.json')})
                    print(fixture, 'print dialog cancel PASS', flush=True)
                finally:
                    if process.poll() is None:
                        process.terminate(); process.wait(timeout=10)
        report['passed'] = True
    finally:
        (folder / 'desktop.json').write_text(json.dumps(report, indent=2))
        print(folder / 'desktop.json', flush=True)

if __name__ == '__main__':
    main()
