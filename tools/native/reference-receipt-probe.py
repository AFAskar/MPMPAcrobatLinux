#!/usr/bin/env python3
"""Reference-control diagnostic: oversized receipt acknowledgement and field focus.

This qualifies transport behavior only, not a complete MPMB reference environment.
The full preflight/readiness contract still applies before compatibility claims.
"""
import argparse, hashlib, json, subprocess, sys, time
from pathlib import Path
from pypdf import PdfReader
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
from verify import canonical_fields, script_hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Disposable real Reader-generated spell output')
    parser.add_argument('--preflight', type=Path, required=True)
    parser.add_argument('--exercise-rich-events', action='store_true', help='Stress rendering/calculation before checking small and oversized result receipts')
    args = parser.parse_args(); assert json.loads(args.preflight.read_text())['passed']
    assert args.source.resolve().is_relative_to(ROOT / 'output/testing')
    original = next((ROOT / 'Testing').glob('*_2014_*.pdf'))
    assert script_hashes(args.source) == script_hashes(original)
    fields = canonical_fields(PdfReader(args.source))
    prefix = [p for p in str(fields['Template.extras.SSfront']['/V']).split(',') if p][-1]
    names = [prefix + 'spells.remember.' + str(i) for i in range(128)]
    expected = {n: str(fields[n]['/V']) if n in fields else None for n in names}
    folder = ROOT / 'output/testing' / ('reference-receipt-' + str(time.time_ns())); folder.mkdir()
    report = {'passed': False, 'scope': __doc__, 'preflight': str(args.preflight.resolve()), 'source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest()}
    print(folder, flush=True)
    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow' and '.pdf' in e.get('name', '').lower()], 'No pre-existing reference document is allowed'
            remote = 'runs/receipt-control-' + str(time.time_ns()) + '.pdf'; path = c.remote_path(remote)
            subprocess.run(c.SCP + [str(args.source.resolve()), 'mpmb-test@127.0.0.1:MPMB-Testing/' + remote], check=True, capture_output=True)
            c.ensure_document(path)
            if args.exercise_rich_events:
                stress = "var iFileName='Receipt rendering stress.js';(function(d){var f=d.getField('Player Name'),value=f.valueAsString,rich=f.richText;try{for(var i=0;i<24;i++){f.richText=i%2===0;f.value='Receipt rendering cycle '+i;d.calculateNow();}}finally{f.richText=rich;f.value=value;}})(tDoc);"
                c.script('set', path=path, values={'User Script': stress})
                stress_request = c.script_submit('call', path=path, name='RunUserScript', args=[False])
                report['rendering_stress_request'] = stress_request
                completed = c.script_result(stress_request, timeout=180)
                assert completed.get('value') is True, completed
                report['rendering_stress_completed'] = True
            ident = c.script_submit('read', path=path, fields=names)
            deadline = time.monotonic() + 30; elements = []; receipts = []
            while time.monotonic() < deadline:
                elements = c.command('inspect')
                receipts = [e for e in elements if e.get('name', '').startswith('MPMB_RESULT') and json.loads(e['name'][11:].strip())['id'] == ident]
                if receipts:
                    break
                time.sleep(.1)
            assert receipts, 'Expected the exact submitted result receipt'
            owner = receipts[0]['owner']; dialog = next(e for e in elements if e['handle'] == owner)
            buttons = [e for e in elements if e.get('owner') == owner and e.get('class') == 'Button' and e.get('name') == 'OK']; assert len(buttons) == 1
            x, y, w, h = buttons[0]['rect']; center = [x + w / 2, y + h / 2]; dx, dy, dw, dh = dialog['rect']
            clipped = not (dx <= center[0] < dx + dw and dy <= center[1] < dy + dh)
            report['receipt_geometry'] = {'dialog': dialog['rect'], 'button': buttons[0]['rect'], 'center_outside_dialog': clipped}
            # Require this regression to reach the known off-dialog button case.
            assert clipped, 'This run did not exercise the oversized receipt fallback'
            result = c.script_result(ident)
            assert result['fields'] == expected, 'Receipt field data differs from independently decoded input'
            assert not any(e.get('name', '').startswith('MPMB_RESULT') for e in c.command('inspect'))
            report['large_receipt_acknowledged'] = True
            value = 'Receipt focus validation'
            c.script('focus', path=path, field='PC Name'); c.command('paste', value=value)
            assert c.script('read', path=path, fields=['PC Name'])['fields']['PC Name'] == value
            report['keyboard_focus_restored'] = True
            saved = path[:-4] + '-saved.pdf'; c.script('save', path=path, output=saved); c.script('close', path=saved)
            local = c.fetch(saved, folder / 'reader-saved.pdf')
            assert canonical_fields(PdfReader(local))['PC Name']['/V'] == value
            assert script_hashes(local) == script_hashes(original)
            report['reader_saved'] = str(local); report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        try:
            shot = c.command('screenshot'); report['screenshot'] = str(c.fetch(shot['path'], folder / 'failure.png'))
        except Exception as capture_error:
            report['capture_error'] = str(capture_error)
        raise
    finally:
        (folder / 'receipt-control.json').write_text(json.dumps(report, indent=2) + '\n'); print(folder / 'receipt-control.json', flush=True)


if __name__ == '__main__':
    main()
