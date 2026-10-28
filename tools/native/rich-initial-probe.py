#!/usr/bin/env python3
"""Compare all initial rich text field getters in an authorized fixture.

No field actions are replaced. Optional getter errors are captured locally.
The only diagnostic writes are the add-on and its ASCII-escaped result carrier.
This measures initial getters, not progression, presentation or import fidelity.
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
from verify import canonical_fields, script_hashes

ADDON = r'''var iFileName='Initial rich getters.js';
(function(d){var result={fields:{},sentinel:'\u00a0\u2028\ud83d\ude00'};
 function read(f,key){try{var value=f[key];return value===undefined?{undefined_value:true}:JSON.parse(JSON.stringify(value))}catch(e){return {getter_error:String(e)}}}
 for(var i=0;i<d.numFields;i++){var name=d.getNthFieldName(i),f=d.getField(name);if(f.type!=='text'||!f.richText)continue;
  var row={};['valueAsString','richText','multiline','readonly','alignment','textSize','textFont','textColor','defaultStyle','richValue'].forEach(function(key){row[key]=read(f,key)});result.fields[name]=row;
 }
 Value('PC Name',JSON.stringify(result).replace(/[\u007f-\uffff]/g,function(c){return '\\u'+('0000'+c.charCodeAt(0).toString(16)).slice(-4)}));
})(tDoc);'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', choices=['2014', '2024', 'ashnar'], required=True)
    parser.add_argument('--native-only', action='store_true')
    parser.add_argument('--readiness', type=Path)
    args = parser.parse_args()
    if not args.native_only:
        assert args.readiness
        ready = json.loads(args.readiness.read_text())
        assert ready['passed'] and len(ready['cases']) == 24
    folder = ROOT / 'output/testing' / ('rich-initial-' + str(time.time_ns()))
    folder.mkdir()
    source = next((ROOT / 'Testing').glob({'2014': '*_2014_*.pdf', '2024': '*_2024_*.pdf', 'ashnar': 'Ashnar*.pdf'}[args.fixture]))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'fixture': args.fixture, 'readiness': str(args.readiness),
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'addon_sha256': hashlib.sha256(ADDON.encode()).hexdigest()}
    print(folder, flush=True)
    try:
        spec, evidence = folder / 'scenario.json', folder / 'native.json'
        spec.write_text(json.dumps({'dialogs': [{'result': 'ok'}] * 30, 'alerts': [1] * 30, 'steps': [
            {'op': 'advance', 'ms': 4100}, {'op': 'eval', 'code': "getField('User Script').value=" + json.dumps(ADDON)},
            {'op': 'eval', 'code': "__host.command('RunUserScript(false)')"},
            {'op': 'eval', 'code': "JSON.parse(What('PC Name'))"}]}))
        with (folder / 'native.log').open('w') as log:
            proc = subprocess.run([str(binary), str(source), '--probe', str(spec), str(evidence)], stdout=log, stderr=log, timeout=300)
        data = json.loads(evidence.read_text())
        assert proc.returncode == 0 and data['passed'], data.get('error')
        native = report['native'] = data['stages'][-1]['result']
        assert [ord(ch) for ch in native['sentinel']] == [160, 8232, 128512]
        report['rich_fields'] = len(native['fields'])
        assert report['rich_fields']
        if not args.native_only:
            with c.desktop_lock():
                assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow' and '.pdf' in e.get('name', '').lower()], 'Pre-existing Reader document'
                remote = c.remote_path('runs/rich-initial-' + str(time.time_ns()) + '.pdf')
                report['reader_path'] = remote
                fixture = 'ashnar.pdf' if args.fixture == 'ashnar' else 'blank-' + args.fixture + '.pdf'
                c.powershell('Copy-Item ' + c.literal(c.remote_path('fixtures/' + fixture)) + ' ' + c.literal(remote) + ' -Force;(Get-Item ' + c.literal(remote) + ').IsReadOnly=$false')
                c.script('set', path=remote, values={'User Script': ADDON})
                request = c.script_submit('call', path=remote, name='RunUserScript', args=[False])
                report['reader_request'] = request
                c.script_result(request, timeout=180)
                summary = c.script('field_summary', path=remote, fields=['PC Name'])['fields']['PC Name']
                c.script('set', path=remote, values={'User Script': ''})
                saved = remote[:-4] + '-saved.pdf'
                c.script('save', path=remote, output=saved)
                c.script('close', path=saved)
                local = c.fetch(saved, folder / 'reader.pdf')
                text = canonical_fields(PdfReader(local))['PC Name']['/V']
                assert text.isascii()
                a, b = 1, 0
                for ch in text:
                    a = (a + ord(ch)) % 65521
                    b = (b + a) % 65521
                assert summary == {'code_units': len(text), 'adler32_utf16': str((b * 65536 + a) & 0xffffffff)}
                actual = report['reader'] = json.loads(text)
                report['reader_summary'] = summary
                report['reader_saved'] = str(local)
                assert script_hashes(local) == script_hashes(source)
                report['differences'] = [name for name in sorted(native['fields'].keys() | actual['fields'].keys()) if native['fields'].get(name) != actual['fields'].get(name)]
                report['execution_completed'] = True
                report['passed'] = actual == native
        else:
            report['execution_completed'] = True
            report['passed'] = None
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (folder / 'getters.json').write_text(json.dumps(report, indent=2) + '\n')
        print(folder / 'getters.json', flush=True)
    return 0 if args.native_only or report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
