#!/usr/bin/env python3
"""Read-only artifact checks for the three authored rich-span roundtrips.

Checks canonical values, visible widget appearances, original scripts, saved
Reader diagnostic integrity and independent Poppler renders. Pixel identity,
mixed-face rendering, defaultStyle edits and class math are not qualified.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
from verify import canonical_fields, field_text, inspect, script_hashes


def metadata(path):
    reader = PdfReader(path)
    result = {}
    for name, field in canonical_fields(reader).items():
        node = reader.get_object(field['reference'])
        if name != 'Extra.Notes':
            values = {}
            for key in ['/DS', '/RV']:
                if key not in node:
                    continue
                value = node[key].get_object()
                raw = value.get_data() if hasattr(value, 'get_data') else value.original_bytes
                values[key] = {'text': field_text(value), 'bytes_sha256': hashlib.sha256(raw).hexdigest()}
            result[name] = values
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    data = json.loads(args.report.read_text())
    assert data['passed'] and not data.get('reader_authored')
    assert sorted(case['fixture'] for case in data['cases']) == ['2014', '2024', 'ashnar']
    folder = ROOT / 'output/testing' / ('rich-persistence-verification-' + str(time.time_ns()))
    folder.mkdir()
    report = {'passed': False, 'scope': __doc__, 'input': str(args.report.resolve()),
              'input_sha256': hashlib.sha256(args.report.read_bytes()).hexdigest(), 'cases': []}
    try:
        for case in data['cases']:
            label = case['fixture']
            source = next((ROOT / 'Testing').glob({'2014': '*_2014_*.pdf', '2024': '*_2024_*.pdf', 'ashnar': 'Ashnar*.pdf'}[label]))
            scripts = script_hashes(source)
            native, saved = Path(case['native']), Path(case['reader_saved'])
            assert metadata(native) == metadata(source), 'Untouched native rich metadata changed'
            stored = canonical_fields(PdfReader(saved))['PC Name']['/V']
            assert stored.isascii() and json.loads(stored) == case['reader']
            assert [ord(ch) for ch in case['reader']['sentinel']] == [160, 8232, 128512]
            a, b = 1, 0
            for ch in stored:
                a = (a + ord(ch)) % 65521
                b = (b + a) % 65521
            assert case['reader_summary'] == {'code_units': len(stored), 'adler32_utf16': str((b * 65536 + a) & 0xffffffff)}
            for kind, path in [('native', native), ('reader', saved)]:
                assert script_hashes(path) == scripts
                result = inspect(path, {'Extra.Notes': case['expected']['value']})
                assert result['passed'], result
                assert result['pages'] == len(PdfReader(source).pages)
                render = folder / (label + '-' + kind)
                subprocess.run(['pdftoppm', '-f', '3', '-l', '3', '-singlefile', '-scale-to', '1400', '-png', str(path), str(render)], check=True, capture_output=True, timeout=90)
                report['cases'].append({'fixture': label, 'kind': kind, 'passed': True,
                                        'independent': result, 'render': str(render.with_suffix('.png'))})
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (folder / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
        print(folder / 'verification.json', flush=True)


if __name__ == '__main__':
    main()
