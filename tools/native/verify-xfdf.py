#!/usr/bin/env python3
"""Compare Reader/native XFDF data, preserving value absence and rich run styles.

XML syntax/whitespace, numeric CSS spelling, adjacent equal-style text runs and
optional producer APIVersion are normalized explicitly. This is semantic export
comparison, not exact XML/API equality or import interoperability qualification.
"""
import argparse, hashlib, importlib.util, json, re, shutil, subprocess, sys, time
import xml.etree.ElementTree as ET
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
spec = importlib.util.spec_from_file_location('style', ROOT / 'tools/native/default-style-persistence.py')
style = importlib.util.module_from_spec(spec); spec.loader.exec_module(style)
NS = '{http://ns.adobe.com/xfdf/}'
XHTML = '{http://www.w3.org/1999/xhtml}'


def css(text):
    result = {}
    for declaration in text.split(';'):
        if not declaration.strip(): continue
        key, value = declaration.split(':', 1); key = key.strip(); value = value.strip()
        if key == 'font-family': value = [v.strip().strip("'\"") for v in value.split(',')]
        elif key == 'font-weight': value = {'bold': '700', 'normal': '400'}.get(value, value)
        elif re.fullmatch(r'-?\d+(?:\.\d+)?pt', value): value = float(value[:-2])
        result[key] = value
    return result


def rich_runs(body):
    assert body.tag == XHTML + 'body'
    runs = []
    def add(text, attributes):
        if not text: return
        if runs and runs[-1]['style'] == attributes: runs[-1]['text'] += text
        else: runs.append({'text': text, 'style': dict(attributes)})
    def walk(node, inherited):
        assert node.tag in [XHTML + tag for tag in ['body', 'p', 'span']]
        attributes = dict(inherited)
        for key, value in node.attrib.items():
            if key == 'style': attributes.update(css(value))
            elif key.endswith('}APIVersion'): continue
            elif key.endswith('}spec'): assert value == '2.0.2'
            else: attributes[key] = value
        add(node.text, attributes)
        for child in node:
            walk(child, attributes); add(child.tail, attributes)
    walk(body, {})
    return runs


def contents(xml):
    root = ET.fromstring(xml); assert root.tag == NS + 'xfdf'
    file = root.find(NS + 'f'); result = {'href': file.attrib['href'], 'fields': {}}
    def walk(node, prefix):
        assert node.tag == NS + 'field'
        name = prefix + ('.' if prefix else '') + node.attrib['name']
        children = node.findall(NS + 'field')
        values = node.findall(NS + 'value'); rich = node.findall(NS + 'value-richtext')
        if not children or values or rich:
            assert name not in result['fields'] and len(rich) <= 1
            result['fields'][name] = {'values': [n.text or '' for n in values], 'rich': rich_runs(rich[0][0]) if rich else None}
        for child in children: walk(child, name)
    fields = root.find(NS + 'fields')
    if fields is not None:
        for field in fields: walk(field, '')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reader', type=Path, required=True)
    parser.add_argument('--binary', type=Path, default=ROOT / 'target/debug/mpmb-reader')
    parser.add_argument('--expected-cases', type=int, default=7)
    args = parser.parse_args(); reference = json.loads(args.reader.read_text()); assert reference['passed']
    observer = Path(reference['observer']).read_text(); source = Path(reference['input'])
    assert hashlib.sha256(observer.encode()).hexdigest() == reference['observer_sha256']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == reference['input_sha256']
    folder = ROOT / 'output/testing' / ('native-xfdf-' + str(time.time_ns())); folder.mkdir(); print(folder, flush=True)
    binary = folder / 'mpmb-reader'; shutil.copy2(args.binary, binary)
    report = {'passed': False, 'scope': __doc__, 'reader': str(args.reader.resolve()), 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
    summary = "(function(){var s=getField('PC Name').valueAsString,a=1,b=0;for(var i=0;i<s.length;i++){a=(a+s.charCodeAt(i))%65521;b=(b+a)%65521}return {code_units:s.length,adler32_utf16:String((b*65536+a)>>>0)}})()"
    scenario = {'dialogs': [{'result': 'ok'}] * 20, 'alerts': [1] * 20, 'steps': [{'op': 'advance', 'ms': 4100}, {'op': 'eval', 'code': "Value('User Script'," + json.dumps(observer) + ')'}, {'op': 'eval', 'code': "__host.command('RunUserScript(false)')"}, {'op': 'eval', 'code': summary}, {'op': 'save', 'path': str(folder / 'native.pdf')}]}
    (folder / 'scenario.json').write_text(json.dumps(scenario))
    try:
        with (folder / 'probe.log').open('w') as log:
            process = subprocess.run([str(binary), str(source), '--probe', str(folder / 'scenario.json'), str(folder / 'probe.json')], stdout=log, stderr=log, timeout=300)
        native = json.loads((folder / 'probe.json').read_text()); report['strict_probe_passed'] = native['passed']; assert process.returncode == 0 and native['passed'], native.get('error')
        captured = style.saved_capture(folder / 'native.pdf', native['stages'][-2]['result'], source)
        report['captured'] = captured
        assert not captured['errors'] and not reference['captured']['errors']
        assert captured['metadata'] == reference['captured']['metadata'], 'API input fields differ'
        assert len(captured['cases']) == len(reference['captured']['cases']) == args.expected_cases
        report['cases'] = []
        for actual, expected in zip(captured['cases'], reference['captured']['cases']):
            assert actual['label'] == expected['label'] and actual['options'] == expected['options']
            label = actual['label']; (folder / ('native-' + label + '.xfdf')).write_text(actual['xml'], encoding='utf-8'); (folder / ('reader-' + label + '.xfdf')).write_text(expected['xml'], encoding='utf-8')
            a, e = contents(actual['xml']), contents(expected['xml'])
            check = {'label': label, 'semantic_equal': a == e, 'exact_xml_equal': actual['xml'] == expected['xml'], 'native': a, 'reader': e}; report['cases'].append(check)
            assert check['semantic_equal'], label + ' differs'
        assert hashlib.sha256(source.read_bytes()).hexdigest() == reference['input_sha256']
        report['passed'] = True
    except Exception as error: report['error'] = str(error); raise
    finally:
        (folder / 'xfdf.json').write_text(json.dumps(report, indent=2) + '\n'); print(folder / 'xfdf.json', flush=True)


if __name__ == '__main__': main()
