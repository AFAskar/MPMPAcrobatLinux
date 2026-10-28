#!/usr/bin/env python3
"""Qualify edited rich spans through native save/reopen and real Reader.

Diagnostic authored text, not class math. Mixed-face appearance fidelity and
edited defaultStyle/DA persistence are separate, incomplete qualifications.
All captured span properties are compared exactly, including optional keys.
"""
import argparse
import hashlib
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
from verify import canonical_fields, field_text, script_hashes, inspect

FIELD = 'Extra.Notes'
CAPTURE = "({value:f.valueAsString,spans:f.richValue})"
EDIT = r"""var f=getField('Extra.Notes');f.setAction('Keystroke','');f.setAction('Validate','');f.setAction('Format','');f.richText=true;f.multiline=true;f.richValue=[{text:'  First <&>  ',endParagraph:true,fontWeight:700,textColor:['RGB',.25,.5,.75],textSize:9},{text:'Second\rline',fontStyle:'italic',textSize:8}];"""
OBSERVER = r"""var iFileName='Observe rich persistence.js';(function(d){var f=d.getField('Extra.Notes');var v={value:f.valueAsString,spans:f.richValue,sentinel:'\u00a0\u2028\ud83d\ude00'};Value('PC Name',JSON.stringify(v).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);"""


def probe(binary, source, folder, name, steps):
    scenario, evidence = folder / (name + '-scenario.json'), folder / (name + '-probe.json')
    scenario.write_text(json.dumps({'dialogs': [{'result': 'ok'}] * 30, 'alerts': [1] * 30, 'steps': [{'op': 'advance', 'ms': 4100}] + steps}))
    with (folder / (name + '.log')).open('w') as log:
        proc = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(evidence)], stdout=log, stderr=log, timeout=240)
    data = json.loads(evidence.read_text())
    assert proc.returncode == 0 and data['passed'], data.get('error')
    return data


