"""Unit tests for the pure subclass-audit qualification rules.

Run without the Rust binary, PDF fixtures, Reader or the audit CLI:

    python3 -m unittest discover -s tools/native \\
        -p 'test_subclass_audit_qualification.py' -v

These tests exercise only report/diagnostic qualification.  They do not claim
reader or MPMB workflow coverage.
"""
import copy
import unittest

from subclass_audit_qualification import (
    case_set_complete,
    qualify_probe,
    reopen_qualification,
)


LEVEL_STAGE = {
    'op': 'assert',
    'passed': True,
    'result': {'Character Level': '3', 'Proficiency Bonus': '2'},
}


def probe_data(errors=None, messages=None, **overrides):
    """Build a successful native probe report with the given diagnostic streams."""
    data = {
        'passed': True,
        'error': None,
        'stages': [copy.deepcopy(LEVEL_STAGE)],
        'diagnostics': {
            'errors': [] if errors is None else errors,
            'console': {'visible': False, 'messages': [] if messages is None else messages},
        },
    }
    data.update(overrides)
    return data


def creation_case(data=None):
    """A case qualified from a clean creation probe."""
    probe = qualify_probe(0, probe_data() if data is None else data)
    assert probe['passed']
    return {
        'class': 'fighter',
        'subclass': 'champion',
        'execution_passed': probe['execution_passed'],
        'passed': probe['passed'],
        'diagnostics_checked': probe['diagnostics_checked'],
        'diagnostic_errors': probe['diagnostic_errors'],
        'console_messages': probe['console_messages'],
        'diagnostic_structure_errors': probe['diagnostic_structure_errors'],
        'probe': 'fixture-report.json',
        'feature_choices': 'Default responses only; unqualified',
        'reader': 'not run',
    }


def completed_case():
    """A case with clean creation and reopen qualification."""
    return reopen_qualification(creation_case(), 0, probe_data())


