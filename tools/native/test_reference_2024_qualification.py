import copy
import os
import subprocess
import sys
import unittest
from pathlib import Path
from reference_2024_qualification import expected_cases, require_2024_reference, require_fixture_reference


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

    def test_invalid_reports_remain_rejected_under_python_optimize(self):
        tools_native = str(Path(__file__).resolve().parent)
        script = (
            'import sys; '
            f'sys.path.insert(0, {tools_native!r}); '
            'from reference_2024_qualification import require_2024_reference, require_fixture_reference; '
            'from workflow_state_comparison import compare; '
            'bad = {"passed": False, "status": "failed", "fixture_scope": ["2024"], "harness_sha256": "old", "planned_cases": 0, "expected_cases": [], "cases": []}; '
            'caught = 0\n'
            'for fn in (lambda: require_2024_reference(bad, "new"), lambda: require_fixture_reference(bad, "new", "2024"), lambda: compare({"passed": False, "phases": []}, {"passed": True, "phases": []})): \n'
            '    try: fn()\n'
            '    except AssertionError: caught += 1\n'
            'if caught != 3: raise SystemExit(1)\n'
        )
        env = dict(os.environ, PYTHONOPTIMIZE='1')
        proc = subprocess.run([sys.executable, '-O', '-c', script], env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)


if __name__ == '__main__':
    unittest.main()
