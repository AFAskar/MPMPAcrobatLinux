"""Accept complete, fingerprint-matched reference coverage for the 2024 fixture.

A scoped 12-case report qualifies only 2024. It is never a full 24-case pass.
The explicit sequence rejects duplicate, missing and substituted case names.
"""


def expected_cases(scope):
    result = ['desktop-session', 'reader-bridge', 'reject-outside-workspace']
    for fixture in scope:
        name = 'ashnar' if fixture == 'ashnar' else 'blank-' + fixture
        result.append(name + '-read')
        if fixture == 'ashnar':
            result.extend(['ashnar-class-dialog-cancel', 'ashnar-regenerate-spells'])
        else:
            result.extend(name + '-' + suffix for suffix in [
                'keyboard-and-calculation', 'multiclass', 'manual-addon', 'companion-page'])
        result.append(name + '-roundtrip')
    for suffix in ['wildshape-roundtrip', 'spell-generation-roundtrip']:
        result.extend('druid-' + fixture + '-' + suffix for fixture in scope if fixture != 'ashnar')
    result.append('no-new-reader-crash-or-resource-exhaustion')
    return result


def require_2024_reference(report, fingerprint):
    scope = report.get('fixture_scope', ['2014', '2024', 'ashnar'])
    assert scope in [['2024'], ['2014', '2024', 'ashnar']], 'Unqualified reference fixture scope'
    expected = expected_cases(scope)
    assert report.get('passed') is True and report.get('status') == 'complete', 'Reference suite did not complete successfully'
    assert report.get('harness_sha256') == fingerprint, 'Reference harness fingerprint changed'
    assert report.get('planned_cases') == len(expected), 'Reference planned case count differs'
    cases = report.get('cases', [])
    assert [case.get('name') for case in cases] == expected, 'Reference case sequence differs'
    assert all(case.get('passed') is True for case in cases), 'Reference contains a failed case'
    if 'fixture_scope' in report:
        assert report.get('expected_cases') == expected, 'Scoped reference plan differs'
    return {'fixture_scope': list(scope), 'cases': len(expected), 'qualifies_2024_reference_environment': True,
            'full_three_fixture_readiness': scope == ['2014', '2024', 'ashnar']}
