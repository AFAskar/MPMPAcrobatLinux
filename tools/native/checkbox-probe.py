#!/usr/bin/env python3
"""Compare checkbox runtime values and saved state with original add-ons in Reader.

An absent PDF /V is distinct from its logical runtime value Off. This probe
records both representations; it never writes computed native values to Reader.
"""
import argparse, hashlib, json, shutil, subprocess, sys, time
from pathlib import Path
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
from verify import canonical_fields, script_hashes

NAMES = ['Medium Armor', 'Heavy Armor', 'AC Stealth Disadvantage']
ADDON = '''var iFileName="Checkbox behavior probe.js";
(function(d){var names=['Medium Armor','Heavy Armor','AC Stealth Disadvantage'],rows=[];
 names.forEach(function(name){var f=d.getField(name),before=f.valueAsString,output=[];
  function capture(label){output.push({stage:label,value:f.valueAsString,valueType:typeof f.value,checked:f.isBoxChecked(0),checkedType:typeof f.isBoxChecked(0)});}
  try{capture('initial');f.value='';capture('assign blank');f.value='invalid';capture('assign invalid');f.value='Off';capture('assign Off');f.checkThisBox(0,false);capture('false');f.checkThisBox(0,true);capture('true');f.checkThisBox(0,true);capture('unchanged true');f.checkThisBox(0,false);capture('false after true');f.checkThisBox(0,false);capture('unchanged false after toggle');}
  finally{f.value=before;}
  rows.push({name:name,events:output});
 });Value('PC Name',JSON.stringify(rows));})(tDoc);'''


def values(path, names):
    fields = canonical_fields(PdfReader(path))
    return {name: fields[name]['/V'] for name in names}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--readiness', type=Path)
    parser.add_argument('--native-only', action='store_true')
    parser.add_argument('--clear-initially-checked', action='store_true', help='Also clear originally checked Ashnar proficiency fields, retaining all trace stages')
    parser.add_argument('--fixture', choices=['2014', '2024', 'ashnar'], action='append')
    args = parser.parse_args()
    names = NAMES + (['Dex ST Prof', 'Proficiency Weapon Other'] if args.clear_initially_checked else [])
    addon = ADDON.replace("['Medium Armor','Heavy Armor','AC Stealth Disadvantage']", json.dumps(names))
    if args.clear_initially_checked:
        addon = addon.replace('f.value=before;', 'f.checkThisBox(0,false);')
    if not args.native_only:
        assert args.readiness
        qualification = json.loads(args.readiness.read_text())
        assert qualification['passed'] and len(qualification['cases']) == 24
    folder = ROOT / 'output/testing' / ('checkbox-events-' + str(time.time_ns())); folder.mkdir()
    binary = folder / 'mpmb-reader'; shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'readiness': str(args.readiness) if args.readiness else None,
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'clear_initially_checked': args.clear_initially_checked, 'cases': []}
    print(folder, flush=True)
    try:
        # Native processes finish before acquiring the desktop; reference cases
        # then run through completion and cleanup without queuing another suite.
        for fixture, pattern in [('2014', '*_2014_*.pdf'), ('2024', '*_2024_*.pdf'), ('ashnar', 'Ashnar*.pdf')]:
            if args.fixture and fixture not in args.fixture:
                continue
            source = next((ROOT / 'Testing').glob(pattern)); saved = folder / (fixture + '-native.pdf')
            steps = [{'op': 'advance', 'ms': 4100}, {'op': 'eval', 'code': "getField('User Script').value=" + json.dumps(addon)},
                     {'op': 'eval', 'code': "__host.command('RunUserScript(false)')"}, {'op': 'advance', 'ms': 1000},
                     {'op': 'eval', 'code': "JSON.parse(What('PC Name'))"}, {'op': 'save', 'path': str(saved)}]
            scenario, evidence = folder / (fixture + '-scenario.json'), folder / (fixture + '-native.json')
            scenario.write_text(json.dumps({'dialogs': [{'result': 'ok'}] * 30, 'alerts': [1] * 30, 'steps': steps}))
            with (folder / (fixture + '-native.log')).open('w') as log:
                proc = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(evidence)], stdout=log, stderr=log, timeout=240)
            data = json.loads(evidence.read_text()); assert proc.returncode == 0 and data['passed'], data.get('error')
            assert script_hashes(saved) == script_hashes(source)
            report['cases'].append({'fixture': fixture, 'native': data['stages'][-2]['result'],
                                    'native_saved': str(saved), 'native_canonical': values(saved, names), 'source': str(source)})
        if not args.native_only:
            with c.desktop_lock():
                assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow' and '.pdf' in e.get('name', '').lower()], 'Reference suite requires no pre-existing document'
                for case in report['cases']:
                    fixture = case['fixture']; reference = 'ashnar.pdf' if fixture == 'ashnar' else 'blank-' + fixture + '.pdf'
                    path = c.remote_path('runs/checkbox-probe-' + str(time.time_ns()) + '-' + fixture + '.pdf')
                    c.powershell('Copy-Item ' + c.literal(c.remote_path('fixtures/' + reference)) + ' ' + c.literal(path) + ' -Force;(Get-Item ' + c.literal(path) + ').IsReadOnly=$false')
                    c.script('set', path=path, values={'User Script': addon})
                    c.script('call', path=path, name='RunUserScript', args=[False])
                    case['reader'] = json.loads(c.script('read', path=path, fields=['PC Name'])['fields']['PC Name'])
                    saved = path[:-4] + '-saved.pdf'; c.script('save', path=path, output=saved); c.script('close', path=saved)
                    local = c.fetch(saved, folder / (fixture + '-reader.pdf')); case['reader_saved'] = str(local)
                    case['reader_canonical'] = values(local, names)
                    assert script_hashes(local) == script_hashes(Path(case['source']))
                    case['runtime_equal'] = case['native'] == case['reader']
                    case['canonical_equal'] = case['native_canonical'] == case['reader_canonical']
                    case['passed'] = case['runtime_equal'] and case['canonical_equal']
                    (folder / 'checkbox-events.json').write_text(json.dumps(report, indent=2))
                    assert case['passed'], {'fixture': fixture, 'runtime_equal': case['runtime_equal'], 'canonical_equal': case['canonical_equal']}
                    print(fixture, 'checkbox runtime and canonical save PASS', flush=True)
            report['passed'] = True
        else:
            report['passed'] = None
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (folder / 'checkbox-events.json').write_text(json.dumps(report, indent=2)); print(folder / 'checkbox-events.json', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
