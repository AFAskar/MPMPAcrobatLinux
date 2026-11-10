import copy
import unittest
from reference_2024_qualification import expected_cases, require_2024_reference


class ReferenceQualificationTests(unittest.TestCase):
    def report(self, scope):
        names = expected_cases(scope)
        return {'passed': True, 'status': 'complete', 'harness_sha256': 'current',
                'fixture_scope': scope, 'planned_cases': len(names), 'expected_cases': names,
                'cases': [{'name': name, 'passed': True} for name in names]}

    def test_scoped_2024_is_twelve_cases_and_never_full_readiness(self):
        result = require_2024_reference(self.report(['2024']), 'current')
        self.assertEqual(result['cases'], 12)
        self.assertFalse(result['full_three_fixture_readiness'])

    def test_original_full_suite_remains_twenty_four(self):
        report = self.report(['2014', '2024', 'ashnar'])
        del report['fixture_scope']
        del report['expected_cases']
        result = require_2024_reference(report, 'current')
        self.assertEqual(result['cases'], 24)
        self.assertTrue(result['full_three_fixture_readiness'])

    def test_invalid_completion_scope_and_plan_are_rejected(self):
        good = self.report(['2024'])
        alterations = [
            {'passed': False}, {'passed': 1}, {'status': 'running'},
            {'harness_sha256': 'old'}, {'planned_cases': 24},
            {'fixture_scope': ['2014']}, {'fixture_scope': ['2024', '2024']},
            {'fixture_scope': ['2024'], 'expected_cases': []},
            {'cases': good['cases'][:-1]},
            {'cases': [good['cases'][0]] + good['cases'][0:-1]},
            {'cases': list(reversed(good['cases']))},
            {'cases': []},
        ]
        for change in alterations:
            with self.subTest(change=change), self.assertRaises(AssertionError):
                require_2024_reference(dict(good, **change), 'current')
        for index in range(12):
            bad = copy.deepcopy(good)
            bad['cases'][index]['passed'] = False
            with self.subTest(failed_case=index), self.assertRaises(AssertionError):
                require_2024_reference(bad, 'current')


if __name__ == '__main__':
    unittest.main()
