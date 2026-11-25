#!/usr/bin/env python3
"""Consume native-produced XFDF through Reader's real file picker and re-export.

This qualifies the string serializer's plain/rich interoperability, not original
MPMB's deprecated Import wrapper or every field/type. Reader receives only the
native API's generated files; expected data is never written into its PDF.
Reader-producer mode records an observational control, including any changes
Reader makes to its own XML. Native control comparisons retain every resulting
rich property; self-roundtrip equality is always recorded separately.
"""
import argparse, hashlib, importlib.util, json, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
from verify import inspect, script_hashes
spec = importlib.util.spec_from_file_location('xfdf', ROOT / 'tools/native/verify-xfdf.py')
xfdf = importlib.util.module_from_spec(spec); spec.loader.exec_module(xfdf)


def file_dialog(path, remote_pdf, events):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        elements = c.command('inspect')
        mains = [e for e in elements if e.get('class') == 'AcrobatSDIWindow' and remote_pdf.replace('\\', '/').split('/')[-1] in e.get('name', '')]
        assert len(mains) == 1, 'Expected the owned target Reader document'
        for root in [e for e in elements if e.get('class') == '#32770' and e.get('parent') == mains[0]['handle']]:
            children = [e for e in elements if e.get('owner') == root['handle']]
            labels = [e for e in children if e.get('class') == 'Static' and e.get('name', '').replace('&', '') == 'File name:']
            buttons = [e for e in children if e.get('class') == 'Button' and e.get('name', '').replace('&', '') == 'Open']
            if len(labels) != 1 or len(buttons) != 1: continue
            edits = [e for e in children if e.get('class') == 'Edit' and e.get('enabled') and e.get('read_only') is False and e['rect'][2] > 0 and e['rect'][3] > 0]
            combos = [e for e in edits if e.get('parent_class') in ['ComboBox', 'ComboBoxEx32']]
            if combos: edits = combos
            assert len(edits) == 1, 'Ambiguous filename edit'
            row = {'path': path, 'observed': elements}
            row['focus'] = c.command('focus_control', owner=root['handle'], handle=edits[0]['handle'])
            row['paste'] = c.command('paste', value=path); assert row['paste']['verified']
            row['verified'] = c.command('dialog_control', owner=root['handle'], handle=edits[0]['handle']); assert row['verified']['text'] == path
            row['open'] = c.command('invoke', name=buttons[0]['name'], owner=root['handle']); events.append(row)
            return
        time.sleep(.2)
    raise RuntimeError('Owned XFDF filename dialog did not appear')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--readiness', type=Path, required=True)
    parser.add_argument('--producer', choices=['native', 'reader'], default='native', help='Reader mode observes its own generated XFDF as a control')
    parser.add_argument('--reader-control', type=Path, help='Compare native import outcome with this Reader-produced import control; retain all style properties')
    args = parser.parse_args(); native = json.loads(args.native.read_text()); assert native['passed']
    reference = json.loads(Path(native['reader']).read_text()); source = Path(reference['input'])
    ready = json.loads(args.readiness.read_text()); assert ready['passed'] and len(ready['cases']) == 24 and ready['harness_sha256'] == c.harness_fingerprint()
    folder = ROOT / 'output/testing' / ('reader-xfdf-import-' + str(time.time_ns())); folder.mkdir(); print(folder, flush=True)
    remote = c.remote_path('runs/xfdf-import-' + str(time.time_ns()) + '.pdf'); opened = False; pending = None
    labels = ['single-name', 'rich']; files = [args.native.parent / (args.producer + '-' + label + '.xfdf') for label in labels]
    expected = {case['name']: case['text'] for case in native['captured']['metadata'] if case['name'] in ['Player Name', 'Notes.Left']}
    observer = r"""var iFileName='Native XFDF Reader consumption.js';Value('User Script','');(function(d){var r={phases:[],errors:[],sentinel:'\u00a0\u2028\ud83d\ude00'};['Player Name','Notes.Left'].forEach(function(name){try{d.importAnXFDF();var f=d.getField(name);r.phases.push({field:name,value:f.valueAsString,richText:f.richText,richValue:f.richText?f.richValue:null,xml:d.exportAsXFDFStr({aFields:[name],cHRef:'urn:mpmb:qualification'})})}catch(e){r.errors.push({field:name,name:e.name,message:e.message})}});Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(ch){return '\\u'+('0000'+ch.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);"""
    (folder / 'observer.js').write_text(observer)
    report = {'passed': False, 'scope': __doc__, 'producer': args.producer, 'reader_control': str(args.reader_control.resolve()) if args.reader_control else None, 'native': str(args.native.resolve()), 'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'readiness': str(args.readiness.resolve()), 'file_dialogs': [], 'inputs': []}
    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow' and '.pdf' in e.get('name', '').lower()], 'Pre-existing Reader document'
            uploads = [(source, remote)]
            for label, file in zip(labels, files):
                target = c.remote_path('runs/native-' + label + '-' + str(time.time_ns()) + '.xfdf')
                report['inputs'].append({'local': str(file.resolve()), 'remote': target, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()}); uploads.append((file, target))
            for local, target in uploads:
                subprocess.run(c.SCP + [str(local), c.SCP_TARGET + ':MPMB-Testing/runs/' + target.replace('\\', '/').split('/')[-1]], check=True, capture_output=True)
                assert c.powershell('(Get-FileHash -Algorithm SHA256 ' + c.literal(target) + ').Hash').strip().lower() == hashlib.sha256(local.read_bytes()).hexdigest()
            opened = True; c.ensure_document(remote)
            c.script('set', path=remote, values={'User Script': observer}); pending = c.script_submit('call', path=remote, name='RunUserScript', args=[False]); report['request'] = pending
            for item in report['inputs']: file_dialog(item['remote'], remote, report['file_dialogs'])
            report['completion'] = c.script_result(pending, timeout=90); pending = None
            summary = c.script('field_summary', path=remote, fields=['PC Name'])['fields']['PC Name']; report['summary'] = summary
            c.script('set', path=remote, values={'User Script': ''}); saved = remote[:-4] + '-saved.pdf'; c.script('save', path=remote, output=saved); remote = saved
            report['close'] = c.script('close', path=remote); opened = False; local = c.fetch(remote, folder / 'reader.pdf')
            captured = xfdf.style.saved_capture(local, summary, source); report['captured'] = captured
            assert not captured['errors'] and len(captured['phases']) == 2
            report['checks'] = []
            control = json.loads(args.reader_control.read_text()) if args.reader_control else None
            if control: assert control['passed'] and control['producer'] == 'reader' and control['native'] == str(args.native.resolve())
            for phase, input_file in zip(captured['phases'], files):
                check = {'field': phase['field'], 'canonical_equal': phase['value'] == expected[phase['field']], 'reader_reexport_semantic_equal': xfdf.contents(phase['xml']) == xfdf.contents(input_file.read_text())}
                report['checks'].append(check); assert check['canonical_equal'], check
                if control:
                    observed = next(item for item in control['captured']['phases'] if item['field'] == phase['field'])
                    check['reader_control_getters_equal'] = all(phase[key] == observed[key] for key in ['field', 'value', 'richText', 'richValue'])
                    check['reader_control_reexport_equal'] = xfdf.contents(phase['xml']) == xfdf.contents(observed['xml'])
                    assert check['reader_control_getters_equal'] and check['reader_control_reexport_equal'], check
                elif args.producer == 'native': assert check['reader_reexport_semantic_equal'], check
            report['self_roundtrip_semantic_equal'] = all(check['reader_reexport_semantic_equal'] for check in report['checks'])
            report['control_observation_only'] = args.producer == 'reader'
            report['independent'] = inspect(local, expected); assert report['independent']['passed']
            assert script_hashes(local) == script_hashes(source) and hashlib.sha256(source.read_bytes()).hexdigest() == report['source_sha256']
            report['passed'] = True
    except Exception as error: report['error'] = str(error); raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    shot = c.command('screenshot'); c.fetch(shot['path'], folder / 'failure.png')
                    if pending: report['original_completion'] = c.script_result(pending, timeout=25)
                    retained = remote[:-4] + '-failed-retained.pdf'; c.script('save', path=remote, output=retained); report['cleanup_close'] = c.script('close', path=retained); c.fetch(retained, folder / 'failed-retained.pdf')
            except Exception as error: report['cleanup_error'] = str(error)
        (folder / 'import.json').write_text(json.dumps(report, indent=2) + '\n'); print(folder / 'import.json', flush=True)


if __name__ == '__main__': main()
