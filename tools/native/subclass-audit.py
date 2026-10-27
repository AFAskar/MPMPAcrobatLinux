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
# Build citation labels from original metadata; the host must still find the
# complete path in the actual dialog before accepting a scripted selection.
INVENTORY = """(function(){
 var isNewAcrobat=false;try{isNewAcrobat=/hamburger/i.test(app.listMenuItems().toSource())}catch(e){}
 function label(name,def,alt){var refs=parseSource(def.source||(alt&&alt.source))||[];
 var abbr=refs.filter(function(x){return CurrentSources.globalExcl.indexOf(x[0])===-1}).map(function(x){return isNewAcrobat?SourceList[x[0]].abbreviation:SourceList[x[0]].uniS});
 return name+(abbr.length?(isNewAcrobat?' ['+abbr.join(', ')+']':' '+abbr.join(' ')):'');}
 function sources(def,alt){return (parseSource(def.source||(alt&&alt.source))||[]).map(function(x){return {key:x[0],abbreviation:SourceList[x[0]].abbreviation}});}
 return Object.keys(ClassList).map(k=>({key:k,sources:sources(ClassList[k]),name:ClassList[k].name,label:label(ClassList[k].name,ClassList[k]),parsed:ParseClass(ClassList[k].name),excluded:testSource(k,ClassList[k],'classExcl'),subs:(ClassList[k].subclasses[1]||[]).map(s=>({key:s,sources:ClassSubList[s]&&sources(ClassSubList[s],ClassList[k]),name:ClassSubList[s]&&ClassSubList[s].subname,label:ClassSubList[s]&&label(ClassSubList[s].subname,ClassSubList[s],ClassList[k]),excluded:!ClassSubList[s]||testSource(s,ClassSubList[s],'classExcl'),parsed:ClassSubList[s]&&ParseClass(ClassSubList[s].fullname||ClassList[k].name+' ('+ClassSubList[s].subname+')')}))}));})()"""


