#!/usr/bin/env python3
"""Fresh native load/save/reopen of Reader-consumed native XFDF values and styles.

Matches full recorded Reader raw-rich getters and semantic re-export, retaining
its explicit import-generated line spacing. Uses original RunUserScript entry;
fields and original scripts are independently checked. No full layout claim.
"""
import argparse, hashlib, importlib.util, json, shutil, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import inspect, script_hashes
spec = importlib.util.spec_from_file_location('xfdf', ROOT / 'tools/native/verify-xfdf.py')
xfdf = importlib.util.module_from_spec(spec); spec.loader.exec_module(xfdf)
OBSERVER = r"""var iFileName='Read retained native XFDF data.js';Value('User Script','');(function(d){var r={phases:[],errors:[],sentinel:'\u00a0\u2028\ud83d\ude00'};['Player Name','Notes.Left'].forEach(function(name){try{var f=d.getField(name);r.phases.push({field:name,value:f.valueAsString,richText:f.richText,richValue:f.richText?f.richValue:null,xml:d.exportAsXFDFStr({aFields:[name],cHRef:'urn:mpmb:qualification'})})}catch(e){r.errors.push({field:name,name:e.name,message:e.message})}});Value('PC Name',JSON.stringify(r).replace(/[\u007f-\uffff]/g,function(ch){return '\\u'+('0000'+ch.charCodeAt(0).toString(16)).slice(-4)}));})(tDoc);"""
SUMMARY = "(function(){var s=getField('PC Name').valueAsString,a=1,b=0;for(var i=0;i<s.length;i++){a=(a+s.charCodeAt(i))%65521;b=(b+a)%65521}return {code_units:s.length,adler32_utf16:String((b*65536+a)>>>0)}})()"


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--reader', type=Path, required=True); args = p.parse_args()
    reader = json.loads(args.reader.read_text()); assert reader['passed'] and reader['producer'] == 'native' and reader['reader_control']
    source = args.reader.parent / 'reader.pdf'; source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    folder = ROOT / 'output/testing' / ('xfdf-persistence-' + str(time.time_ns())); folder.mkdir(); print(folder, flush=True)
    binary = folder / 'mpmb-reader'; shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    report = {'passed': False, 'scope': __doc__, 'reader': str(args.reader.resolve()), 'source_sha256': source_hash, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'phases': []}
    expected = {phase['field']: phase['value'] for phase in reader['captured']['phases']}
    try:
        for label in ['fresh-native', 'native-reopen']:
            output = folder / (label + '.pdf'); scenario = {'dialogs': [{'result': 'ok'}] * 10, 'alerts': [1] * 20, 'steps': [{'op': 'advance', 'ms': 4100}, {'op': 'assert', 'values': expected}, {'op': 'eval', 'code': "Value('User Script'," + json.dumps(OBSERVER) + ')'}, {'op': 'eval', 'code': "__host.command('RunUserScript(false)')"}, {'op': 'eval', 'code': SUMMARY}, {'op': 'save', 'path': str(output)}]}
            scenario_path = folder / (label + '-scenario.json'); evidence = folder / (label + '-probe.json'); scenario_path.write_text(json.dumps(scenario))
            with (folder / (label + '.log')).open('w') as log: run = subprocess.run([str(binary), str(source), '--probe', str(scenario_path), str(evidence)], stdout=log, stderr=log, timeout=300)
            data = json.loads(evidence.read_text()); assert run.returncode == 0 and data['passed'], data.get('error')
            captured = xfdf.style.saved_capture(output, data['stages'][-2]['result'], source); assert not captured['errors'] and len(captured['phases']) == 2
            checks = []
            for actual, reference in zip(captured['phases'], reader['captured']['phases']):
                check = {'field': actual['field'], 'getters_equal': all(actual[key] == reference[key] for key in ['field', 'value', 'richText', 'richValue']), 'reexport_equal': xfdf.contents(actual['xml']) == xfdf.contents(reference['xml'])}; checks.append(check); assert check['getters_equal'] and check['reexport_equal'], check
            independent = inspect(output, expected); assert independent['passed'] and script_hashes(output) == script_hashes(source)
            report['phases'].append({'label': label, 'output': str(output), 'probe': str(evidence), 'checks': checks, 'independent': independent}); source = output
        assert hashlib.sha256((args.reader.parent / 'reader.pdf').read_bytes()).hexdigest() == source_hash
        report['passed'] = True
    except Exception as error: report['error'] = str(error); raise
    finally:
        (folder / 'persistence.json').write_text(json.dumps(report, indent=2) + '\n'); print(folder / 'persistence.json', flush=True)


if __name__ == '__main__': main()
