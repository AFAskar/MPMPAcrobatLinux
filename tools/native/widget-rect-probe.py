#!/usr/bin/env python3
"""Compare multi-widget rectangle getters, setters and saved geometry with Reader.

Translations retain widget size. This does not qualify appearance reflow or rotation.
"""
import argparse, hashlib, json, shutil, subprocess, sys, time
from pathlib import Path
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
from verify import canonical_fields, script_hashes
FIELD = 'Save Modifiers Title'
ADDON = r'''var iFileName='Widget rectangle probe.js';
(function(d){var f=d.getField('Save Modifiers Title'),g=d.getField('Save Modifiers Title.1'),rows=[];
 function rect(v){return v.map(function(x){return Math.round(x*1000)/1000})}
 function capture(label){rows.push({stage:label,base:rect(f.rect),first:rect(d.getField('Save Modifiers Title.0').rect),second:rect(g.rect)})}
 capture('initial');var r=f.rect;r[0]+=3;r[2]+=3;r[1]+=2;r[3]+=2;f.rect=r;capture('base translation');
 r=g.rect;r[0]-=4;r[2]-=4;r[1]-=3;r[3]-=3;g.rect=r;capture('indexed translation');
 r=g.rect;r[0]=999;capture('getter copy');rows.push({stage:'transport sentinel',value:'\u00a0\u2028\ud83d\ude00'});Value('PC Name',JSON.stringify(rows).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);'''


