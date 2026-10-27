#!/usr/bin/env python3
"""Independently create native table scenarios in Reader from original fixtures.

Only user inputs (abilities, class choice, resource uses, HP and hit dice used)
are assigned. Calculated reference values are produced exclusively by Reader.
"""
import argparse, json, math, re, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
from verify import inspect, script_hashes


def apply_class(path, class_input, folder, label):
    ident=c.script_submit('call',path=path,name='ApplyClasses',args=[class_input,False])
    deadline=time.monotonic()+120;decisions=[]
    while time.monotonic()<deadline:
        elements=c.command('inspect')
        if any(e.get('name','').startswith('MPMB_RESULT') for e in elements):
            return c.script_result(ident),decisions
        questions=[e for e in elements if e.get('name')=='ASK USER DIALOG' and e.get('class')=='#32770']
        if questions:
            question=questions[0];names={e.get('name','') for e in elements if e.get('owner')==question['handle']}
            assert class_input.startswith('Monk ') and {'Select proficiencies','Tools','Monk'}<=names, 'Unexpected class question requires explicit test input'
            uia=c.command('inspect_uia');values=[e['value'] for e in uia if e.get('class')=='RICHEDIT50W' and e.get('value')]
            assert len(values)==1 and values[0].casefold() in ["artisan's tool or musical instrument","artisan's tools or musical instrument"], {'unqualified_tool_choice':values}
            shot=c.command('screenshot');image=c.fetch(shot['path'],folder/(label+'-tool-question-'+str(len(decisions))+'.png'))
            decisions.append({'dialog':'ASK USER DIALOG','regarding':'Tools','class':'Monk','input':values[0],'profile':'unchanged original default; tool-choice coverage remains unqualified','screenshot':str(image)})
            c.command('invoke',name='OK',owner=question['handle'])
        elif any(e.get('name')=='CHANGES ALERT DIALOG' for e in elements):
            return c.script_result(ident,timeout=90),decisions
        time.sleep(.1)
    raise RuntimeError('Class request did not complete: '+ident)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_report', type=Path)
    parser.add_argument('--readiness', type=Path, required=True)
    args = parser.parse_args()
    native = json.loads(args.native_report.read_text()); qualification = json.loads(args.readiness.read_text())
    assert native['passed'] and qualification['passed'] and len(qualification['cases']) == 24
    folder = args.native_report.resolve().parent / ('reader-table-' + str(time.time_ns())); folder.mkdir()
    report = {'passed': False, 'readiness': str(args.readiness.resolve()), 'cases': []}
    print(folder, flush=True)
    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class')=='AcrobatSDIWindow' and '.pdf' in e.get('name','').lower()], 'Reference suite requires no pre-existing document'
            for case in native['cases']:
                fixture = case['fixture']; label = fixture + '-' + case['class_input'].split()[0].lower()
                source = 'ashnar.pdf' if fixture == 'ashnar' else 'blank-' + fixture + '.pdf'
                path = c.remote_path('runs/table-reference-' + str(time.time_ns()) + '-' + label + '.pdf')
                c.powershell('Copy-Item ' + c.literal(c.remote_path('fixtures/' + source)) + ' ' + c.literal(path) + ' -Force;(Get-Item ' + c.literal(path) + ').IsReadOnly=$false')
                c.ensure_document(path)
                c.script('set', path=path, values={n: '18' for n in ['Str', 'Dex', 'Con', 'Int', 'Wis', 'Cha']})
                _,decisions=apply_class(path,case['class_input'],folder,label)
                phases = {}; phase_differences = {}; baseline_names = list(case['phases']['baseline'])
                resource_names = [n for n in baseline_names if n.startswith('Limited Feature')]
                def capture(phase, names):
                    actual = c.script('read', path=path, fields=names)['fields']; phases[phase] = actual
                    differences = {n: {'native': case['phases'][phase].get(n), 'reader': actual.get(n)} for n in set(actual) | set(case['phases'][phase]) if actual.get(n) != case['phases'][phase].get(n)}
                    (folder / (label + '-phases.json')).write_text(json.dumps(phases, indent=2))
                    if differences: phase_differences[phase] = differences
                capture('baseline', baseline_names)
                used = {}
                # Determine usable rows independently from Reader's actual class.
                for name, value in phases['baseline'].items():
                    match = re.fullmatch(r'Limited Feature (\d+)', name)
                    if not match or not value:
                        continue
                    try:
                        maximum = float(phases['baseline'].get('Limited Feature Max Usages ' + match[1], ''))
                    except (ValueError, TypeError):
                        continue
                    if math.isfinite(maximum) and maximum > 0:
                        used['Limited Feature Used ' + match[1]] = '1'
                assert used, 'Reader has no usable resource rows'
                c.script('set', path=path, values=used); capture('used', resource_names)
                c.script('call', path=path, name='resetLimFeaUsed', args=['short rest']); capture('short-rest', resource_names)
                c.script('set', path=path, values=used)
                c.script('call', path=path, name='resetLimFeaUsed', args=['long rest']); capture('long-rest', resource_names)
                c.script('set', path=path, values=case['health_input'])
                c.script('call', path=path, name='HealItNow', args=[]); capture('healed', list(case['health_input']))
                saved = path[:-4] + '-saved.pdf'; c.script('save', path=path, output=saved); c.script('close', path=saved)
                local = c.fetch(saved, folder / (label + '-reader.pdf'))
                independent = inspect(local, case['expected']); assert independent['passed'], independent
                assert script_hashes(local) == script_hashes(Path(case['source']))
                comparison = folder / (label + '-comparison.json')
                with (folder / (label + '-comparison.log')).open('w') as log:
                    subprocess.run([sys.executable, str(ROOT / 'tools/native/compare.py'), case['output'], str(local), str(comparison)], stdout=log, stderr=log, check=True)
                full = json.loads(comparison.read_text())
                report['cases'].append({'fixture': fixture, 'class_input': case['class_input'], 'passed': not phase_differences, 'phase_differences': phase_differences, 'explicit_dialog_defaults': decisions, 'phases': str(folder / (label + '-phases.json')), 'reader_saved': str(local), 'comparison': str(comparison), 'all_canonical_values_equal': full['field_values_equal'], 'canonical_difference_count': len(full.get('value_differences', []))})
                (folder / 'reader-table.json').write_text(json.dumps(report, indent=2)); print(label, 'independent Reader resource/rest/healing', 'FAIL' if phase_differences else 'PASS', flush=True)
                assert not phase_differences, {'case': label, 'differences': phase_differences}
            report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        try:
            shot = c.command('screenshot'); c.fetch(shot['path'], folder / 'failure.png')
        except Exception as screenshot_error:
            report['screenshot_error'] = str(screenshot_error)
        raise
    finally:
        (folder / 'reader-table.json').write_text(json.dumps(report, indent=2)); print(folder / 'reader-table.json', flush=True)

if __name__ == '__main__':
    main()
