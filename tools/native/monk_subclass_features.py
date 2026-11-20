"""Bounded logical-state gates for the 2024 Open Hand/Shadow six-state probe.

These assertions do not qualify canonical PDFs, appearances, legal character
construction, desktop input, healing or complete Monk compatibility.
"""
from workflow_state_comparison import encoded_state

LABELS = ['open6', 'open11', 'open17', 'shadow3', 'back-open6', 'cold-open6']


def qualify(report, reference=None):
    assert report.get('passed') is True, 'Execution report failed'
    phases = report['phases']
    assert [p['label'] for p in phases] == LABELS, 'Incomplete or reordered transitions'
    checks = []
    for point, level in zip(phases, [6, 11, 17, 3, 6, 6]):
        state = point['state']
        shadow = point['label'] == 'shadow3'
        subclass = 'monk-shadow-2' if shadow else 'monk-open hand'
        assert state['identity'] == {'level': level, 'subclass': subclass}
        assert state['definition']['key'] == subclass
        assert state['definition']['source'], 'Missing original definition source'
        assert not state['errors'] and not state['unavailable'], 'Original errors/unavailable reads'
        assert state['calculation'] == {'app': True, 'doc': True, 'delay': False}
        assert state['pages'] == 6, 'Unexpected generated-page change'
        choices = state['choices']['classes']['monk']
        notes = '\n'.join(state['notesAndActions'].values()).lower()
        assert ('fleet step' in notes) == (not shadow and level >= 11)
        assert ('quivering palm' in notes) == (not shadow and level >= 17)
        assert ('subclassfeature17' in choices) == (not shadow and level >= 17)
        if level == 17:
            assert choices['subclassfeature17']['extrachoices'] == ['quivering palm']
        if shadow:
            assert choices['subclassfeature3']['extrachoices'] == ['shadow arts: darkness']
            assert list(state['spells']) == ['monk'], 'Shadow spell state missing'
            assert 'shadow arts' in notes and 'wholeness of body' not in notes
        else:
            assert state['spells'] == {}, 'Removed subclass caster retained'
            assert 'wholeness of body' in notes and 'shadow arts' not in notes
        resources = state['resources']
        rows = [name for name, value in resources.items() if value == 'Focus Points']
        assert len(rows) == 1
        index = rows[0].removeprefix('Limited Feature ')
        assert resources['Limited Feature Max Usages ' + index] == str(level)
        wholeness = [value for value in resources.values() if value.startswith('Wholeness of Body (')]
        assert bool(wholeness) == (not shadow), 'Subclass resource removal/readdition differs'
        checks.append({'label': point['label'], 'level': level, 'subclass': subclass})
    assert encoded_state(phases[4]['state']) == encoded_state(phases[5]['state']), 'Cold reopen changed logical state'
    if reference is not None:
        qualify(reference)
        for actual, expected in zip(phases, reference['phases']):
            assert encoded_state(actual['state']) == encoded_state(expected['state']), ('Complete captured state differs', actual['label'])
    return {'passed': True, 'scope': __doc__, 'phases': checks,
            'full_captured_reference_comparison': reference is not None}


if __name__ == '__main__':
    import argparse
    import hashlib
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = {'passed': False, 'scope': __doc__}
    try:
        data = json.loads(args.report.read_text())
        reference = json.loads(args.reference.read_text()) if args.reference else None
        result.update(qualify(data, reference))
        result['report_sha256'] = hashlib.sha256(args.report.read_bytes()).hexdigest()
        if args.reference:
            result['reference_sha256'] = hashlib.sha256(args.reference.read_bytes()).hexdigest()
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        args.output.write_text(json.dumps(result, indent=2) + '\n')