def geometry(path):
    reader = PdfReader(path); field = reader.get_object(canonical_fields(reader)[FIELD]['reference'])
    return [[round(float(x), 3) for x in ref.get_object()['/Rect']] for ref in field.get('/Kids', [field])]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--readiness', type=Path); parser.add_argument('--native-only', action='store_true')
    args = parser.parse_args()
    if not args.native_only:
        assert args.readiness
        qualification = json.loads(args.readiness.read_text())
        assert qualification['passed'] and len(qualification['cases']) == 24
    folder = ROOT / 'output/testing' / ('widget-rect-' + str(time.time_ns())); folder.mkdir()
    source = next((ROOT / 'Testing').glob('*_2024_*.pdf'))
    binary = folder / 'mpmb-reader'; shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    saved = folder / 'native.pdf'
    report = {'passed': False, 'scope': __doc__, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
              'addon_sha256': hashlib.sha256(ADDON.encode()).hexdigest(), 'readiness': str(args.readiness)}
    print(folder, flush=True)
    try:
        steps = [{'op': 'advance', 'ms': 4100}, {'op': 'eval', 'code': "getField('User Script').value=" + json.dumps(ADDON)},
                 {'op': 'eval', 'code': "__host.command('RunUserScript(false)')"}, {'op': 'advance', 'ms': 1000},
                 {'op': 'eval', 'code': "if(Array.from(What('PC Name')).some(c=>c.charCodeAt(0)>127))throw Error('Non-ASCII diagnostic');JSON.parse(What('PC Name'))"}, {'op': 'eval', 'code': "getField('User Script').value=''"}, {'op': 'save', 'path': str(saved)}]
        scenario, evidence = folder / 'scenario.json', folder / 'native.json'
        scenario.write_text(json.dumps({'dialogs': [{'result': 'ok'}] * 30, 'alerts': [1] * 30, 'steps': steps}))
        with (folder / 'native.log').open('w') as log:
            proc = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(evidence)], stdout=log, stderr=log, timeout=240)
        data = json.loads(evidence.read_text()); assert proc.returncode == 0 and data['passed'], data.get('error')
        payload = data['stages'][-3]['result']; assert [ord(ch) for ch in payload[-1]['value']] == [160, 8232, 128512]
        rows = report['native'] = payload[:-1]
        assert len(rows) == 4 and rows[0]['base'] == rows[0]['first']
        assert rows[1]['second'] == rows[0]['second'] and rows[2]['first'] == rows[1]['first']
        assert rows[3]['base'] == rows[2]['base'] and rows[3]['second'] == rows[2]['second']
        assert rows[1]['base'] == [v + delta for v, delta in zip(rows[0]['base'], [3, 2, 3, 2])]
        assert rows[2]['second'] == [round(v + delta, 3) for v, delta in zip(rows[0]['second'], [-4, -3, -4, -3])]
        report['native_geometry'] = geometry(saved)
        for index, name in enumerate(['first', 'second']):
            r = rows[-1][name]; assert report['native_geometry'][index] == [r[0], r[3], r[2], r[1]]
        assert script_hashes(saved) == script_hashes(source)
        # A new native process must reload the persisted geometry.
        reopen = folder / 'reopen.json'; reopen_spec = folder / 'reopen-scenario.json'
        reopen_spec.write_text(json.dumps({'dialogs': [{'result': 'ok'}] * 30, 'alerts': [1] * 30,
                                          'steps': [{'op': 'advance', 'ms': 4100}, {'op': 'eval', 'code': "[getField('Save Modifiers Title.0').rect,getField('Save Modifiers Title.1').rect].map(r=>r.map(x=>Math.round(x*1000)/1000))"}]}))
        with (folder / 'reopen.log').open('w') as log:
            proc = subprocess.run([str(binary), str(saved), '--probe', str(reopen_spec), str(reopen)], stdout=log, stderr=log, timeout=240)
        opened = json.loads(reopen.read_text()); assert proc.returncode == 0 and opened['passed']
        assert opened['stages'][-1]['result'] == [rows[-1]['first'], rows[-1]['second']]
        report['native_reopen'] = True
        if not args.native_only:
            with c.desktop_lock():
                assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow' and '.pdf' in e.get('name', '').lower()], 'No pre-existing reference document allowed'
                path = c.remote_path('runs/widget-rect-' + str(time.time_ns()) + '.pdf')
                c.powershell('Copy-Item ' + c.literal(c.remote_path('fixtures/blank-2024.pdf')) + ' ' + c.literal(path) + ' -Force;(Get-Item ' + c.literal(path) + ').IsReadOnly=$false')
                c.script('set', path=path, values={'User Script': ADDON}); c.script('call', path=path, name='RunUserScript', args=[False])
                text = c.script('read', path=path, fields=['PC Name'])['fields']['PC Name']; assert text.isascii()
                reader_payload = json.loads(text); assert [ord(ch) for ch in reader_payload[-1]['value']] == [160, 8232, 128512]
                report['reader'] = reader_payload[:-1]
                summary = c.script('field_summary', path=path, fields=['PC Name'])['fields']['PC Name']
                c.script('set', path=path, values={'User Script': ''})
                output = path[:-4] + '-saved.pdf'; c.script('save', path=path, output=output); c.script('close', path=output)
                local = c.fetch(output, folder / 'reader.pdf'); assert script_hashes(local) == script_hashes(source)
                report['reader_geometry'] = geometry(local)
                stored = canonical_fields(PdfReader(local))['PC Name']['/V']; assert stored.isascii() and stored == text
                a, b = 1, 0
                for ch in stored:
                    a = (a + ord(ch)) % 65521; b = (b + a) % 65521
                assert summary == {'code_units': len(stored), 'adler32_utf16': str((b * 65536 + a) & 0xffffffff)}
                report['reader_summary'] = summary; report['unicode_sentinel_verified'] = True
            report['passed'] = report['reader'] == rows and report['reader_geometry'] == report['native_geometry']
            assert report['passed'], 'Native and Reader rectangle behavior differs'
        else:
            report['passed'] = None
    except Exception as error:
        report['error'] = str(error); raise
    finally:
        (folder / 'rectangles.json').write_text(json.dumps(report, indent=2) + '\n'); print(folder / 'rectangles.json', flush=True)


if __name__ == '__main__':
    main()
