#!/usr/bin/env python3
"""Bounded read-only generated-field qualification.

Every supplied canonical/API value is compared, with explicit button-name
conversion. Populated text and choice appearances run in fresh eight-field
processes with768MiB address-space limits. Exact original ASCII uppercase
Format actions have fingerprinted display rules; /V stays unchanged.
Empty text appearances and unchecked button rendering are explicit gaps.
No PDF is written. The output directory must be new.
"""
from pathlib import Path
import sys, json, subprocess, resource, hashlib, time
root = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(root / 'tools/native'), str(root / 'tools/acrobat')]
from pypdf import PdfReader
from pypdf.generic import NameObject
from verify import canonical_fields, inspect
source_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
if len(sys.argv) < 2 or sys.argv[1] == '--help':
    print('Usage: verify-generated-fields.py PDF EXPECTED_API_JSON UNIQUE_OUTPUT_DIR')
    raise SystemExit(0 if len(sys.argv) > 1 else 2)
if sys.argv[1] == 'child':
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 ** 2, 768 * 1024 ** 2))
    pdf = Path(sys.argv[2])
    expected = json.loads(Path(sys.argv[3]).read_text())
    output = Path(sys.argv[4])
    r = inspect(pdf, expected)
    reader = PdfReader(pdf)
    nodes = canonical_fields(reader)
    rules = []
    for w in r['widgets']:
        if w['appearance_matches'] is False and expected[w['name']] and expected[w['name']].isascii():
            node = reader.get_object(nodes[w['name']]['reference'])
            action = node.get('/AA', {}).get('/F')
            if action:
                action = action.get_object()
                code = action.get('/JS', '')
                code = code.get_data().decode('utf-8') if hasattr(code, 'get_data') else str(code)
                sha = hashlib.sha256(code.encode()).hexdigest()
                if sha == '2e26e97cc0d3be3dae91797de20edcef7ea059d1e08b992de2dd5a6f103cc83a':
                    w['canonical_appearance_matches'] = w['appearance_matches']
                    w['formatted_appearance_matches'] = w['appearance_text'] == expected[w['name']].upper()
                    rules.append({'field': w['name'], 'format_sha256': sha, 'canonical': expected[w['name']], 'display': expected[w['name']].upper(), 'observed': w['appearance_text'], 'rule': 'Exact original pure uppercase Format action; ASCII values only, canonical /V remains strict'})
    r['display_rules'] = rules
    r['source_sha256'] = source_hash
    r['passed'] = r['actual'] == expected and {w['name'] for w in r['widgets']} == set(expected) and all((w['matches'] and (not w['visible'] or not expected[w['name']] or (w['appearance'] and w.get('formatted_appearance_matches', w['appearance_matches']))) for w in r['widgets']))
    r['peak_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    output.write_text(json.dumps(r))
    raise SystemExit(0 if r['passed'] else 1)
pdf = Path(sys.argv[1])
expected = json.loads(Path(sys.argv[2]).read_text())
folder = Path(sys.argv[3])
folder.mkdir()
report = {'passed': False, 'source_sha256': source_hash, 'expected_sha256': hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest(), 'scope': 'Canonical API comparison all supplied fields; POPULATED text/choice AP checks isolated in fresh processes of eight fields,768MiB AS each; raw button value/AS/AP presence retained separately, unchecked appearance interoperability/rendering and empty-text APs not qualified here. Exact original pure-uppercase Format actions are guarded and canonical/display expectations remain separate.', 'input': str(pdf), 'input_sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(), 'batches': [], 'buttons': []}
try:
    r = PdfReader(pdf)
    canon = canonical_fields(r)
    text = {}
    raw = []
    for k, wanted in expected.items():
        rec = canon[k]
        node = r.get_object(rec['reference'])
        value = rec['/V']
        logical = value
        literal = node.get('/V')
        flags = int(node.get('/Ff', 0))
        if rec['/FT'] == '/Btn' and (not flags & 65536):
            if isinstance(literal, NameObject):
                logical = str(literal)[1:]
            elif value == '':
                logical = 'Off'
        assert logical == wanted, ('Canonical/API mismatch', k, wanted, logical)
        raw.append({'field': k, 'raw': value, 'api': wanted, 'type': str(rec['/FT'])})
        if rec['/FT'] in ['/Tx', '/Ch']:
            if value:
                text[k] = value
        else:
            widgets = []

            def walk(ref):
                obj = ref.get_object()
                if obj.get('/Subtype') == '/Widget':
                    state = str(obj.get('/AS', ''))
                    normal = obj.get('/AP', {}).get('/N', {}).get_object()
                    keys = list(map(str, normal.keys())) if hasattr(normal, 'keys') else []
                    widgets.append({'AS': state, 'N_keys': keys, 'flags': int(obj.get('/F', 0))})
                    assert state in ['', '/Off'] if wanted == 'Off' else state == '/' + wanted
                    assert wanted == 'Off' or state in keys
                for child in obj.get('/Kids', []):
                    walk(child)
            walk(node)
            assert widgets
            report['buttons'].append({'field': k, 'raw': value, 'api': wanted, 'widgets': widgets})
    report['canonical'] = raw
    report['text_count'] = len(text)
    pairs = list(text.items())
    for start in range(0, len(pairs), 8):
        spec = folder / ('batch-' + str(start) + '.json')
        output = folder / ('batch-' + str(start) + '-result.json')
        spec.write_text(json.dumps(dict(pairs[start:start + 8])))
        with (folder / ('batch-' + str(start) + '.log')).open('w') as log:
            p = subprocess.run([sys.executable, __file__, 'child', str(pdf), str(spec), str(output)], stdout=log, stderr=log, timeout=120)
        point = {'start': start, 'returncode': p.returncode, 'output': str(output)}
        report['batches'].append(point)
        (folder / 'progress.json').write_text(json.dumps(report, indent=2))
        assert p.returncode == 0, point
        d = json.loads(output.read_text())
        assert d['passed'] and d['source_sha256'] == source_hash
        point['peak_kib'] = d['peak_kib']
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == source_hash
    report['passed'] = True
except Exception as e:
    report['error'] = str(e)
    raise
finally:
    (folder / 'verification.json').write_text(json.dumps(report, indent=2))
    print(folder, flush=True)