class ProbeQualificationTests(unittest.TestCase):
    def test_clean_successful_probe_passes(self):
        result = qualify_probe(0, probe_data())
        self.assertTrue(result['execution_passed'])
        self.assertTrue(result['diagnostics_checked'])
        self.assertTrue(result['passed'])
        self.assertEqual(result['diagnostic_errors'], [])
        self.assertEqual(result['console_messages'], [])
        self.assertEqual(result['diagnostic_structure_errors'], [])
        self.assertIsNone(result['error'])

    def test_creation_errors_fail_despite_passing_execution_and_level_assertions(self):
        data = probe_data(errors=[{
            'stage': 'field', 'field': 'A', 'event': 'V', 'error': 'original boom',
        }])
        self.assertIs(data['stages'][0]['passed'], True)
        result = qualify_probe(0, data)
        self.assertTrue(result['execution_passed'])
        self.assertTrue(result['diagnostics_checked'])
        self.assertFalse(result['passed'])
        self.assertEqual(result['diagnostic_errors'], data['diagnostics']['errors'])
        self.assertIn('creation probe reported 1 original caught error', result['error'])
        self.assertNotIn('console message', result['error'])

    def test_creation_console_messages_fail_independently(self):
        message = {'document': 'sheet.pdf', 'text': 'warning: keep \u00a0 spacing'}
        data = probe_data(messages=[message])
        self.assertIs(data['stages'][0]['passed'], True)
        result = qualify_probe(0, data)
        self.assertTrue(result['execution_passed'])
        self.assertTrue(result['diagnostics_checked'])
        self.assertFalse(result['passed'])
        self.assertEqual(result['console_messages'], [message])
        self.assertEqual(result['diagnostic_errors'], [])
        self.assertIn('creation probe reported 1 original console message', result['error'])
        self.assertNotIn('caught error', result['error'])

    def test_both_diagnostic_streams_are_reported_and_preserved(self):
        error = {'stage': 'original-alert', 'error': 'bad alert'}
        message = {'document': 'sheet.pdf', 'text': '[warning] unchanged text'}
        result = qualify_probe(0, probe_data(errors=[error], messages=[message]))
        self.assertFalse(result['passed'])
        self.assertEqual(result['diagnostic_errors'], [error])
        self.assertEqual(result['console_messages'], [message])
        self.assertIn('1 original caught error', result['error'])
        self.assertIn('1 original console message', result['error'])

    def test_reopen_errors_fail_despite_passing_execution_and_level_assertions(self):
        case = creation_case()
        error = {'stage': 'timer', 'code': 'original()', 'error': 'reopen boom'}
        reopened = reopen_qualification(case, 0, probe_data(errors=[error]))
        self.assertTrue(reopened['reopen_execution_passed'])
        self.assertTrue(reopened['reopen_diagnostics_checked'])
        self.assertFalse(reopened['passed'])
        self.assertEqual(reopened['reopen_diagnostic_errors'], [error])
        self.assertEqual(reopened['reopen_console_messages'], [])
        self.assertIn('reopen probe reported 1 original caught error', reopened['error'])
        self.assertNotIn('console message', reopened['error'])
        self.assertEqual(reopened['diagnostic_errors'], [])

    def test_reopen_console_messages_fail_independently(self):
        case = creation_case()
        message = {'document': 'sheet.pdf', 'text': 'reopen warning'}
        reopened = reopen_qualification(case, 0, probe_data(messages=[message]))
        self.assertTrue(reopened['reopen_execution_passed'])
        self.assertTrue(reopened['reopen_diagnostics_checked'])
        self.assertFalse(reopened['passed'])
        self.assertEqual(reopened['reopen_console_messages'], [message])
        self.assertEqual(reopened['reopen_diagnostic_errors'], [])
        self.assertIn('reopen probe reported 1 original console message', reopened['error'])
        self.assertNotIn('caught error', reopened['error'])

    def test_clean_reopen_preserves_creation_diagnostics_and_provenance(self):
        case = creation_case()
        reopened = reopen_qualification(case, 0, probe_data())
        self.assertTrue(reopened['passed'])
        self.assertEqual(reopened['diagnostic_errors'], [])
        self.assertEqual(reopened['console_messages'], [])
        self.assertEqual(reopened['reopen_diagnostic_errors'], [])
        self.assertEqual(reopened['reopen_console_messages'], [])
        self.assertEqual(reopened['probe'], 'fixture-report.json')
        self.assertEqual(reopened['feature_choices'], 'Default responses only; unqualified')
        self.assertEqual(reopened['reader'], 'not run')

    def test_reopen_nonzero_returncode_fails_even_with_clean_diagnostics(self):
        reopened = reopen_qualification(creation_case(), 3, probe_data())
        self.assertFalse(reopened['reopen_execution_passed'])
        self.assertTrue(reopened['reopen_diagnostics_checked'])
        self.assertFalse(reopened['passed'])
        self.assertIn('reopen probe exited with status 3', reopened['error'])

    def test_reopen_reported_execution_failure_fails(self):
        data = probe_data(passed=False, error='reopen level assertion failed')
        reopened = reopen_qualification(creation_case(), 0, data)
        self.assertFalse(reopened['reopen_execution_passed'])
        self.assertFalse(reopened['passed'])
        self.assertIn('reopen level assertion failed', reopened['error'])

    def test_malformed_reopen_diagnostics_cannot_pass(self):
        reopened = reopen_qualification(creation_case(), 0, {'passed': True})
        self.assertFalse(reopened['reopen_diagnostics_checked'])
        self.assertFalse(reopened['passed'])
        self.assertTrue(reopened['reopen_diagnostic_structure_errors'])
        self.assertIn('malformed', reopened['error'])

    def test_nonzero_returncode_fails_even_with_clean_diagnostics(self):
        result = qualify_probe(2, probe_data())
        self.assertFalse(result['execution_passed'])
        self.assertTrue(result['diagnostics_checked'])
        self.assertFalse(result['passed'])
        self.assertIn('creation probe exited with status 2', result['error'])

    def test_reported_execution_failure_fails(self):
        data = probe_data(passed=False, error='level assertion failed')
        result = qualify_probe(0, data)
        self.assertFalse(result['execution_passed'])
        self.assertFalse(result['passed'])
        self.assertIn('level assertion failed', result['error'])

    def test_passed_must_be_literal_true(self):
        for passed in (1, 'true', None, [], {}):
            with self.subTest(passed=passed):
                data = probe_data(passed=passed)
                result = qualify_probe(0, data)
                self.assertFalse(result['execution_passed'])
                self.assertFalse(result['passed'])

    def test_malformed_or_missing_diagnostic_structures_cannot_pass(self):
        valid = probe_data()
        cases = [
            ('report is not an object', []),
            ('diagnostics missing', {'passed': True}),
            ('diagnostics not an object', {'passed': True, 'diagnostics': None}),
            ('errors missing', {
                'passed': True,
                'diagnostics': {'console': {'messages': []}},
            }),
            ('errors not a list', {
                'passed': True,
                'diagnostics': {'errors': {}, 'console': {'messages': []}},
            }),
            ('errors entry not an object', {
                'passed': True,
                'diagnostics': {'errors': [None], 'console': {'messages': []}},
            }),
            ('console missing', {
                'passed': True,
                'diagnostics': {'errors': []},
            }),
            ('console not an object', {
                'passed': True,
                'diagnostics': {'errors': [], 'console': []},
            }),
            ('console messages missing', {
                'passed': True,
                'diagnostics': {'errors': [], 'console': {}},
            }),
            ('console messages not a list', {
                'passed': True,
                'diagnostics': {'errors': [], 'console': {'messages': {}}},
            }),
            ('console message not an object', {
                'passed': True,
                'diagnostics': {
                    'errors': [],
                    'console': {'messages': ['plain warning']},
                },
            }),
        ]
        for label, data in cases:
            with self.subTest(label=label):
                if isinstance(data, dict):
                    self.assertIs(data.get('passed'), True)
                result = qualify_probe(0, data)
                self.assertFalse(result['passed'])
                self.assertFalse(result['diagnostics_checked'])
                self.assertTrue(result['diagnostic_structure_errors'])
                self.assertTrue(result['error'])
                if isinstance(data, dict):
                    self.assertIn('malformed', result['error'])
        self.assertTrue(qualify_probe(0, valid)['passed'])


