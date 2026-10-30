#!/usr/bin/env python3
"""Enter Reader-offered spell labels through observed original PopupEdit controls.

Used by qualified Reader workflows; this never assigns CurrentSpells. Selection
is verified by the caller's original-script observer and independent PDF checks.
"""
import time

CANTRIPS = ['eldritch blast', 'mage hand', 'minor illusion']
SPELLS = ['hex', 'armor of agathys', 'misty step', 'counterspell', 'fly', 'hunger of hadar']


def type_selection(c, owner, elements, offered):
    """Locate columns by fresh headings and owned edit relationships, not pixels."""
    headings = {}
    for label in ['Cantrips', 'Spells', 'Bonus Spells']:
        matches = [e for e in elements if e.get('owner') == owner
                   and e.get('class') == 'Static' and e.get('name') == label]
        assert len(matches) == 1, 'Missing or ambiguous spell heading: ' + label
        headings[label] = matches[0]
    assert headings['Cantrips']['rect'][0] < headings['Spells']['rect'][0] < headings['Bonus Spells']['rect'][0]
    evidence = []
    for label, next_label, keys, map_key in [
        ('Cantrips', 'Spells', CANTRIPS, 'cantrips'),
        ('Spells', 'Bonus Spells', SPELLS, 'spells'),
    ]:
        left = headings[label]['rect'][0]
        right = headings[next_label]['rect'][0]
        top = headings[label]['rect'][1] + headings[label]['rect'][3]
        edits = sorted([e for e in elements if e.get('owner') == owner
                        and e.get('class') == 'Edit' and e.get('parent_class') == 'ComboBox'
                        and e.get('enabled') and e.get('read_only') is False
                        and left <= e['rect'][0] < right and e['rect'][1] > top
                        and e['rect'][2] > 0 and e['rect'][3] > 0],
                       key=lambda e: e['rect'][1])
        assert len(edits) >= len(keys), 'Too few observed editable controls: ' + label
        assert len({e['rect'][1] for e in edits}) == len(edits), 'Ambiguous spell rows'
        for control, key in zip(edits, keys):
            exact_label = offered[map_key][key]
            assert isinstance(exact_label, str) and exact_label, 'Spell not offered by Reader: ' + key
            focus = c.command('focus_control', owner=owner, handle=control['handle'])
            assert focus['focused'], 'Requested spell edit did not receive focus'
            pasted = c.command('paste', value=exact_label)
            assert pasted['verified'] and pasted['value'] == exact_label
            # Tab invokes the original manualInputToSpellObj callback. Reject an
            # unexpected nested chooser rather than supplying a generic reply.
            fresh = c.command('inspect')
            dialogs = [e for e in fresh if e.get('class') == '#32770']
            assert len(dialogs) == 1 and dialogs[0]['handle'] == owner, 'Unexpected dialog after spell entry'
            actual = c.command('dialog_control', owner=owner, handle=control['handle'])
            assert actual['text'] == exact_label, 'Original spell edit text differs'
            evidence.append({'key': key, 'label': exact_label, 'control': control,
                             'focus': focus, 'paste': pasted, 'after': actual,
                             'observed_at': time.time()})
    return evidence
