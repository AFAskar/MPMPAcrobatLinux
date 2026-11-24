#!/usr/bin/env python3
"""Generate first-level Druid spell lists through the original MPMB dialogs."""
import json
import time
from pathlib import Path
from pypdf import PdfReader
import control as c
from verify import canonical_fields, inspect, script_hashes


def wait_dialog(title, deadline):
    while time.monotonic() < deadline:
        elements = c.command('inspect')
        roots = [e for e in elements if e['name'] == title]
        if roots:
            return roots[0], elements
        time.sleep(0.1)
    raise RuntimeError('Expected dialog did not appear: ' + title)


def test(rule, run_id, on_active=None):
    mark = on_active or (lambda _path: None)
    source = c.remote_path('runs/druid-' + rule + '-' + run_id + '-saved.pdf')
    path = c.remote_path('runs/spells-' + rule + '-' + run_id + '.pdf')
    c.powershell('Copy-Item ' + c.literal(source) + ' ' + c.literal(path) + ' -Force;(Get-Item ' + c.literal(path) + ').IsReadOnly=$false')
    mark(path)
    c.ensure_document(path)
    ident = c.script_submit('call', path=path, name='GenerateSpellSheet', args=[])
    return finish(rule, run_id, path, ident, mark)


def finish(rule, run_id, path, ident, mark=lambda _path: None):
    deadline = time.monotonic() + 90
    root, elements = wait_dialog('SPELL SELECTION DIALOG', deadline)
    choices = [e for e in elements if e.get('owner') == root['handle'] and e['class'] == 'Button' and e['name'].startswith('1st') and 'Bonus' in e['name']]
    if len(choices) != 1:
        raise RuntimeError('Expected first-level spell-list option: ' + json.dumps(elements))
    c.command('invoke', name=choices[0]['name'], owner=root['handle'])
    c.command('invoke', name='Continue to Next Dialog >>', owner=root['handle'])
    root, elements = wait_dialog('SPELL LIST GENERATION DIALOG', deadline)
    c.command('invoke', name='Generate the Spell Sheet', owner=root['handle'])
    generated = c.script_result(ident, timeout=55)
    assert generated.get('value') is True, generated
    return verify_generated(rule, run_id, path, generated, choices[0]['name'], mark)


def verify_generated(rule, run_id, path, generated, dialog_option, mark=lambda _path: None):
    prefixes = c.script('read', path=path, fields=['Template.extras.SSfront'])['fields']['Template.extras.SSfront']
    prefix = [p for p in prefixes.split(',') if p][-1]
    remembered = c.script('read', path=path, fields=[prefix + 'spells.remember.' + str(i) for i in range(64)])['fields']
    cure = {name: value for name, value in remembered.items() if value and value.startswith('cure wounds##')}
    assert cure, 'Generated Druid list does not contain Cure Wounds'
    expected = {'PC Name': 'MPMB Druid ' + rule, 'Character Level': '2', prefix + 'spellshead.dc.0': 'DC 13', prefix + 'spellshead.attack.0': '+5'}
    actual = c.script('read', path=path, fields=list(expected))
    assert actual['fields'] == expected, actual
    saved = path[:-4] + '-saved.pdf'
    c.script('save', path=path, output=saved)
    mark(saved)
    c.script('close', path=saved)
    mark(None)
    reopened = path[:-4] + '-reopened.pdf'
    c.powershell('Copy-Item ' + c.literal(saved) + ' ' + c.literal(reopened) + ' -Force;if((Get-FileHash ' + c.literal(saved) + ').Hash -ne (Get-FileHash ' + c.literal(reopened) + ").Hash){throw 'Reopen snapshot differs'}")
    mark(reopened)
    again = c.script('read', path=reopened, fields=list(expected))
    assert again['fields'] == expected, again
    local = c.fetch(saved, c.STATE / ('spells-' + rule + '-' + run_id + '.pdf'))
    verified = inspect(local, expected)
    assert verified['passed'], verified
    fields = canonical_fields(PdfReader(local))
    for name, value in cure.items():
        assert fields[name]['/V'] == value, 'Saved spell entry changed'
    original = next((c.REPO / 'Testing').glob('*_' + rule + '_*.pdf'))
    assert script_hashes(original) == script_hashes(local), 'Document scripts changed'
    c.script('close', path=reopened)
    mark(None)
    return dict(dialog_option=dialog_option, generated=generated, reader=again, remembered=cure, pdf=verified)


if __name__ == '__main__':
    import sys
    with c.desktop_lock():
        result = test(sys.argv[1], sys.argv[2])
        (c.STATE / ('spells-' + sys.argv[1] + '-' + sys.argv[2] + '.json')).write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