def source_dialogs(fixture, target=None):
    startup = [{'title': SOURCE, 'result': 'ok'}] if fixture != 'ashnar' else []
    elements = [{'title': ELEMENTS, 'event': 'BTRA'}]
    books = []
    if target:
        cl, sub, excluded_books = target
        for book in excluded_books:
            books += [{'title': SOURCE, 'event': 'IncL', 'select': {'IncL': book['dialog_path']}}, {'title': SOURCE, 'event': 'BTL1'}]
        elements = [{'title': ELEMENTS, 'event': 'BTLA'},
                    {'title': ELEMENTS, 'event': 'BTR1', 'select': {'ExcL': [cl['label'], sub['label']]}}]
    return startup + [{'title': SOURCE, 'event': 'BTRA'}] + books + [{'title': SOURCE, 'event': 'bCla'}] + elements + [{'title': ELEMENTS, 'result': 'ok'}, {'title': SOURCE, 'result': 'ok'}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', choices=['2014', '2024', 'ashnar'], action='append')
    parser.add_argument('--isolate-shadowed', action='store_true', help='Test shadowed pairs with only the target class/subclass enabled through original source-element controls')
    parser.add_argument('--resume-report', type=Path, help='Skip cases already passed in a prior target-only shadowed-pair report; retains provenance')
    parser.add_argument('--class-key', action='append')
    parser.add_argument('--skip-class-key', action='append', help='Explicit separate-profile classes; recorded as unexercised in this suite')
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
            prior_passed = set()
            if args.resume_report:
                assert args.isolate_shadowed, 'Resume is limited to the explicit shadowed-profile suite'
                previous = json.loads(args.resume_report.read_text())
                for prior in previous['fixtures']:
                    if prior['fixture'] == fixture:
                        assert prior.get('profile_mode') == 'isolated-shadowed' or prior['profile'].startswith('All sourcebooks; only the target')
                        prior_passed |= {(c['class'], c['subclass']) for c in prior['cases'] if c['passed']}
                item['resumed_from'] = str(args.resume_report.resolve())
                item['previous_report_sha256'] = hashlib.sha256(args.resume_report.read_bytes()).hexdigest()
                item['previous_passing_cases'] = len(prior_passed)
            source_paths = []
            def leaves(options, path=()):
                for name, value in options.items():
                    if isinstance(value, dict):
                        yield from leaves(value, path + (name,))
                    else:
                        yield list(path + (name,))
            for request_path in sorted((folder / (fixture + '-inventory-dialogs')).glob('dialog-*.json')):
                request = json.loads(request_path.read_text())
                if request['description'].get('name') == SOURCE:
                    offered = list(leaves(request['values'].get('IncL', {})))
                    if len(offered) > len(source_paths): source_paths = offered
            candidates = []
            for cl in inventory:
                if cl['excluded'] or (not args.isolate_shadowed and (not cl['parsed'] or cl['parsed'][0] != cl['key'])):
                    item['not_exercised'].append({'class': cl['key'], 'reason': 'Excluded or shadowed by another class with this source profile', 'parsed': cl['parsed']}); continue
                for sub in cl['subs']:
                    if sub['excluded'] or (not args.isolate_shadowed and (not sub['parsed'] or sub['parsed'][:2] != [cl['key'], sub['key']])):
                        item['not_exercised'].append({'class': cl['key'], 'subclass': sub['key'], 'reason': 'Excluded or shadowed with this source profile', 'parsed': sub['parsed']}); continue
                    if args.isolate_shadowed and cl['parsed'] and cl['parsed'][0] == cl['key'] and sub['parsed'] and sub['parsed'][:2] == [cl['key'], sub['key']]:
                        item['not_exercised'].append({'class': cl['key'], 'subclass': sub['key'], 'reason': 'Selectable in all-source profile; this suite targets shadowed pairs only'}); continue
                    if (cl['key'], sub['key']) in prior_passed:
                        item['not_exercised'].append({'class': cl['key'], 'subclass': sub['key'], 'reason': 'Passed in referenced prior bounded report'}); continue
                    if args.skip_class_key and cl['key'] in args.skip_class_key:
                        item['not_exercised'].append({'class': cl['key'], 'subclass': sub['key'], 'reason': 'Explicit separate-profile class filter'}); continue
                    if args.class_key and cl['key'] not in args.class_key:
                        item['not_exercised'].append({'class': cl['key'], 'subclass': sub['key'], 'reason': 'Command class filter'}); continue
                    if args.subclass_key and sub['key'] not in args.subclass_key:
                        item['not_exercised'].append({'class': cl['key'], 'subclass': sub['key'], 'reason': 'Command subclass filter'}); continue
                    candidates.append((cl, sub))
                if not cl['subs']:
                    item['not_exercised'].append({'class': cl['key'], 'reason': 'No subclasses; separate base-class qualification required'})
            if args.isolate_shadowed:
                item['profile_mode']='isolated-shadowed'
                item['profile']='All-source starting profile; target class/subclass elements and recorded conflicting parent sourcebook exclusions per case'
                item['inventory_profile']='All sourcebooks and class elements enabled; used to identify shadowing'
            item['candidates']=[{'class':cl['key'],'subclass':sub['key']} for cl,sub in candidates]
            item['candidate_count']=len(candidates)
            for index, (cl, sub) in enumerate(candidates):
                if args.limit is not None and index >= args.limit:
                    item['not_exercised'].append({'class': cl['key'], 'subclass': sub['key'], 'reason': 'Command limit'}); continue
                label = fixture + '-' + str(index); output = folder / (label + '.pdf')
                excluded_books = []
                if args.isolate_shadowed:
                    # Original MergeElement moves every matching leaf label,
                    # including shared Ranger subclasses under both parents.
                    # Exclude conflicting parent books through the real source
                    # dialog, without disabling a source needed by the target.
                    required = {s['key'] for s in cl['sources'] + sub['sources']}
                    conflicts = [other for other in inventory if other['key'] != cl['key'] and any(s['key'] == sub['key'] for s in other['subs'])]
                    seen = set()
                    for other in conflicts:
                        for source_book in other['sources']:
                            if source_book['key'] in required or source_book['key'] in seen: continue
                            matches = [path for path in source_paths if path[-1].endswith('(' + source_book['abbreviation'] + ')')]
                            assert len(matches) == 1, {'source_book': source_book, 'actual_offered_paths': matches}
                            excluded_books.append(dict(source_book, dialog_path=matches[0])); seen.add(source_book['key'])
                case_sources = source_dialogs(fixture, (cl, sub, excluded_books) if args.isolate_shadowed else None)
                dialogs = case_sources + [{'event': 'r0CD', 'select': {'r0CD': cl['name']}}, {'event': 'r0SD', 'select': {'r0SD': sub['name']}}, {'event': 'r0LV', 'values': {'r0LV': '3'}}, {'result': 'ok'}] + [{'result': 'ok'}] * 300
                # Reset prior classes before selecting through the real dropdowns.
                steps = setup() + [{'op': 'eval', 'code': "__host.command(\"ApplyClasses('',false)\")"}, {'op': 'advance', 'ms': 1000}]
                # Clearing Ashnar may open a changes notification before selection.
                if fixture == 'ashnar':
                    dialogs.insert(len(case_sources), {'title': 'CHANGES ALERT DIALOG', 'result': 'ok'})
                steps += [{'op': 'edit', 'field': ability, 'value': '18'} for ability in ['Str', 'Dex', 'Con', 'Int', 'Wis', 'Cha']]
                steps += [{'op': 'eval', 'code': "__host.command('SelectClass()')"}, {'op': 'advance', 'ms': 1000}]
                if args.isolate_shadowed:
                    steps += [{'op':'eval','code':"var enabledClassKeys=Object.keys(ClassList).filter(function(k){return !testSource(k,ClassList[k],'classExcl')});if(enabledClassKeys.length!==1||enabledClassKeys[0]!=="+json.dumps(cl['key'])+")throw Error('Target-only source profile not applied');if(testSource("+json.dumps(sub['key'])+",ClassSubList["+json.dumps(sub['key'])+"],'classExcl'))throw Error('Target subclass excluded');"}]
                verify_class = 'if(!classes.known[' + json.dumps(cl['key']) + ']||classes.known[' + json.dumps(cl['key']) + '].subclass!==' + json.dumps(sub['key']) + ")throw Error('Wrong class/subclass selected');"
                if excluded_books:
                    verify_class = "if(" + json.dumps([book['key'] for book in excluded_books]) + ".some(function(k){return CurrentSources.globalExcl.indexOf(k)<0}))throw Error('Conflicting sourcebook exclusion not retained');" + verify_class
                steps += [{'op': 'eval', 'code': verify_class + "var chosenClass=What('Class and Levels');"}, {'op': 'assert', 'values': {'Character Level': '3'}}]
                if sub['key'] == 'druid-circle of wildfire':
                    steps += [{'op': 'eval', 'code': "var spiritPrefix=What('Template.extras.AScomp').split(',').filter(p=>p&&What(p+'Comp.Race')==='Wildfire Spirit')[0];if(!spiritPrefix)throw Error('Missing Wildfire Spirit');if(What(spiritPrefix+'Comp.Use.HD.Die')!==''||What(spiritPrefix+'Comp.Use.HD.Level')!=='')throw Error('Spirit must have empty hit dice');if(Number(What(spiritPrefix+'Comp.Use.HP.Max'))!==20)throw Error('Spirit level-3 HP must be 20');"}]

                for level in [5, 11, 20, 3]:
                    code = '__host.command("ApplyClasses("+JSON.stringify(chosenClass.replace(/\\s*\\d+\\s*$/,\'\')+\' ' + str(level) + '\')+",false)")'
                    steps += [{'op': 'eval', 'code': code}, {'op': 'advance', 'ms': 1000}, {'op': 'eval', 'code': verify_class}, {'op': 'assert', 'values': {'Character Level': str(level), 'Proficiency Bonus': str(2 + (level - 1) // 4)}}]
                steps += [{'op': 'save', 'path': str(output)}]
                rc, data, evidence = run(source, label, dialogs, steps)
                case = {'class': cl['key'], 'subclass': sub['key'], 'passed': rc == 0 and data['passed'], 'probe': evidence, 'error': data.get('error'), 'source_exclusions': excluded_books, 'feature_choices': 'Default responses only; unqualified', 'reader': 'not run'}; item['cases'].append(case)
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
        for fixture in report['fixtures']:
            attempted={(case['class'],case['subclass']) for case in fixture['cases']}
            fixture['unattempted_candidates']=[candidate for candidate in fixture.get('candidates',[]) if (candidate['class'],candidate['subclass']) not in attempted]
        (folder / 'subclasses.json').write_text(json.dumps(report, indent=2)); print(folder / 'subclasses.json', flush=True)

if __name__ == '__main__':
    main()
