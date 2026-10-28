#!/usr/bin/env python3
"""Original 2024 companion AC after native/Reader save, reopen and Dex change.

Only creature choice and Dexterity are supplied. Original MPMB actions compute
the AC display; the canonical formula must remain unchanged. This is one wolf
workflow, not complete companion, combat or formatting coverage.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from pypdf import PageObject, PdfReader
from pypdf.generic import NameObject

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
from verify import canonical_fields, script_hashes


def appearance(path, field):
    reader = PdfReader(path)
    node = reader.get_object(canonical_fields(reader)[field]['reference'])
    active = {ref.idnum for page in reader.pages for ref in page.get('/Annots', [])}
    texts = []
    for ref in node.get('/Kids', [node]):
        widget = ref.get_object()
        if widget.indirect_reference.idnum not in active:
            continue
        stream = widget['/AP']['/N'].get_object()
        page = PageObject.create_blank_page(width=500, height=500)
        page[NameObject('/Resources')] = stream['/Resources']
        page[NameObject('/Contents')] = stream
        texts.append(page.extract_text().strip())
    assert texts
    return texts



def render_ac(path, field):
    reader = PdfReader(path)
    node = reader.get_object(canonical_fields(reader)[field]['reference'])
    widgets = {ref.get_object().indirect_reference.idnum: ref.get_object() for ref in node.get('/Kids', [node])}
    for number, page in enumerate(reader.pages, 1):
        for ref in page.get('/Annots', []):
            if ref.idnum not in widgets:
                continue
            left, bottom, right, top = map(float, widgets[ref.idnum]['/Rect'])
            scale = 2
            output = path.with_suffix('')
            subprocess.run(['pdftoppm', '-f', str(number), '-l', str(number), '-r', '144',
                            '-x', str(max(0, int((left-4)*scale))),
                            '-y', str(max(0, int((float(page.mediabox.top)-top-4)*scale))),
                            '-W', str(int((right-left+8)*scale)), '-H', str(int((top-bottom+8)*scale)),
                            '-singlefile', '-png', str(path), str(output)], check=True, capture_output=True)
            image = output.with_suffix('.png')
            assert image.stat().st_size > 100
            return str(image)
    raise AssertionError('No active AC widget to render')


def run(binary, source, folder, label, steps):
    spec, evidence = folder / (label + '-scenario.json'), folder / (label + '-probe.json')
    spec.write_text(json.dumps({'dialogs': [{'result': 'ok'}] * 30, 'alerts': [1] * 30,
                                'steps': [{'op': 'advance', 'ms': 4100}] + steps}))
    with (folder / (label + '.log')).open('w') as log:
        proc = subprocess.run([str(binary), str(source), '--probe', str(spec), str(evidence)], stdout=log, stderr=log, timeout=300)
    data = json.loads(evidence.read_text())
    assert proc.returncode == 0 and data['passed'], data.get('error')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-only', action='store_true')
    parser.add_argument('--readiness', type=Path)
    parser.add_argument('--stale-native', type=Path, help='Earlier disposable wolf output with Dex 18 and stale AC 12')
    args = parser.parse_args()
    if not args.native_only:
        assert args.readiness
        ready = json.loads(args.readiness.read_text())
        assert ready['passed'] and len(ready['cases']) == 24
    folder = ROOT / 'output/testing' / ('formatted-companion-ac-' + str(time.time_ns()))
    folder.mkdir()
    binary = folder / 'mpmb-reader'
    shutil.copy2(ROOT / 'target/debug/mpmb-reader', binary)
    source = next((ROOT / 'Testing').glob('*_2024_*.pdf'))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    report = {'passed': False, 'scope': __doc__, 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'readiness': str(args.readiness)}
    print(folder, flush=True)
    try:
        before, after = folder / 'before.pdf', folder / 'after.pdf'
        capture = "({prefix:__acPrefix,canonical:getField(__acPrefix+'Comp.Use.AC').valueAsString,formatted:JSON.parse(__host.snapshot())[__acPrefix+'Comp.Use.AC'].formatted,dex:getField(__acPrefix+'Comp.Use.Ability.Dex.Score').valueAsString})"
        data = run(binary, source, folder, 'create', [
            {'op': 'eval', 'code': "var __acPrefix=DoTemplate('AScomp','Add',null,true);ApplyCompRace('wolf',__acPrefix);" + capture},
            {'op': 'save', 'path': str(before)}])
        first = data['stages'][-2]['result']
        prefix = first['prefix']
        data = run(binary, before, folder, 'change-after-reopen', [
            {'op': 'eval', 'code': 'var __acPrefix=' + json.dumps(prefix) + ";__host.edit(__acPrefix+'Comp.Use.Ability.Dex.Score','18');calculateNow();" + capture},
            {'op': 'save', 'path': str(after)}])
        second = data['stages'][-2]['result']
        assert first['canonical'] == second['canonical'] == '10+Dex'
        assert (first['formatted'], second['formatted']) == (12, 14)
        assert (first['dex'], second['dex']) == ('15', '18')
        report['native'] = {'before': first, 'after': second, 'before_appearance': appearance(before, prefix + 'Comp.Use.AC'), 'after_appearance': appearance(after, prefix + 'Comp.Use.AC')}
        assert report['native']['before_appearance'] == ['12']
        assert report['native']['after_appearance'] == ['14'], 'Calculated display not projected after reopening'
        report['native']['renders'] = [render_ac(path, prefix + 'Comp.Use.AC') for path in [before, after]]
        assert script_hashes(before) == script_hashes(after) == script_hashes(source)
        reopened = folder / 'after-reopened.pdf'
        data = run(binary, after, folder, 'reopen-after', [
            {'op': 'eval', 'code': 'var __acPrefix=' + json.dumps(prefix) + ';' + capture},
            {'op': 'save', 'path': str(reopened)}])
        assert data['stages'][-2]['result'] == second
        assert appearance(reopened, prefix + 'Comp.Use.AC') == ['14']
        report['native']['saved_reopened'] = True
        if args.stale_native:
            stale = args.stale_native.resolve()
            assert stale.is_relative_to(ROOT / 'output/testing')
            assert script_hashes(stale) == script_hashes(source)
            assert appearance(stale, prefix + 'Comp.Use.AC') == ['12']
            corrected = folder / 'corrected-old-output.pdf'
            data = run(binary, stale, folder, 'old-output', [
                {'op': 'eval', 'code': 'var __acPrefix=' + json.dumps(prefix) + ';' + capture},
                {'op': 'save', 'path': str(corrected)}])
            assert data['stages'][-2]['result'] == second
            assert appearance(corrected, prefix + 'Comp.Use.AC') == ['14']
            assert script_hashes(corrected) == script_hashes(source)
            report['corrected_old_native_output'] = str(corrected)

        if not args.native_only:
            with c.desktop_lock():
                assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow' and '.pdf' in e.get('name', '').lower()], 'Pre-existing Reader document'
                path = c.remote_path('runs/formatted-ac-' + str(time.time_ns()) + '.pdf')
                c.powershell('Copy-Item ' + c.literal(c.remote_path('fixtures/blank-2024.pdf')) + ' ' + c.literal(path) + ' -Force;(Get-Item ' + c.literal(path) + ').IsReadOnly=$false')
                report['reader_path'] = path
                value = c.script('call', path=path, name='DoTemplate', args=['AScomp', 'Add', None, True])
                reader_prefix = value['value']
                c.script('call', path=path, name='ApplyCompRace', args=['wolf', reader_prefix])
                saved = path[:-4] + '-before.pdf'
                c.script('save', path=path, output=saved)
                c.script('close', path=saved)
                local_before = c.fetch(saved, folder / 'reader-before.pdf')
                fresh = path[:-4] + '-reopen.pdf'
                c.powershell("$p=" + c.literal(saved) + ";$q=" + c.literal(fresh) + ";$s=[IO.File]::Open($p,'Open','Read','None');$s.Dispose();Copy-Item $p $q -Force;if((Get-FileHash $p).Hash -ne (Get-FileHash $q).Hash){throw 'Snapshot mismatch'}")
                c.script('set', path=fresh, values={reader_prefix + 'Comp.Use.Ability.Dex.Score': '18'})
                output = fresh[:-4] + '-after.pdf'
                c.script('save', path=fresh, output=output)
                c.script('close', path=output)
                local_after = c.fetch(output, folder / 'reader-after.pdf')
                report['reader'] = {'before_appearance': appearance(local_before, reader_prefix + 'Comp.Use.AC'), 'after_appearance': appearance(local_after, reader_prefix + 'Comp.Use.AC')}
                assert report['reader'] == {key: report['native'][key] for key in ['before_appearance', 'after_appearance']}
                report['reader']['renders'] = [render_ac(path, reader_prefix + 'Comp.Use.AC') for path in [local_before, local_after]]
                for path in [local_before, local_after]:
                    assert script_hashes(path) == script_hashes(source)
                    assert canonical_fields(PdfReader(path))[reader_prefix + 'Comp.Use.AC']['/V'] == '10+Dex'
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
        report['passed'] = True if not args.native_only else None
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (folder / 'formatting.json').write_text(json.dumps(report, indent=2) + '\n')
        print(folder / 'formatting.json', flush=True)


if __name__ == '__main__':
    main()
