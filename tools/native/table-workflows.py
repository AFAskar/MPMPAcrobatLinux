#!/usr/bin/env python3
"""Use real limited features, short/long rests and healing in original class workflows.

Native evidence only here. Reader must independently create the same character
from its original fixture and execute the same user actions before comparison.
"""
import hashlib, json, shutil, subprocess, sys, time
from pathlib import Path
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import inspect, script_hashes


def main():
    folder = ROOT / 'output/testing' / ('native-table-' + str(time.time_ns())); folder.mkdir(parents=True)
    binary = folder / 'mpmb-reader'; shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'scope': __doc__, 'cases': []}
    print(folder, flush=True)
    def run(source, label, steps):
        scenario, evidence = folder / (label + '-scenario.json'), folder / (label + '-report.json')
        scenario.write_text(json.dumps({'dialogs': [{'result': 'ok'}] * 100, 'alerts': [1] * 100, 'steps': steps}))
        with (folder / (label + '.log')).open('w') as log:
            proc = subprocess.run([str(binary), str(source), '--probe', str(scenario), str(evidence)], cwd=ROOT, stdout=log, stderr=log, timeout=240)
        data = json.loads(evidence.read_text()); assert proc.returncode == 0 and data['passed'], data.get('error')
        return data, str(evidence)
    try:
        for fixture, pattern in [('2014', '*_2014_*.pdf'), ('2024', '*_2024_*.pdf'), ('ashnar', 'Ashnar*.pdf')]:
            source = next((ROOT / 'Testing').glob(pattern)); original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            for class_name in ['Fighter (Champion) 5', 'Monk (' + ('Warrior of Shadow' if fixture == '2024' else 'Way of Shadow') + ') 5']:
                label = fixture + '-' + class_name.split()[0].lower(); output = folder / (label + '.pdf')
                setup = "__host.command(" + json.dumps('ApplyClasses(' + json.dumps(class_name) + ',false)') + ')'
                collect = "var resourceFields=__host.names.filter(n=>/^Limited Feature(?: Max Usages| Recovery| Used)? \\d+$/.test(n));var characterFields=['Class and Levels','Character Level','Proficiency Bonus'];function readTableFields(names){var o={};names.forEach(n=>o[n]=getField(n).valueAsString);return o;}"
                use = "var usedFields=__host.names.filter(n=>/^Limited Feature \\d+$/.test(n)&&What(n)&&Number(What(n.replace('Limited Feature ','Limited Feature Max Usages ')))>0).map(n=>n.replace('Limited Feature ','Limited Feature Used '));if(!usedFields.length)throw Error('No usable class resource');usedFields.forEach(n=>Value(n,'1'));"
                capture = lambda phase, names: {'op': 'eval', 'code': "({phase:" + json.dumps(phase) + ',fields:readTableFields(' + names + ')})'}
                steps = [{'op': 'advance', 'ms': 4100}]
                steps += [{'op': 'edit', 'field': n, 'value': '18'} for n in ['Str', 'Dex', 'Con', 'Int', 'Wis', 'Cha']]
                steps += [{'op': 'eval', 'code': setup}, {'op': 'advance', 'ms': 1000}, {'op': 'assert', 'values': {'Character Level': '5', 'Proficiency Bonus': '3'}}, {'op': 'eval', 'code': collect}, capture('baseline', 'characterFields.concat(resourceFields)'), {'op': 'eval', 'code': use}, {'op': 'advance', 'ms': 1000}, capture('used', 'resourceFields'), {'op': 'eval', 'code': "__host.command(\"resetLimFeaUsed('short rest')\")"}, {'op': 'advance', 'ms': 1000}, capture('short-rest', 'resourceFields'), {'op': 'eval', 'code': "usedFields.forEach(n=>Value(n,'1'))"}, {'op': 'eval', 'code': "__host.command(\"resetLimFeaUsed('long rest')\")"}, {'op': 'advance', 'ms': 1000}, capture('long-rest', 'resourceFields')]
                health = {'HP Max': '30', 'HP Current': '7', 'HP Temp': '3', 'HD1 Used': '3'}
                steps += [{'op': 'edit', 'field': n, 'value': v} for n, v in health.items()]
                steps += [{'op': 'eval', 'code': "__host.command('HealItNow()')"}, {'op': 'advance', 'ms': 1000}, capture('healed', json.dumps(list(health))), {'op': 'save', 'path': str(output)}]
                data, evidence = run(source, label, steps)
                phases = {s['result']['phase']: s['result']['fields'] for s in data['stages'] if isinstance(s.get('result'), dict) and 'phase' in s['result']}
                assert set(phases) == {'baseline', 'used', 'short-rest', 'long-rest', 'healed'}
                assert any(phases['baseline'].get(k) != v for k, v in phases['used'].items()) and phases['used'] != phases['long-rest'], 'Resource use/rest did not change resource counters'
                expected = {'Character Level': '5', 'Proficiency Bonus': '3'} | phases['healed'] | phases['long-rest']
                independent = inspect(output, expected); assert independent['passed'], independent
                assert script_hashes(output) == script_hashes(source)
                _, reopen = run(output, label + '-reopen', [{'op': 'advance', 'ms': 4100}, {'op': 'assert', 'values': expected}])
                report['cases'].append({'fixture': fixture, 'class_input': class_name, 'passed': True, 'source': str(source), 'output': str(output), 'probe': evidence, 'reopen': reopen, 'phases': phases, 'health_input': health, 'expected': expected})
                assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
                (folder / 'table.json').write_text(json.dumps(report, indent=2)); print(label, 'resource/rest/healing/native persistence PASS', flush=True)
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error); raise
    finally:
        (folder / 'table.json').write_text(json.dumps(report, indent=2)); print(folder / 'table.json', flush=True)

if __name__ == '__main__':
    main()
