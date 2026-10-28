#!/usr/bin/env python3
"""Measure edited default styles through fresh native and real Reader reopen.

The 2024 Extra.Notes case changes size/alignment/color with unchanged text.
Five original controls also expose loaded default-appearance colors/fonts.
Reader authors its own original fixture; no expected state is written into a
reference output with a PDF library. This is bounded style persistence evidence.
"""
import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
from verify import canonical_fields, script_hashes
spec = importlib.util.spec_from_file_location('rich_persistence', ROOT / 'tools/native/rich-persistence.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
FIELD = 'Extra.Notes'
CONTROLS = "(function(){var result={};['Background Extra','Text.PRsheet.AL.asterisk','AC Shield Weight Title','AmmoLeft.Top.1','DCI.Title'].forEach(function(name){var c=tDoc.getField(name);result[name]={textFont:c.textFont,textColor:c.textColor};});return result;})()"
CAPTURE = "({value:f.valueAsString,defaultStyle:f.defaultStyle,textSize:f.textSize,textFont:f.textFont,textColor:f.textColor,alignment:f.alignment,spans:f.richValue,controls:" + CONTROLS + "})"
EDIT = "var f=getField('Extra.Notes');f.value='style probe';f.defaultStyle={textSize:9,alignment:'right',textColor:['RGB',0,0,1]};"
# This includes a nonempty rich value before changing defaults, so default and
# existing span styles must be recorded separately.
OBSERVER = r"""(function(d){var f=d.getField('Extra.Notes');var result=CAPTURE;result.sentinel='\u00a0\u2028\ud83d\ude00';Value('PC Name',JSON.stringify(result).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);""".replace('CAPTURE', CAPTURE)


def saved_capture(local, summary, source):
    text = canonical_fields(PdfReader(local))['PC Name']['/V']
    assert text.isascii()
    a, b = 1, 0
    for ch in text:
        a = (a + ord(ch)) % 65521
        b = (b + a) % 65521
    assert summary == {'code_units': len(text), 'adler32_utf16': str((b * 65536 + a) & 0xffffffff)}
    state = json.loads(text)
    assert [ord(ch) for ch in state.pop('sentinel')] == [160, 8232, 128512]
    assert script_hashes(local) == script_hashes(source)
    return state


def check_reference(path, source):
    reference = json.loads(path.read_text())
    assert reference['execution_completed'] and reference['reader_equal']
    for phase in ['before', 'reopened']:
        local = path.parent / ('reader-' + phase + '.pdf')
        assert script_hashes(local) == script_hashes(source)
        captured = json.loads(canonical_fields(PdfReader(local))['PC Name']['/V'])
        assert [ord(ch) for ch in captured.pop('sentinel')] == [160, 8232, 128512]
        assert captured == reference['reader_' + phase]
    return reference


def reader_native_roundtrip(folder, source, binary, report):
    output = folder / 'native.pdf'
    with c.desktop_lock():
        assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow' and '.pdf' in e.get('name', '').lower()], 'Pre-existing Reader document'
        remote = 'runs/native-default-style-' + str(time.time_ns()) + '.pdf'
        subprocess.run(c.SCP + [str(output), 'mpmb-test@127.0.0.1:MPMB-Testing/' + remote], capture_output=True, check=True)
        remote = c.remote_path(remote)
        report['native_reader_path'] = remote
        c.script('set', path=remote, values={'User Script': "var iFileName='Observe native default style.js';" + OBSERVER})
        request = c.script_submit('call', path=remote, name='RunUserScript', args=[False])
        report['native_reader_request'] = request
        c.script_result(request, timeout=180)
        summary = c.script('field_summary', path=remote, fields=['PC Name'])['fields']['PC Name']
        c.script('set', path=remote, values={'User Script': ''})
        saved = remote[:-4] + '-saved.pdf'
        c.script('save', path=remote, output=saved)
        c.script('close', path=saved)
        local = c.fetch(saved, folder / 'native-reader.pdf')
        actual = report['native_reader'] = saved_capture(local, summary, source)
        report['native_reader_summary'] = summary
        assert actual == report['native_before'], 'Reader changed native-authored default style'
        reopened = p.probe(binary, local, folder, 'native-reader-reopen', [
            {'op':'eval','code':"(function(){var f=getField('Extra.Notes');return " + CAPTURE + '})()'}])['stages'][-1]['result']
        report['native_reader_native_reopened'] = reopened
        assert reopened == actual
    report['independent'] = {}
    for local in [output, folder / 'native-reader.pdf']:
        inspected = p.inspect(local, {FIELD: report['native_before']['value']})
        report['independent'][local.name] = inspected
        assert inspected['passed'], inspected
        render = local.with_suffix('')
        subprocess.run(['pdftoppm','-f','3','-l','3','-scale-to','1400','-singlefile','-png',str(local),str(render)], capture_output=True, check=True)
    report['renders'] = [str(folder / name) for name in ['native.png','native-reader.png']]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-only', action='store_true')
    parser.add_argument('--native-only', action='store_true')
    parser.add_argument('--readiness', type=Path)
    parser.add_argument('--load-reference', action='store_true', help='Compare native loading of both saved Reader states exactly')
    parser.add_argument('--controls-only', action='store_true', help='Compare five source getters with an existing independent Reader measurement')
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--style-json', help='Diagnostic replacement defaultStyle object; default is size9/right/blue')
    args = parser.parse_args()
    assert not (args.reference_only and args.native_only)
    edit = EDIT
    if args.style_json is not None:
        style = json.loads(args.style_json)
        assert isinstance(style, dict)
        edit = "var f=getField('Extra.Notes');f.value='style probe';f.defaultStyle=" + json.dumps(style) + ';'
    if not args.native_only and not args.controls_only and not args.load_reference:
        assert args.readiness
        ready = json.loads(args.readiness.read_text())
        assert ready['passed'] and len(ready['cases']) == 24
    folder = ROOT / 'output/testing' / ('default-style-roundtrip-' + str(time.time_ns()))
    folder.mkdir()
    source = next((ROOT / 'Testing').glob('*_2024_*.pdf'))
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    binary = folder / 'mpmb-reader'
    shutil.copy2(args.binary or ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'readiness': str(args.readiness)}
    report['edit_sha256'] = hashlib.sha256(edit.encode()).hexdigest()
    print(folder, flush=True)
    try:
        if args.load_reference:
            assert args.reference and not args.reference_only and not args.controls_only
            reference = json.loads(args.reference.read_text())
            assert reference['execution_completed'] and reference['reader_equal']
            report['reference'] = str(args.reference.resolve())
            report['reference_sha256'] = hashlib.sha256(args.reference.read_bytes()).hexdigest()
            report['reader_loads'] = {}
            for phase in ['before', 'reopened']:
                local = args.reference.parent / ('reader-' + phase + '.pdf')
                preserved = hashlib.sha256(local.read_bytes()).hexdigest()
                assert script_hashes(local) == script_hashes(source)
                captured = json.loads(canonical_fields(PdfReader(local))['PC Name']['/V'])
                captured.pop('sentinel')
                assert captured == reference['reader_' + phase]
                native = p.probe(binary, local, folder, 'load-' + phase, [
                    {'op':'eval','code':"(function(){var f=getField('Extra.Notes');return " + CAPTURE + '})()'}])['stages'][-1]['result']
                report['reader_loads'][phase] = {'native':native, 'expected':captured}
                assert native == captured, 'Native load differs from saved Reader state: ' + phase
                assert hashlib.sha256(local.read_bytes()).hexdigest() == preserved
            assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
            report['passed'] = True
            report['execution_completed'] = True
            return
        if args.controls_only:
            assert args.reference and not args.reference_only
            reference = json.loads(args.reference.read_text())
            assert reference['execution_completed'] and reference['reader_equal']
            for phase in ['before', 'reopened']:
                local = args.reference.parent / ('reader-' + phase + '.pdf')
                assert script_hashes(local) == script_hashes(source)
                captured = json.loads(canonical_fields(PdfReader(local))['PC Name']['/V'])
                captured.pop('sentinel')
                assert captured == reference['reader_' + phase]
            data = p.probe(binary, source, folder, 'controls', [{'op':'eval','code':CONTROLS}])
            report['native_controls'] = data['stages'][-1]['result']
            report['reader_controls'] = reference['reader_before']['controls']
            report['reference'] = str(args.reference.resolve())
            report['reference_sha256'] = hashlib.sha256(args.reference.read_bytes()).hexdigest()
            report['controls_only'] = True
            assert report['native_controls'] == report['reader_controls'], 'Loaded color/font controls differ from Reader'
            assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
            report['passed'] = True
            report['execution_completed'] = True
            return
        if not args.reference_only:
            output = folder / 'native.pdf'
            data = p.probe(binary, source, folder, 'native', [
                {'op': 'eval', 'code': '(function(){' + edit + 'return ' + CAPTURE + '})()'},
                {'op': 'save', 'path': str(output)}])
            expected = report['native_before'] = data['stages'][-2]['result']
            reopened = p.probe(binary, output, folder, 'native-reopen', [
                {'op': 'eval', 'code': "(function(){var f=getField('Extra.Notes');return " + CAPTURE + '})()'}])['stages'][-1]['result']
            report['native_reopened'] = reopened
            report['native_equal'] = reopened == expected
            assert script_hashes(output) == script_hashes(source)
            if args.native_only:
                assert report['native_equal'], 'Edited default style changed after native reopen'
        if args.reference and not args.native_only and not args.reference_only:
            reference = check_reference(args.reference, source)
            report['reference'] = str(args.reference.resolve())
            report['reference_sha256'] = hashlib.sha256(args.reference.read_bytes()).hexdigest()
            report['reader_before'] = reference['reader_before']
            report['reader_reopened'] = reference['reader_reopened']
            assert report['native_equal'], 'Edited default style changed after native reopen'
            assert report['native_before'] == reference['reader_before'], 'Native assignment differs from Reader'
            assert report['native_reopened'] == reference['reader_reopened']
            reader_native_roundtrip(folder, source, binary, report)
            assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
            report['passed'] = True
            report['execution_completed'] = True
            return
        if not args.native_only:
            with c.desktop_lock():
                assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow' and '.pdf' in e.get('name', '').lower()], 'Pre-existing Reader document'
                remote = c.remote_path('runs/default-style-' + str(time.time_ns()) + '.pdf')
                report['reader_path'] = remote
                c.powershell('Copy-Item ' + c.literal(c.remote_path('fixtures/blank-2024.pdf')) + ' ' + c.literal(remote) + ' -Force;(Get-Item ' + c.literal(remote) + ').IsReadOnly=$false')
                for phase in ['before', 'reopened']:
                    addon = "var iFileName='Default style persistence.js';" + (('(function(d){' + edit.replace('getField(', 'd.getField(') + '})(tDoc);') if phase == 'before' else '') + OBSERVER
                    c.script('set', path=remote, values={'User Script': addon})
                    request = c.script_submit('call', path=remote, name='RunUserScript', args=[False])
                    report['reader_' + phase + '_request'] = request
                    c.script_result(request, timeout=180)
                    summary = c.script('field_summary', path=remote, fields=['PC Name'])['fields']['PC Name']
                    report['reader_' + phase + '_summary'] = summary
                    c.script('set', path=remote, values={'User Script': ''})
                    saved = remote[:-4] + '-saved.pdf'
                    c.script('save', path=remote, output=saved)
                    c.script('close', path=saved)
                    local = c.fetch(saved, folder / ('reader-' + phase + '.pdf'))
                    report['reader_' + phase] = saved_capture(local, summary, source)
                    if phase == 'before':
                        fresh = remote[:-4] + '-reopen.pdf'
                        c.powershell("$p=" + c.literal(saved) + ";$q=" + c.literal(fresh) + ";$s=[IO.File]::Open($p,'Open','Read','None');$s.Dispose();Copy-Item $p $q -Force;if((Get-FileHash $p).Hash -ne (Get-FileHash $q).Hash){throw 'Snapshot mismatch'}")
                        remote = fresh
                report['reader_equal'] = report['reader_before'] == report['reader_reopened']
                assert report['reader_equal'], 'Reader changed style after reopening'
                if not args.reference_only:
                    assert report['native_equal']
                    assert report['native_before'] == report['reader_before']
                    assert report['native_reopened'] == report['reader_reopened']
        if not args.reference_only and not args.native_only:
            reader_native_roundtrip(folder, source, binary, report)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
        report['passed'] = None if args.reference_only or args.native_only else True
        report['execution_completed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (folder / 'styles.json').write_text(json.dumps(report, indent=2) + '\n')
        print(folder / 'styles.json', flush=True)


if __name__ == '__main__':
    main()
