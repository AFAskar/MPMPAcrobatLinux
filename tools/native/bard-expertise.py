#!/usr/bin/env python3
"""Original Bard expertise menu choices, expansion/removal and down-leveling.

This bounded Lore5 input has Dex14/Int12/Wis13/Cha20. Proficiencies are genuine
checkbox activations; expertise is chosen through actual offered class menus.
Reader equivalence and other class/ASI/feat choices remain separate gates.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import inspect, script_hashes
spec = importlib.util.spec_from_file_location('style', ROOT / 'tools/native/default-style-persistence.py')
style = importlib.util.module_from_spec(spec)
spec.loader.exec_module(style)
spec = importlib.util.spec_from_file_location('field_state', ROOT / 'tools/native/field-state-comparison.py')
field_state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(field_state)

PROFS = ['Acr Prof', 'Arc Prof', 'Perc Prof', 'Pers Prof']
SKILLS = ['Acr', 'Arc', 'Perc', 'Pers', 'His']
EXPECTED = {
    'expertise5': (['acrobatics', 'arcana'], [8, 7, 4, 8, 2]),
    'expertise9': (['acrobatics', 'arcana', 'perception', 'persuasion'], [10, 9, 9, 13, 3]),
    'removed-arcana': (['acrobatics', 'perception', 'persuasion'], [10, 5, 9, 13, 3]),
    'downleveled': ([], [4, 3, 3, 7, 1]),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    source = args.input.resolve()
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    observer = (ROOT / 'tools/native/bard-expertise-observer.js').read_text()
    folder = ROOT / 'output/testing' / ('native-bard-expertise-' + str(time.time_ns()))
    folder.mkdir()
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    print(folder, flush=True)
    report = {'passed': False, 'scope': __doc__, 'input': str(source), 'source_sha256': source_hash,
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
              'observer_sha256': hashlib.sha256(observer.encode()).hexdigest(), 'phases': []}
    steps = [{'op': 'advance', 'ms': 4100}, {'op': 'assert', 'values': {
        'Character Level': '5', 'Dex': '14', 'Int': '12', 'Wis': '13', 'Cha': '20'}},
        {'op': 'edit', 'field': 'PC Name', 'value': 'Bard compatibility'}]
    for name in PROFS:
        steps.append({'op': 'eval', 'code': 'if(getField(' + json.dumps(name) +
                      ').isBoxChecked(0))throw Error("Input proficiency already selected");__host.activate(' + json.dumps(name) + ')'})
    dialogs = []
    captures = []
    summary = "(function(){var s=getField('PC Name').valueAsString,a=1,b=0;for(var i=0;i<s.length;i++){a=(a+s.charCodeAt(i))%65521;b=(b+a)%65521}return {code_units:s.length,adler32_utf16:String((b*65536+a)>>>0)}})()"

    def choose(skill, count, maximum):
        dialogs.extend([{'title': 'MPMB menu', 'button_path': ['Bard (College of Lore)',
                        f'Expertise (selected {count} of {maximum})', skill]},
                        {'title': 'CHANGES ALERT DIALOG', 'result': 'ok'}])
        steps.extend([{'op': 'eval', 'code': "__host.activate('Class Features Menu')"}, {'op': 'advance', 'ms': 1000}])

    def capture(label):
        # This diagnostic carrier is read-only in the user-facing form. Match
        # Reader's programmatic assignment and original RunUserScript entry.
        steps.extend([{'op': 'eval', 'code': "Value('User Script'," + json.dumps(observer) + ')'},
                      {'op': 'eval', 'code': "__host.command('RunUserScript(false)')"}])
        index = len(steps)
        steps.append({'op': 'eval', 'code': summary})
        diagnostic = folder / (label + '-diagnostic.pdf')
        output = folder / (label + '.pdf')
        steps.extend([{'op': 'save', 'path': str(diagnostic)},
                      {'op': 'edit', 'field': 'PC Name', 'value': 'Bard compatibility'},
                      {'op': 'save', 'path': str(output)}])
        captures.append((label, index, diagnostic, output))

    choose('Acrobatics', 0, 2)
    choose('Arcana', 1, 2)
    capture('expertise5')
    steps.extend([{'op': 'eval', 'code': "__host.command(\"ApplyClasses('Bard (College of Lore) 9',false)\")"}, {'op': 'advance', 'ms': 1000}])
    dialogs.append({'title': 'CHANGES ALERT DIALOG', 'result': 'ok'})
    choose('Perception', 2, 4)
    choose('Persuasion', 3, 4)
    capture('expertise9')
    choose('Arcana', 4, 4)
    capture('removed-arcana')
    steps.extend([{'op': 'eval', 'code': "__host.command(\"ApplyClasses('Bard 1',false)\")"}, {'op': 'advance', 'ms': 1000}])
    dialogs.append({'title': 'CHANGES ALERT DIALOG', 'result': 'ok'})
    capture('downleveled')
    scenario = folder / 'scenario.json'
    scenario.write_text(json.dumps({'steps': steps, 'dialogs': dialogs, 'alerts': [1] * 40}))
    try:
        with (folder / 'probe.log').open('w') as log:
            process = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(folder / 'probe.json')],
                                     stdout=log, stderr=log, timeout=480)
        data = json.loads((folder / 'probe.json').read_text())
        assert process.returncode == 0 and data['passed'] and not data['diagnostics']['errors']
        for label, index, diagnostic, output in captures:
            state = style.saved_capture(diagnostic, data['stages'][index]['result'], source)
            expected_choices, totals = EXPECTED[label]
            assert state['choices'] == expected_choices
            assert all(state['fields'][name] == 'True' for name in PROFS)
            raw = field_state.compare(output, state['fields'])
            displays = {}
            for name, total in zip(SKILLS, totals):
                checked = inspect(output, {name: state['fields'][name]})
                displays[name] = [w['appearance_text'] for w in checked['widgets'] if w['visible']]
                assert displays[name] and all(t == '+' + str(total) for t in displays[name])
            assert script_hashes(output) == script_hashes(source)
            report['phases'].append({'label': label, 'state': state, 'pdf': str(output),
                                     'displays': displays, 'api_raw_comparison': raw})
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        target = folder / 'expertise.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
