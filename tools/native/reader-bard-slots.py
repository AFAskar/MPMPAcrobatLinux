#!/usr/bin/env python3
"""Spend real generated Bard slot checkboxes and qualify original short/long rests.

Uses named-field focus and Space, verifies each changed checkbox, saves/reopens
the spent state, then independently checks every saved selected slot field.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
from verify import canonical_fields, script_hashes
spec = importlib.util.spec_from_file_location('field_state', ROOT / 'tools/native/field-state-comparison.py')
field_state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(field_state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--readiness', type=Path, required=True)
    args = parser.parse_args()
    ready = json.loads(args.readiness.read_text())
    assert ready['passed'] and len(ready['cases']) == 24 and ready['harness_sha256'] == c.harness_fingerprint()
    source = args.input.resolve()
    reader = PdfReader(source)
    fields = canonical_fields(reader)
    prefixes = [row['/V'].split(',')[-1] for name, row in fields.items() if name == 'Template.extras.SSfront']
    assert len(prefixes) == 1 and prefixes[0]
    prefix = prefixes[0]
    boxes = []
    for page in reader.pages:
        for reference in page.get('/Annots', []):
            node = reference.get_object()
            chain = [node]
            while chain[-1].get('/Parent'):
                chain.append(chain[-1]['/Parent'].get_object())
            name = '.'.join(str(n['/T']) for n in reversed(chain) if n.get('/T'))
            if name.startswith(prefix + 'SpellSlots.Checkboxes.lvl') and not int(node.get('/F', 0)) & 34:
                assert fields[name]['/FT'] == '/Btn'
                boxes.append(name)
    boxes = sorted(set(boxes))
    assert len(boxes) == 9, ('Expected actual Bard5 4/3/2 visible slot controls', boxes)
    selected = [next(name for name in boxes if '.lvl' + str(level) + '.' in name) for level in [1, 2, 3]]
    names = boxes + [prefix + 'SpellSlots.CheckboxesSet.lvl' + str(i) for i in [1, 2, 3]]
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    folder = ROOT / 'output/testing' / ('reader-bard-slots-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    remote_base = c.remote_path('runs/bard-slots-' + str(time.time_ns()))
    remote = remote_base + '.pdf'
    opened = False
    report = {'passed': False, 'scope': __doc__, 'input': str(source), 'input_sha256': before,
              'readiness': str(args.readiness), 'boxes': boxes, 'selected': selected, 'names': names, 'phases': []}

    def capture(label):
        nonlocal remote
        values = c.script('read', path=remote, fields=names)['fields']
        saved = remote_base + '-' + label + '.pdf'
        c.script('save', path=remote, output=saved)
        remote = saved
        report['phases'].append({'label': label, 'fields': values, 'reader_path': saved})
        (folder / 'progress.json').write_text(json.dumps(report, indent=2) + '\n')
        assert [values[prefix + 'SpellSlots.CheckboxesSet.lvl' + str(i)] for i in [1, 2, 3]] == ['4', '3', '2']
        return values

    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow'
                        and '.pdf' in e.get('name', '').lower()], 'Pre-existing Reader document'
            subprocess.run(c.SCP + [str(source), c.SCP_TARGET + ':MPMB-Testing/runs/' +
                                    remote.replace('\\', '/').split('/')[-1]], check=True, capture_output=True)
            opened = True
            c.ensure_document(remote)
            loaded = capture('loaded')
            assert all(loaded[name] == 'Off' for name in boxes)
            report['activations'] = []
            for name in selected:
                focus = c.script('focus', path=remote, field=name)
                key = c.command('keys', keys=' ')
                values = c.script('read', path=remote, fields=names)['fields']
                assert values[name] == 'True', ('Named slot did not toggle', name)
                report['activations'].append({'field': name, 'focus': focus, 'key': key, 'fields': values})
            spent = capture('spent')
            assert all(spent[name] == ('True' if name in selected else 'Off') for name in boxes)
            c.script('call', path=remote, name='resetLimFeaUsed', args=['short rest'])
            assert capture('short-rest') == spent
            report['spent_close'] = c.script('close', path=remote)
            opened = False
            opened = True
            c.ensure_document(remote)
            assert capture('reopened-spent') == spent
            c.script('call', path=remote, name='resetLimFeaUsed', args=['long rest'])
            rested = capture('long-rest')
            assert all(rested[name] == 'Off' for name in boxes)
            report['close'] = c.script('close', path=remote)
            opened = False
            for phase in report['phases']:
                local = c.fetch(phase['reader_path'], folder / (phase['label'] + '.pdf'))
                phase['pdf'] = str(local)
                phase['api_raw_comparison'] = field_state.compare(local, phase['fields'])
                assert script_hashes(local) == script_hashes(source)
            assert hashlib.sha256(source.read_bytes()).hexdigest() == before
            report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    shot = c.command('screenshot')
                    c.fetch(shot['path'], folder / 'failure.png')
                    retained = remote_base + '-failed-retained.pdf'
                    c.script('save', path=remote, output=retained)
                    report['cleanup_close'] = c.script('close', path=retained)
                    c.fetch(retained, folder / 'failed-retained.pdf')
            except Exception as error:
                report['cleanup_error'] = str(error)
        target = folder / 'slots.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