def appearances(node):
    return [hashlib.sha256(ref.get_object()['/AP']['/N'].get_object().get_data()).hexdigest() for ref in node.get('/Kids', [node]) if ref.get_object().get('/AP', {}).get('/N') is not None]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--readiness', type=Path)
    parser.add_argument('--native-only', action='store_true')
    parser.add_argument('--reader-authored', action='store_true', help='Create a separate original Reader reference from authored input, not native output')
    parser.add_argument('--fixture', choices=['2014','2024','ashnar'])
    args = parser.parse_args()
    if not args.native_only:
        assert args.readiness
        ready = json.loads(args.readiness.read_text())
        assert ready['passed'] and len(ready['cases']) == 24
    folder = ROOT / 'output/testing' / ('rich-persistence-' + str(time.time_ns()))
    folder.mkdir()
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'readiness': str(args.readiness), 'reader_authored': args.reader_authored, 'cases': []}
    print(folder, flush=True)
    try:
        for label, pattern in [('2014', '*_2014_*.pdf'), ('2024', '*_2024_*.pdf'), ('ashnar', 'Ashnar*.pdf')]:
            if args.fixture and args.fixture != label:
                continue
            source = next((ROOT / 'Testing').glob(pattern))
            original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            saved, restyled = folder / (label + '.pdf'), folder / (label + '-restyled.pdf')
            data = probe(binary, source, folder, label, [
                {'op': 'eval', 'code': '(function(){' + EDIT + 'return ' + CAPTURE + '})()'}, {'op': 'save', 'path': str(saved)},
                {'op': 'eval', 'code': "(function(){var f=getField('Extra.Notes');var r=f.richValue;r[0].fontWeight=400;r[1].textSize=10;f.richValue=r;return " + CAPTURE + "})()"}, {'op': 'save', 'path': str(restyled)}])
            before, expected = data['stages'][-4]['result'], data['stages'][-2]['result']
            assert before['value'] == expected['value'] and before['spans'] != expected['spans']
            a, b = PdfReader(saved), PdfReader(restyled)
            fa, fb = [reader.get_object(canonical_fields(reader)[FIELD]['reference']) for reader in (a, b)]
            assert field_text(fa['/RV']) != field_text(fb['/RV']), 'Style-only /RV edit lost'
            assert int(fb['/Ff']) & 33554432
            assert appearances(fa) != appearances(fb), 'Style-only appearance edit lost'
            validation = inspect(restyled, {FIELD: expected['value']})
            assert validation['passed'], validation
            render = folder / (label + '-native-page')
            subprocess.run(['pdftoppm', '-f', '3', '-l', '3', '-scale-to', '1400', '-singlefile', '-png', str(restyled), str(render)], check=True, capture_output=True, timeout=90)
            for path in [saved, restyled]:
                assert script_hashes(path) == script_hashes(source)
            reopened = probe(binary, restyled, folder, label + '-reopen', [{'op': 'eval', 'code': "(function(){var f=getField('Extra.Notes');return " + CAPTURE + "})()"}])['stages'][-1]['result']
            assert reopened == expected, (reopened, expected)
            case = {'fixture': label, 'passed': False, 'native': str(restyled), 'expected': expected, 'native_reopen': reopened, 'style_only_rv_changed': True, 'style_only_appearance_changed': True, 'independent': validation, 'render': str(render.with_suffix('.png'))}
            report['cases'].append(case)
            if not args.native_only:
                with c.desktop_lock():
                    assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow' and '.pdf' in e.get('name', '').lower()], 'Pre-existing Reader document'
                    remote = 'runs/rich-persistence-' + str(time.time_ns()) + '-' + label + '.pdf'
                    if args.reader_authored:
                        original_remote = {'2014':'blank-2014.pdf','2024':'blank-2024.pdf','ashnar':'ashnar.pdf'}[label]
                        c.powershell('Copy-Item '+c.literal(c.remote_path('fixtures/'+original_remote))+' '+c.literal(c.remote_path(remote))+' -Force;(Get-Item '+c.literal(c.remote_path(remote))+').IsReadOnly=$false')
                    else:
                        subprocess.run(c.SCP + [str(restyled), 'mpmb-test@127.0.0.1:MPMB-Testing/' + remote], capture_output=True, check=True)
                    path = c.remote_path(remote)
                    observer = OBSERVER
                    if args.reader_authored:
                        author = '(function(d){'+EDIT.replace('getField(', 'd.getField(')+"var r=f.richValue;r[0].fontWeight=400;r[1].textSize=10;f.richValue=r;})(tDoc);"
                        observer = observer.replace('(function(d){', author+'(function(d){', 1)
                    c.script('set', path=path, values={'User Script': observer})
                    c.script('call', path=path, name='RunUserScript', args=[False])
                    summary = c.script('field_summary', path=path, fields=['PC Name'])['fields']['PC Name']
                    c.script('set', path=path, values={'User Script': ''})
                    output = path[:-4] + '-saved.pdf'
                    c.script('save', path=path, output=output)
                    c.script('close', path=output)
                    local = c.fetch(output, folder / (label + '-reader.pdf'))
                    stored = canonical_fields(PdfReader(local))['PC Name']['/V']
                    assert stored.isascii()
                    actual = json.loads(stored)
                    assert [ord(ch) for ch in actual['sentinel']] == [160, 8232, 128512]
                    aa, bb = 1, 0
                    for ch in stored:
                        aa = (aa + ord(ch)) % 65521
                        bb = (bb + aa) % 65521
                    assert summary == {'code_units': len(stored), 'adler32_utf16': str((bb * 65536 + aa) & 0xffffffff)}
                    assert script_hashes(local) == script_hashes(source)
                    case.update(reader=actual, reader_summary=summary, reader_saved=str(local))
                    assert {key:actual[key] for key in ['value','spans']} == expected, (actual, expected)
                    resaved = probe(binary, local, folder, label + '-reader-reopen', [{'op': 'eval', 'code': "(function(){var f=getField('Extra.Notes');return " + CAPTURE + "})()"}])['stages'][-1]['result']
                    case['reader_saved_native_state'] = resaved
                    assert resaved == expected, (resaved, expected)
                    case['reader_saved_native_reopen'] = True
            cleared, plain = folder / (label + '-cleared.pdf'), folder / (label + '-plain.pdf')
            probe(binary, restyled, folder, label + '-clear', [
                {'op': 'eval', 'code': "getField('Extra.Notes').richValue=[]"}, {'op': 'save', 'path': str(cleared)},
                {'op': 'eval', 'code': "getField('Extra.Notes').richText=false"}, {'op': 'save', 'path': str(plain)}])
            cleared_state = probe(binary, cleared, folder, label + '-clear-reopen', [{'op': 'eval', 'code': "(function(){var f=getField('Extra.Notes');return " + CAPTURE + "})()"}])['stages'][-1]['result']
            assert cleared_state == {'value': '', 'spans': []}, cleared_state
            plain_reader = PdfReader(plain)
            plain_field = plain_reader.get_object(canonical_fields(plain_reader)[FIELD]['reference'])
            assert '/RV' not in plain_field and not int(plain_field['/Ff']) & 33554432
            assert script_hashes(plain) == script_hashes(source) == script_hashes(cleared)
            case['native_clear_and_disable'] = True
            assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
            case['passed'] = True
            print(label, 'edited rich persistence PASS', flush=True)
        report['passed'] = True if not args.native_only else None
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (folder / 'persistence.json').write_text(json.dumps(report, indent=2) + '\n')
        print(folder / 'persistence.json', flush=True)


if __name__ == '__main__':
    main()
