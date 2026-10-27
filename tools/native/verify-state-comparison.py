#!/usr/bin/env python3
"""Qualify serialized-state comparisons with a Reader baseline and damaged native copies."""
import argparse, hashlib, json, subprocess, sys, time
from pathlib import Path
from pypdf import PdfWriter
from pypdf.generic import NameObject, TextStringObject
ROOT = Path(__file__).resolve().parents[2]


def find_field(refs, wanted, prefix=''):
    for ref in refs:
        node = ref.get_object(); part = str(node.get('/T', ''))
        name = '.'.join(s for s in [prefix, part] if s)
        if name == wanted:
            return node
        result = find_field(node.get('/Kids', []), wanted, name)
        if result is not None:
            return result
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('native_report', type=Path); parser.add_argument('reader_report', type=Path)
    args = parser.parse_args()
    native, reader = [json.loads(p.read_text()) for p in [args.native_report, args.reader_report]]
    assert native['passed'] and reader['passed']
    case = native['cases'][0]
    reference = next(c for c in reader['cases'] if c['fixture'] == case['fixture'] and c['class_input'] == case['class_input'])
    source, oracle = Path(case['output']), Path(reference['reader_saved'])
    assert 'native-table-' in str(source), 'Negative controls require a disposable native table output'
    originals = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in [source, oracle]}
    folder = ROOT / 'output/testing' / ('state-verifier-' + str(time.time_ns())); folder.mkdir()
    comparer = ROOT / 'tools/native/compare-state.py'
    comparer_hash = hashlib.sha256(comparer.read_bytes()).hexdigest()
    report = {'passed': False, 'originals': originals, 'comparer_sha256': comparer_hash, 'cases': []}
    print(folder, flush=True)
    def compare(path, label):
        result_path = folder / (label + '.json')
        proc = subprocess.run([sys.executable, str(ROOT / 'tools/native/compare-state.py'), str(path), str(oracle), str(result_path)], capture_output=True, text=True, timeout=90)
        data = json.loads(result_path.read_text())
        assert proc.returncode in [0, 1], proc.stderr
        assert (proc.returncode == 0) == data['passed']
        return data, result_path
    try:
        baseline, path = compare(source, 'baseline'); assert baseline['passed'], baseline
        assert baseline['text_difference_count'] > 0, 'Baseline must exercise different MPMB source serialization'
        report['cases'].append({'name': 'different serialization, equal stored state', 'passed': True, 'comparison': str(path)})
        for label, field, value in [('missing-character-level', 'Character Level', None),
                                    ('changed-internal-state', 'CurrentVars.Stringified', '({})'),
                                    ('malformed-internal-state', 'CurrentVars.Stringified', '({broken)')]:
            writer = PdfWriter(clone_from=source)
            node = find_field(writer._root_object['/AcroForm']['/Fields'], field); assert node is not None
            if value is None:
                node.pop('/V', None)
            else:
                node[NameObject('/V')] = TextStringObject(value)
            damaged = folder / (label + '.pdf')
            with damaged.open('xb') as handle:
                writer.write(handle)
            data, result = compare(damaged, label); assert not data['passed'], label + ' was incorrectly accepted'
            if value is None:
                assert field in data['nonserialized_value_differences']
            else:
                assert not data['serialized_comparison'][field]['equal']
            report['cases'].append({'name': label, 'passed': True, 'damaged_native_copy': str(damaged), 'comparison': str(result)})
        assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest for p, digest in originals.items())
        assert hashlib.sha256(comparer.read_bytes()).hexdigest() == comparer_hash
        report['passed'] = True
    finally:
        (folder / 'verification.json').write_text(json.dumps(report, indent=2) + '\n'); print(folder / 'verification.json', flush=True)


if __name__ == '__main__':
    main()
