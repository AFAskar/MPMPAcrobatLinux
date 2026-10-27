#!/usr/bin/env python3
"""Select original source/class/subclass dialogs and audit progression/persistence.

Default feature replies leave feature-choice coverage incomplete. All-source
selection does not prove every source configuration or every predefined class.
"""
import argparse, hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import canonical_fields, inspect, script_hashes

SOURCE = 'SOURCE SELECTION DIALOG'
ELEMENTS = 'CLASSES OR ARCHETYPES SOURCE SELECTION DIALOG'
INVENTORY = "Object.keys(ClassList).map(k=>({key:k,name:ClassList[k].name,parsed:ParseClass(ClassList[k].name),excluded:testSource(k,ClassList[k],'classExcl'),subs:(ClassList[k].subclasses[1]||[]).map(s=>({key:s,name:ClassSubList[s]&&ClassSubList[s].subname,excluded:!ClassSubList[s]||testSource(s,ClassSubList[s],'classExcl'),parsed:ClassSubList[s]&&ParseClass(ClassSubList[s].fullname||ClassList[k].name+' ('+ClassSubList[s].subname+')')}))}))"


def source_dialogs(fixture):
    startup = [{'title': SOURCE, 'result': 'ok'}] if fixture != 'ashnar' else []
    return startup + [{'title': SOURCE, 'event': 'BTRA'}, {'title': SOURCE, 'event': 'bCla'}, {'title': ELEMENTS, 'event': 'BTRA'}, {'title': ELEMENTS, 'result': 'ok'}, {'title': SOURCE, 'result': 'ok'}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', choices=['2014', '2024', 'ashnar'], action='append')
    parser.add_argument('--class-key', action='append')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--subclass-key', action='append')
    args = parser.parse_args()
    folder = ROOT / 'output/testing' / ('native-subclasses-' + str(time.time_ns())); folder.mkdir(parents=True)
    report = {'passed': False, 'full_mpmb_compatibility': False, 'scope': __doc__, 'fixtures': []}
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report['binary_sha256'] = hashlib.sha256(binary.read_bytes()).hexdigest()
    print(folder, flush=True)

    def run(source, label, dialogs, steps):
        spec, evidence = folder / (label + '-scenario.json'), folder / (label + '-report.json')
        spec.write_text(json.dumps({'dialogs': dialogs, 'alerts': [1] * 300, 'steps': steps}))
        env = os.environ.copy(); env['MPMB_DIALOG_TRACE_DIR'] = str(folder / (label + '-dialogs'))
        with (folder / (label + '.log')).open('w') as log:
            proc = subprocess.run([str(binary), str(source), '--probe', str(spec), str(evidence)], stdout=log, stderr=log, env=env, timeout=300)
        data = json.loads(evidence.read_text())
        return proc.returncode, data, str(evidence)

    def setup():
        return [{'op': 'advance', 'ms': 4100}, {'op': 'eval', 'code': "__host.command('resourceDecisionDialog()')"}, {'op': 'advance', 'ms': 1000}]

    try:
        for fixture in args.fixture or ['2014', '2024', 'ashnar']:
            pattern = 'Ashnar*.pdf' if fixture == 'ashnar' else '*_' + fixture + '_*.pdf'
            source = next((ROOT / 'Testing').glob(pattern)); original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            rc, data, evidence = run(source, fixture + '-inventory', source_dialogs(fixture) + [{'result': 'cancel'}], setup() + [{'op': 'eval', 'code': "__host.command('SelectClass()')"}, {'op': 'eval', 'code': INVENTORY}])
            assert rc == 0 and data['passed'], data.get('error')
            inventory = data['stages'][-1]['result']
            item = {'fixture': fixture, 'profile': 'All sourcebooks and class elements enabled via original dialog buttons', 'inventory': evidence, 'cases': [], 'not_exercised': []}; report['fixtures'].append(item)
            candidates = []
            for cl in inventory:
                if cl['excluded'] or not cl['parsed'] or cl['parsed'][0] != cl['key']:
                    item['not_exercised'].append({'class': cl['key'], 'reason': 'Excluded or shadowed by another class with this source profile', 'parsed': cl['parsed']}); continue
                for sub in cl['subs']:
                    if sub['excluded'] or not sub['parsed'] or sub['parsed'][:2] != [cl['key'], sub['key']]:
                        item['not_exercised'].append({'class': cl['key'], 'subclass': sub['key'], 'reason': 'Excluded or shadowed with this source profile', 'parsed': sub['parsed']}); continue
                    if args.class_key and cl['key'] not in args.class_key:
                        item['not_exercised'].append({'class': cl['key'], 'subclass': sub['key'], 'reason': 'Command class filter'}); continue
                    if args.subclass_key and sub['key'] not in args.subclass_key:
                        item['not_exercised'].append({'class': cl['key'], 'subclass': sub['key'], 'reason': 'Command subclass filter'}); continue
                    candidates.append((cl, sub))
                if not cl['subs']:
                    item['not_exercised'].append({'class': cl['key'], 'reason': 'No subclasses; separate base-class qualification required'})
            for index, (cl, sub) in enumerate(candidates):
                if args.limit is not None and index >= args.limit:
                    item['not_exercised'].append({'class': cl['key'], 'subclass': sub['key'], 'reason': 'Command limit'}); continue
                label = fixture + '-' + str(index); output = folder / (label + '.pdf')
                dialogs = source_dialogs(fixture) + [{'event': 'r0CD', 'select': {'r0CD': cl['name']}}, {'event': 'r0SD', 'select': {'r0SD': sub['name']}}, {'event': 'r0LV', 'values': {'r0LV': '3'}}, {'result': 'ok'}] + [{'result': 'ok'}] * 300
                # Reset prior classes before selecting through the real dropdowns.
                steps = setup() + [{'op': 'eval', 'code': "__host.command(\"ApplyClasses('',false)\")"}, {'op': 'advance', 'ms': 1000}]
                # Clearing Ashnar may open a changes notification before selection.
                if fixture == 'ashnar':
                    dialogs.insert(len(source_dialogs(fixture)), {'title': 'CHANGES ALERT DIALOG', 'result': 'ok'})
                steps += [{'op': 'edit', 'field': ability, 'value': '18'} for ability in ['Str', 'Dex', 'Con', 'Int', 'Wis', 'Cha']]
                steps += [{'op': 'eval', 'code': "__host.command('SelectClass()')"}, {'op': 'advance', 'ms': 1000}]
                verify_class = 'if(!classes.known[' + json.dumps(cl['key']) + ']||classes.known[' + json.dumps(cl['key']) + '].subclass!==' + json.dumps(sub['key']) + ")throw Error('Wrong class/subclass selected');"
                steps += [{'op': 'eval', 'code': verify_class + "var chosenClass=What('Class and Levels');"}, {'op': 'assert', 'values': {'Character Level': '3'}}]
                if sub['key'] == 'druid-circle of wildfire':
                    steps += [{'op': 'eval', 'code': "var spiritPrefix=What('Template.extras.AScomp').split(',').filter(p=>p&&What(p+'Comp.Race')==='Wildfire Spirit')[0];if(!spiritPrefix)throw Error('Missing Wildfire Spirit');if(What(spiritPrefix+'Comp.Use.HD.Die')!==''||What(spiritPrefix+'Comp.Use.HD.Level')!=='')throw Error('Spirit must have empty hit dice');if(Number(What(spiritPrefix+'Comp.Use.HP.Max'))!==20)throw Error('Spirit level-3 HP must be 20');"}]

                for level in [5, 11, 20, 3]:
                    code = '__host.command("ApplyClasses("+JSON.stringify(chosenClass.replace(/\\s*\\d+\\s*$/,\'\')+\' ' + str(level) + '\')+",false)")'
                    steps += [{'op': 'eval', 'code': code}, {'op': 'advance', 'ms': 1000}, {'op': 'eval', 'code': verify_class}, {'op': 'assert', 'values': {'Character Level': str(level), 'Proficiency Bonus': str(2 + (level - 1) // 4)}}]
                steps += [{'op': 'save', 'path': str(output)}]
                rc, data, evidence = run(source, label, dialogs, steps)
                case = {'class': cl['key'], 'subclass': sub['key'], 'passed': rc == 0 and data['passed'], 'probe': evidence, 'error': data.get('error'), 'feature_choices': 'Default responses only; unqualified', 'reader': 'not run'}; item['cases'].append(case)
                if case['passed']:
                    expected = {'Class and Levels': canonical_fields(PdfReader(output))['Class and Levels']['/V'], 'Character Level': '3', 'Proficiency Bonus': '2'}
                    independent = inspect(output, expected); assert independent['passed'], independent
                    assert script_hashes(output) == script_hashes(source)
                    rc, reopened, reopen_evidence = run(output, label + '-reopen', [{'result': 'ok'}] * 20, [{'op': 'advance', 'ms': 4100}, {'op': 'assert', 'values': expected}, {'op': 'eval', 'code': verify_class}])
                    case.update({'passed': rc == 0 and reopened['passed'], 'reopen': reopen_evidence, 'expected': expected, 'output': str(output), 'error': reopened.get('error')})
                print(fixture, sub['key'], 'PASS' if case['passed'] else 'FAIL', case.get('error') or '', flush=True)
                (folder / 'subclasses.json').write_text(json.dumps(report, indent=2))
                # Stop at concrete failures rather than generating hundreds of identical errors.
                assert case['passed'], case
            assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
        report['passed'] = all(f['cases'] and all(c['passed'] for c in f['cases']) for f in report['fixtures'])
    except Exception as error:
        report['error'] = str(error); raise
    finally:
        (folder / 'subclasses.json').write_text(json.dumps(report, indent=2)); print(folder / 'subclasses.json', flush=True)

if __name__ == '__main__':
    main()
