"""Host readiness controls; real Reader evidence is qualified separately."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('mpmb_control', Path(__file__).parents[1]/'acrobat/control.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def state(count=1, calculate=True):
    return {'functions': {'InitializeEverything': 'function', 'CalcMod': 'function'},
            'calculation': {'app': calculate, 'doc': True, 'delay': False},
            'startup': {'invocations': count}}


class StartupReadiness(unittest.TestCase):
    def run_states(self, states):
        with patch.object(c, 'command'), patch.object(c, 'raw_script', side_effect=states) as script, \
                patch.object(c.time, 'sleep'):
            result = c.ensure_document('runs/disposable.pdf')
        return result, script.call_count

    def test_calculation_alone_does_not_qualify_pending_callback(self):
        result, calls = self.run_states([state(0), state(0), state(1)])
        self.assertEqual(calls, 3)
        self.assertEqual(result['startup']['invocations'], 1)

    def test_callback_alone_does_not_override_disabled_calculation(self):
        _, calls = self.run_states([state(1, False), state(1)])
        self.assertEqual(calls, 2)

    def test_missing_callback_reaches_deadline(self):
        with patch.object(c, 'command'), patch.object(c, 'raw_script', return_value=state(0)), \
                patch.object(c.time, 'monotonic', side_effect=[0, 36]):
            with self.assertRaisesRegex(RuntimeError, 'not ready'):
                c.ensure_document('runs/disposable.pdf')

    def test_unexpected_duplicate_count_is_rejected(self):
        _, calls = self.run_states([state(2), state(1)])
        self.assertEqual(calls, 2)


if __name__ == '__main__':
    unittest.main()