class CaseSetCompletionTests(unittest.TestCase):
    def test_clean_completed_case_set_passes(self):
        fixtures = [{'fixture': '2014', 'cases': [completed_case()]}]
        complete, reason = case_set_complete(fixtures)
        self.assertTrue(complete)
        self.assertIsNone(reason)

    def test_zero_fixtures_fail(self):
        complete, reason = case_set_complete([])
        self.assertFalse(complete)
        self.assertIn('no fixture cases', reason)

    def test_fixture_with_zero_completed_cases_fails(self):
        complete, reason = case_set_complete([{'fixture': '2014', 'cases': []}])
        self.assertFalse(complete)
        self.assertIn('2014 has zero completed cases', reason)

    def test_fixture_without_cases_field_fails(self):
        complete, reason = case_set_complete([{'fixture': '2014'}])
        self.assertFalse(complete)
        self.assertIn('zero completed cases', reason)

    def test_missing_reopen_qualification_fails(self):
        case = completed_case()
        del case['reopen_diagnostics_checked']
        complete, reason = case_set_complete([{'fixture': '2014', 'cases': [case]}])
        self.assertFalse(complete)
        self.assertIn('reopen diagnostics were not checked', reason)

    def test_reopen_errors_keep_case_set_incomplete(self):
        case = completed_case()
        case['reopen_diagnostic_errors'] = [{'stage': 'field', 'error': 'boom'}]
        complete, reason = case_set_complete([{'fixture': '2014', 'cases': [case]}])
        self.assertFalse(complete)
        self.assertIn('reopen errors are not empty', reason)

    def test_creation_console_message_keeps_case_set_incomplete(self):
        case = completed_case()
        case['console_messages'] = [{'document': 'sheet.pdf', 'text': 'warning'}]
        complete, reason = case_set_complete([{'fixture': '2014', 'cases': [case]}])
        self.assertFalse(complete)
        self.assertIn('creation console messages are not empty', reason)

    def test_failed_case_fails(self):
        case = completed_case()
        case['passed'] = False
        complete, reason = case_set_complete([{'fixture': '2014', 'cases': [case]}])
        self.assertFalse(complete)
        self.assertIn('did not pass', reason)

    def test_malformed_case_fails(self):
        complete, reason = case_set_complete([{'fixture': '2014', 'cases': [None]}])
        self.assertFalse(complete)
        self.assertIn('case 0 is malformed', reason)

    def test_malformed_fixture_fails(self):
        complete, reason = case_set_complete([None])
        self.assertFalse(complete)
        self.assertIn('fixture entry is malformed', reason)


if __name__ == '__main__':
    unittest.main()
