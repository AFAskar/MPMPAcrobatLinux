#!/usr/bin/env python3
"""Wrap one existing weapon Validate action in a disclosed diagnostic INPUT.

Keeps the exact original code once, with guarded before/after observations that
never assign event or field values. Requires a verified startup-observer input.
Canonical values/scripts/all other field actions must remain unchanged. This is
instrumentation preparation, not a native or Reader workflow pass.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools/acrobat'), str(ROOT/'tools/native')]
from verify import canonical_fields, script_hashes

spec = importlib.util.spec_from_file_location('workflow_preparation', ROOT/'tools/native/prepare-workflow-observer.py')
preparation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preparation)


def field_node(writer, name):
    seen = set()
    def walk(ref, prefix='', depth=0):
        assert depth < 64, 'Field tree exceeds diagnostic depth bound'
        node = ref.get_object()
        ident = getattr(ref, 'idnum', id(node))
        assert ident not in seen, 'Cyclic or repeated field reference'
        seen.add(ident)
        full = '.'.join(p for p in [prefix, str(node.get('/T', ''))] if p)
        if full == name:
            return node
        for child in node.get('/Kids', []):
            found = walk(child, full, depth+1)
            if found is not None:
                return found
        return None
    for ref in writer._root_object['/AcroForm']['/Fields']:
        found = walk(ref)
        if found is not None:
            return found
    raise ValueError('Target field is absent: '+name)


def observation(phase, original_sha, trace_property):
    prop = json.dumps(trace_property, ensure_ascii=True)
    overflow = json.dumps(trace_property+'Overflow', ensure_ascii=True)
    return ('\n(function(){try{var d=tDoc,a=d['+prop+']||(d['+prop+']=[]),r={phase:'+
            json.dumps(phase)+',original_sha256:'+json.dumps(original_sha)+'};'
            'try{r.field=event.target.name;}catch(e){r.field_error=String(e);}'
            'try{r.value=String(event.value);r.value_type=typeof event.value;}catch(e){r.value_error=String(e);}'
            'if(a.length<512)a.push(r);else d['+overflow+']=true;'
            '}catch(e){try{tDoc['+overflow+']=true;}catch(ignored){}}})();\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--instrumentation', type=Path, required=True)
    parser.add_argument('--field', default='Attack.1.Weapon Selection')
    parser.add_argument('--expect-action-sha256', required=True)
    parser.add_argument('--trace-property', default='__monkWeaponTrace')
    args = parser.parse_args()
    manifest = json.loads(args.instrumentation.read_text())
    source = Path(manifest['input'])
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert manifest['passed'] and manifest['mode'] == 'startup-script-timer'
    source_hash = digest(source)
    assert source_hash == manifest['input_sha256']
    before_reader = PdfReader(source)
    before_actions = preparation.field_actions(before_reader)
    field = before_reader.get_fields()[args.field]
    action = field['/AA']['/V'].get_object()
    assert action['/S'] == '/JavaScript', 'Requires a genuine JavaScript Validate action'
    literal = action['/JS']
    code = literal.get_data().decode('utf-8') if hasattr(literal, 'get_data') else str(literal)
    original_hash = hashlib.sha256(code.encode()).hexdigest()
    assert code and original_hash == args.expect_action_sha256, 'Original action fingerprint differs'
    wrapped = observation('before', original_hash, args.trace_property)+code+observation('after', original_hash, args.trace_property)
    assert wrapped.isascii() and wrapped.count(code) == 1
    folder = ROOT/'output/testing'/('weapon-validation-input-'+str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    writer = PdfWriter(clone_from=source)
    node = field_node(writer, args.field)
    # Detach both dictionaries: shared PDF action objects must not instrument
    # other fields as an accidental consequence of modifying this one.
    actions = DictionaryObject(node['/AA'].get_object())
    changed = DictionaryObject(actions['/V'].get_object())
    changed[NameObject('/JS')] = TextStringObject(wrapped)
    actions[NameObject('/V')] = writer._add_object(changed)
    node[NameObject('/AA')] = writer._add_object(actions)
    output = folder/'instrumented.pdf'
    writer.write(output)
    after_reader = PdfReader(output)
    strip = lambda rows: {name:{k:v for k,v in row.items() if k != 'reference'} for name,row in rows.items()}
    assert strip(canonical_fields(before_reader)) == strip(canonical_fields(after_reader))
    assert script_hashes(source) == script_hashes(output)
    after_actions = preparation.field_actions(after_reader)
    target = args.field+' /V'
    changed_keys = [k for k in sorted(set(before_actions)|set(after_actions)) if before_actions.get(k) != after_actions.get(k)]
    assert changed_keys == [target], ('Unexpected field-action changes', changed_keys)
    saved = str(after_reader.get_fields()[args.field]['/AA']['/V'].get_object()['/JS'])
    assert saved == wrapped and saved.count(code) == 1
    assert digest(source) == source_hash
    manifest.update(input=str(output), input_sha256=digest(output),
                    original_preparation=str(args.instrumentation.resolve()),
                    original_field_actions=before_actions, field_actions=after_actions,
                    canonical_comparison='All canonical properties exact except physical object reference IDs, which cloning can renumber',
                    field_action_wrapper={'field':args.field,'trigger':'/V','original_bytes':len(code.encode()),
                        'original_sha256':original_hash,'original_occurrences':1,
                        'wrapped_sha256':hashlib.sha256(wrapped.encode()).hexdigest(),
                        'changed_action_keys':changed_keys,'trace_property':args.trace_property,
                        'scope':__doc__})
    (folder/'input.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(folder/'input.json', flush=True)


if __name__ == '__main__':
    main()
