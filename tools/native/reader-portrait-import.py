#!/usr/bin/env python3
"""Original2024 portrait PNG import/cancel and changed Reader cold persistence.

Requires a disclosed Bard startup observer and matching2024 reference readiness.
Select the actual active widget: widget zero may belong to an inactive template.
File selection uses observed owned controls, checked paste and live WM_GETTEXT.
This bounded PNG workflow does not qualify every icon format or PDF page choice.
"""
import argparse
import hashlib
import importlib.util
import json
import ntpath
from pathlib import Path
import subprocess
import sys
import time
from PIL import Image
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/acrobat'))
import control as c
import fighter_additional_diagnostics as diagnostics
import reader_document_controls as closing
from reference_2024_qualification import require_2024_reference
from verify import canonical_fields, script_hashes


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT/'tools/native'/file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def portrait(path):
    reader = PdfReader(path)
    field = reader.get_fields()['Portrait']
    active = {ref.idnum for page in reader.pages for ref in page.get('/Annots', [])}
    result = []
    for index, ref in enumerate(field.get('/Kids', [])):
        widget = ref.get_object()
        icon = widget['/MK']['/I'].get_object()
        images = []
        seen = set()

        def walk(obj, depth=0):
            assert depth < 16 and len(seen) < 64, 'Unexpected icon resource graph'
            ident = getattr(obj, 'idnum', None)
            if ident is not None:
                if ident in seen:
                    return
                seen.add(ident)
            obj = obj.get_object()
            if obj.get('/Subtype') == '/Image':
                data = obj.get_data()
                images.append({'width': int(obj['/Width']), 'height': int(obj['/Height']),
                               'color_space': str(obj['/ColorSpace']),
                               'data_sha256': hashlib.sha256(data).hexdigest(),
                               'bytes': len(data), 'has_mask': '/SMask' in obj})
            else:
                assert obj.get('/Subtype') == '/Form'
                for child in obj.get('/Resources', {}).get('/XObject', {}).values():
                    walk(child, depth+1)

        walk(widget['/MK']['/I'])
        result.append({'index': index, 'active': ref.idnum in active,
                       'flags': int(widget.get('/F', 0)), 'images': images,
                       'icon_content_sha256': hashlib.sha256(icon.get_data()).hexdigest(),
                       'appearance_present': bool(widget.get('/AP', {}).get('/N'))})
    assert result and any(w['active'] and not w['flags'] & 34 for w in result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--readiness', type=Path, required=True)
    args = parser.parse_args()
    source = args.input.resolve()
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    before = canonical_fields(PdfReader(source))
    original_media = portrait(source)
    widgets = [w for w in original_media if w['active'] and not w['flags'] & 34]
    assert len(widgets) == 1, 'Select exactly one visible active portrait widget'
    target = 'Portrait.'+str(widgets[0]['index'])
    ready = json.loads(args.readiness.read_text())
    qualified = require_2024_reference(ready, c.harness_fingerprint())
    folder = ROOT/'output/testing'/('reader-portrait-import-'+str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    image = folder/'blue-yellow.png'
    pixels = bytes([0, 0, 255, 255, 255, 0])
    Image.frombytes('RGB', (2, 1), pixels).save(image)
    base = c.remote_path('runs/portrait-import-'+str(time.time_ns()))
    remote = base+'.pdf'
    image_path = ntpath.normpath(base+'-blue-yellow.png')
    opened = False
    report = {'passed': False, 'scope': __doc__, 'input': str(source),
              'input_sha256': source_hash, 'reference': qualified, 'target': target,
              'source_media': original_media, 'phases': [], 'actions': [],
              'console_checks': [], 'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    menus = module('portrait_menus', 'warlock-reader-invocations.py')
    console = module('portrait_console', 'reader-console.py')
    style = module('portrait_style', 'default-style-persistence.py')

    def persist():
        (folder/'progress.json').write_text(json.dumps(report, indent=2)+'\n')

    def dialog(title):
        end = time.monotonic()+20
        while True:
            rows = c.command('inspect')
            roots = [r for r in rows if r['class'] == '#32770' and r['name'] == title]
            if roots:
                assert len(roots) == 1
                return roots[0]['handle'], rows
            assert time.monotonic() < end, ('Dialog absent', title, rows)

    def invoke(owner, rows, name):
        buttons = [r for r in rows if r['owner'] == owner and r['class'] == 'Button'
                   and r['name'] == name and r['enabled'] and r['rect'][2] > 0 and r['rect'][3] > 0]
        assert len(buttons) == 1, (name, rows)
        # inspect strips mnemonic ampersands; the existing named-control adapter
        # uses that same observed name. Do not invent a raw caption for the
        # physical-button guard, which requires a different representation.
        action = {'button': buttons[0], 'reply': c.command('invoke', owner=owner, name=name)}
        report['actions'].append(action)
        persist()
        return action

    def menu():
        focus = c.script('focus', path=remote, field=target)
        key = c.command('keys', keys=' ')
        label = 'Set any image/pdf file as Portrait'
        popup = menus.popup(label, folder)
        matches = [(i, row) for i, row in enumerate(popup['children'])
                   if row['name'].split('\t')[0].strip() == label]
        assert len(matches) == 1
        index, row = matches[0]
        action = {'focus': focus, 'target': target, 'key': key, 'popup': popup,
                  'selected': row, 'reply': c.command('activate_menu', owner=popup['native_window_handle'],
                                                    position=index, name=row['name'])}
        report['actions'].append(action)
        persist()

    def capture(label, player):
        nonlocal remote
        timer = diagnostics.reader_request(c, remote)
        summary = c.script('field_summary', path=remote, fields=['PC Name'])['fields']['PC Name']
        saved = base+'-'+label+'-diagnostic.pdf'
        c.script('save', path=remote, output=saved)
        remote = saved
        observed = style.saved_capture(c.fetch(remote, folder/(label+'-diagnostic.pdf')), summary, source)
        assert not observed['errors']
        c.script('set', path=remote, values={'User Script': '// MPMB workflow console request'})
        owner, rows = dialog('JavaScript Debugger')
        edits = [r for r in rows if r['owner'] == owner and r['class'] == 'RICHEDIT50W']
        assert len(edits) == 1
        seen = console.read_console_text(owner, edits[0]['handle'])
        report['console_checks'].append(seen)
        seen['close'] = console.close_console(seen)
        assert seen['live']['text'].rstrip('\r\n') == 'MPMB 2024 Bard resource workflow console sentinel'
        c.script('set', path=remote, values={'PC Name': before['PC Name']['/V'],
                                           'User Script': before['User Script']['/V']})
        saved = base+'-'+label+'.pdf'
        c.script('save', path=remote, output=saved)
        remote = saved
        pdf = c.fetch(remote, folder/(label+'.pdf'))
        assert script_hashes(pdf) == script_hashes(source)
        values = canonical_fields(PdfReader(pdf))
        expected = json.loads(json.dumps(before))
        if player is not None:
            for name in ['Player Name', 'AdvLog.Player Name']:
                expected[name]['/V'] = player
        diffs = [n for n in sorted(set(expected) | set(values)) if expected.get(n) != values.get(n)]
        assert not diffs, ('Canonical field changes', diffs)
        media = portrait(pdf)
        for widget in media:
            assert widget['appearance_present']
            assert widget['images'] == [{'width': 2, 'height': 1, 'color_space': '/DeviceRGB',
                                         'data_sha256': hashlib.sha256(pixels).hexdigest(),
                                         'bytes': 6, 'has_mask': False}], widget
        phase = {'label': label, 'pdf': str(pdf), 'timer': timer, 'observer': observed,
                 'media': media, 'canonical_difference_names': diffs}
        report['phases'].append(phase)
        persist()
        return phase

    try:
        with c.desktop_lock():
            assert not [r for r in c.command('inspect') if r['class'] == 'AcrobatSDIWindow'
                        and '.pdf' in r['name'].lower()], 'Pre-existing Reader document'
            for local, destination in [(source, remote), (image, image_path)]:
                subprocess.run(c.SCP+[str(local), c.SCP_TARGET + ':MPMB-Testing/runs/'+
                                      destination.replace('\\', '/').split('/')[-1]],
                               check=True, capture_output=True)
            uploaded = c.powershell('(Get-FileHash -Algorithm SHA256 '+c.literal(image_path)+').Hash').lower()
            assert uploaded == hashlib.sha256(image.read_bytes()).hexdigest()
            report['uploaded_media'] = {'path': image_path, 'sha256': uploaded}
            opened = True
            c.ensure_document(remote)
            menu()
            owner, rows = dialog('Select Image')
            invoke(owner, rows, 'Browse...')
            owner, rows = dialog('Open')
            edits = [r for r in rows if r['owner'] == owner and r['class'] == 'Edit'
                     and r['enabled'] and r['read_only'] is False and r['rect'][2] > 0]
            assert len(edits) == 1
            edit = edits[0]
            typed = {'focus': c.command('focus_control', owner=owner, handle=edit['handle']),
                     'select_all': c.command('keys', keys='^a'),
                     'paste': c.command('paste', value=image_path),
                     'readback': c.command('dialog_control', owner=owner, handle=edit['handle'])}
            assert typed['readback']['text'] == image_path
            report['file_input'] = typed
            invoke(owner, rows, 'Open')
            c.ensure_document(remote)
            imported = capture('imported', None)
            assert imported['media'] != original_media
            shot = c.command('screenshot')
            c.fetch(shot['path'], folder/'reader-imported.png')
            menu()
            owner, rows = dialog('Select Image')
            invoke(owner, rows, 'Cancel')
            c.ensure_document(remote)
            cancelled = capture('cancelled', None)
            assert cancelled['media'] == imported['media']
            report['first_close'] = closing.close_saved(c, remote)
            opened = False
            remote, report['snapshot'] = closing.reopen_snapshot(c, remote)
            opened = True
            c.ensure_document(remote)
            player = 'Portrait import changed cold Reader'
            c.script('set', path=remote, values={'Player Name': player})
            capture('cold-changed', player)
            report['final_close'] = closing.close_saved(c, remote)
            opened = False
            assert report['first_close']['process_terminated'] and report['final_close']['process_terminated']
            assert [p['timer']['invocation_count'] for p in report['phases']] == [1, 2, 1]
            assert c.harness_fingerprint() == ready['harness_sha256']
            assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
            report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        if opened:
            try:
                with c.desktop_lock():
                    for _ in range(8):
                        rows = c.command('inspect')
                        roots = [r for r in rows if r['class'] == '#32770']
                        if not roots:
                            break
                        selected = next((r for r in roots if r['name'] in ['Open', 'Select Image']), None)
                        if selected:
                            invoke(selected['handle'], rows, 'Cancel')
                        elif len(roots) == 1 and roots[0]['name'] == 'JavaScript Debugger':
                            owner = roots[0]['handle']
                            edit = next(r['handle'] for r in rows if r['owner'] == owner and r['class'] == 'RICHEDIT50W')
                            seen = console.read_console_text(owner, edit)
                            report['cleanup_console'] = seen
                            seen['close'] = console.close_console(seen)
                        else:
                            raise RuntimeError('Unknown blocking dialog; retained for inspection')
                    if any(r['class'] == '#32768' for r in c.command('inspect')):
                        c.command('keys', keys='{ESC}')
                    saved = base+'-failed-retained.pdf'
                    c.script('save', path=remote, output=saved)
                    report['cleanup_close'] = closing.close_saved(c, saved)
                    c.fetch(saved, folder/'failed-retained.pdf')
            except Exception as error:
                report['cleanup_error'] = str(error)
        (folder/'portrait.json').write_text(json.dumps(report, indent=2)+'\n')
        print(folder/'portrait.json', flush=True)


if __name__ == '__main__':
    main()
