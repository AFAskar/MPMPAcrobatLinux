#!/usr/bin/env python3
"""Open a native generated Bard sheet in Reader and edit its casting ability.

Checks the complete selected spell fields before and after the original ability
actions, preserves the original scripts and independently checks the saved PDF.
Does not assume automatic spell-description regeneration.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/acrobat'))
import control as c
from verify import inspect, script_hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--readiness', type=Path, required=True)
    args = parser.parse_args()
    native = json.loads(args.native.read_text())
    ready = json.loads(args.readiness.read_text())
    assert native['passed'] and ready['passed'] and len(ready['cases']) == 24
    assert ready['harness_sha256'] == c.harness_fingerprint()
    phase = next(p for p in native['phases'] if p['state']['phase'] == 'regenerated')
    source = Path(phase['pdf']).resolve()
    state = phase['state']
    names = list(state['fields'])
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    folder = ROOT / 'output/testing' / ('reader-bard-spell-reopen-' + str(time.time_ns()))
    folder.mkdir()
    print(folder, flush=True)
    remote = c.remote_path('runs/bard-spell-reopen-' + str(time.time_ns()) + '.pdf')
    report = {'passed': False, 'scope': __doc__, 'native': str(args.native),
              'input': str(source), 'source_sha256': source_hash, 'readiness': str(args.readiness)}
    opened = False
    try:
        with c.desktop_lock():
            assert not [e for e in c.command('inspect') if e.get('class') == 'AcrobatSDIWindow'
                        and '.pdf' in e.get('name', '').lower()], 'Pre-existing Reader document'
            subprocess.run(c.SCP + [str(source), 'mpmb-test@127.0.0.1:MPMB-Testing/runs/' +
                                    remote.replace('\\', '/').split('/')[-1]], check=True, capture_output=True)
            opened = True
            c.ensure_document(remote)
            report['loaded'] = c.script('read', path=remote, fields=names)['fields']
            assert report['loaded'] == state['fields'], 'Native generated fields changed on Reader reopen'
            c.script('set', path=remote, values={'Cha': '12'})
            report['edited'] = c.script('read', path=remote, fields=names)['fields']
            prefix = state['prefix']
            assert report['edited'][prefix + 'spellshead.attack.0'] == '+4'
            assert report['edited'][prefix + 'spellshead.dc.0'] == 'DC 12'
            for row in state['rows']:
                assert report['edited'][row['remember']] == state['fields'][row['remember']]
            saved = remote[:-4] + '-edited.pdf'
            c.script('save', path=remote, output=saved)
            remote = saved
            report['close'] = c.script('close', path=remote)
            opened = False
            local = c.fetch(remote, folder / 'reader.pdf')
            report['pdf'] = str(local)
            checked = inspect(local, report['edited'])
            assert checked['actual'] == report['edited'] and checked['widgets']
            assert all(w['matches'] for w in checked['widgets'])
            assert script_hashes(local) == script_hashes(source)
            assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
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
                    retained = remote[:-4] + '-failed-retained.pdf'
                    c.script('save', path=remote, output=retained)
                    report['cleanup_close'] = c.script('close', path=retained)
                    c.fetch(retained, folder / 'failed-retained.pdf')
            except Exception as error:
                report['cleanup_error'] = str(error)
        target = folder / 'reopen.json'
        target.write_text(json.dumps(report, indent=2) + '\n')
        print(target, flush=True)


if __name__ == '__main__':
    main()
