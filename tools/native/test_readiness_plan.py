"""The producer's case plan must survive mutable workflow field expectations."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'acrobat'))
import readiness
from reference_2024_qualification import expected_cases


class ReadinessPlanTests(unittest.TestCase):
    def test_actual_producer_plans_match_independent_consumer(self):
        for scope in [['2024'], ['2014', '2024', 'ashnar']]:
            with self.subTest(scope=scope):
                plan = readiness.case_plan(scope)
                self.assertEqual(plan, expected_cases(scope))
                self.assertEqual(len(plan), 12 if scope == ['2024'] else 24)

    def test_completion_requires_exact_sequence_and_explicit_success(self):
        plan = readiness.case_plan(['2024'])
        cases = [{'name': name, 'passed': True} for name in plan]
        self.assertTrue(readiness.cases_complete(cases, plan))
        self.assertFalse(readiness.cases_complete(cases[:-1], plan))
        self.assertFalse(readiness.cases_complete(cases[::-1], plan))
        self.assertFalse(readiness.cases_complete(cases + cases[:1], plan))
        for value in [False, 1, None]:
            failed = [dict(case) for case in cases]
            failed[7]['passed'] = value
            self.assertFalse(readiness.cases_complete(failed, plan))

    def test_workflow_field_mapping_cannot_be_a_case_plan(self):
        fields = {'PC Name': 'Test', 'Str': '18'}
        cases = [{'name': name, 'passed': True} for name in fields]
        self.assertFalse(readiness.cases_complete(cases, fields))


if __name__ == '__main__':
    unittest.main()
