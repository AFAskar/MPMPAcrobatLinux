#!/usr/bin/env python3
"""Open the original MPMB XFDF fallback dialog in the native renderer.

The startup source dialog uses its offered OK. The export dialog is actually
rendered with generated XML, captured, then closed through the native window.
This does not qualify physical copy/keyboard interaction or direct file export.
"""
import hashlib, json, os, shutil, subprocess, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]


def main():
    folder = ROOT / 'output/testing' / ('native-xfdf-desktop-' + str(time.time_ns())); folder.mkdir(); print(folder, flush=True)
    binary = folder / 'mpmb-reader'; shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    source = next((ROOT / 'Testing').glob('*_2024_*.pdf')); source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    trace = folder / 'dialogs'; capture = folder / 'ui'; capture.mkdir()
    report = {'passed': False, 'scope': __doc__, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'source': str(source), 'source_sha256': source_hash}
    notes = 'First **bold** & <line>\rSecond é'
    steps = [{'op': 'advance', 'ms': 4100}, {'op': 'edit', 'field': 'PC Name', 'value': 'Native XFDF export'}, {'op': 'edit', 'field': 'Player Name', 'value': 'A\u00a0\u03a9'}, {'op': 'edit', 'field': 'Notes.Left', 'value': notes}, {'op': 'assert', 'values': {'Notes.Left': notes}}, {'op': 'eval', 'code': "__host.command(\"MakeXFDFExport('description')\")"}, {'op': 'assert', 'values': {'Notes.Left': notes}}, {'op': 'save', 'path': str(folder / 'native.pdf')}]
    scenario = {'interactive': True, 'dialogs': [{'title': 'SOURCE SELECTION DIALOG', 'result': 'ok'}], 'alerts': [1] * 10, 'steps': steps}
    (folder / 'scenario.json').write_text(json.dumps(scenario))
    env = {**os.environ, 'DISPLAY': ':0', 'XDG_RUNTIME_DIR': '/run/user/1000', 'MPMB_UI_SMOKE_DIR': str(capture), 'MPMB_DIALOG_TRACE_DIR': str(trace)}
    try:
        with (folder / 'probe.log').open('w') as log:
            result = subprocess.run([str(binary), str(source), '--probe', str(folder / 'scenario.json'), str(folder / 'probe.json')], env=env, stdout=log, stderr=log, timeout=300)
        data = json.loads((folder / 'probe.json').read_text()); report['strict_probe_passed'] = data['passed']; assert result.returncode == 0 and data['passed'], data.get('error')
        dialogs = [json.loads(path.read_text()) for path in sorted(trace.glob('dialog-*.json'))]
        exports = [item for item in dialogs if item['description']['name'] == 'XFDF FILE CREATION DIALOG']; assert len(exports) == 1
        xml = exports[0]['values']['expo']; assert xml.startswith('<?xml') and 'Native XFDF export' in xml and 'First **bold** &amp; &lt;line&gt;' in xml
        (folder / 'dialog.xfdf').write_text(xml, encoding='utf-8'); report['exported_xml_sha256'] = hashlib.sha256(xml.encode()).hexdigest()
        assert (capture / 'dialog.png').is_file(); assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
        report['screenshot'] = str(capture / 'dialog.png'); report['dialog'] = exports[0]; report['passed'] = True
    except Exception as error: report['error'] = str(error); raise
    finally:
        (folder / 'desktop.json').write_text(json.dumps(report, indent=2) + '\n'); print(folder / 'desktop.json', flush=True)


if __name__ == '__main__': main()
