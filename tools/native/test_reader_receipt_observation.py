import json
import unittest
from reader_receipt_observation import collect, ReceiptObservationError, FOCUS_REFUSAL

REQUEST = 'a' * 32
ERROR = RuntimeError(json.dumps({'ok': False, 'error': FOCUS_REFUSAL}))


class Controller:
    def __init__(self, results, readiness):
        self.results = iter(results)
        self.readiness = iter(readiness)
        self.calls = []

    def script_result(self, request_id, timeout):
        self.calls.append(('result', request_id, timeout))
        value = next(self.results)
        if isinstance(value, Exception):
            raise value
        return value

    def ensure_document(self, path):
        self.calls.append(('ready', path))
        value = next(self.readiness)
        if isinstance(value, Exception):
            raise value
        return value


class ReceiptTests(unittest.TestCase):
    def test_same_original_receipt_after_acknowledgement_refusal(self):
        c = Controller([ERROR, {'value': True}], [{'doc': True}])
        r = collect(c, REQUEST, 'runs/test.pdf')
        self.assertEqual(r['completion'], {'value': True})
        self.assertEqual(len(r['read_attempts']), 2)
        self.assertIn(FOCUS_REFUSAL, r['read_attempts'][0]['error'])
        self.assertEqual([call[0] for call in c.calls], ['result', 'result', 'ready'])
        self.assertTrue(all(call[1] == REQUEST for call in c.calls if call[0] == 'result'))

    def test_readiness_retry_retains_receipt_without_recollection(self):
        c = Controller([{'value': True}], [ERROR, {'doc': True}])
        r = collect(c, REQUEST, 'runs/test.pdf')
        self.assertEqual([call[0] for call in c.calls], ['result', 'ready', 'ready'])
        self.assertEqual(r['read_attempts'][0]['phase'], 'readiness')

    def test_exhausted_observation_retains_all_failures(self):
        c = Controller([ERROR] * 3, [])
        with self.assertRaises(ReceiptObservationError) as failure:
            collect(c, REQUEST, 'runs/test.pdf')
        self.assertEqual(len(failure.exception.read_attempts), 3)
        self.assertEqual(failure.exception.request_id, REQUEST)
        self.assertIsNone(failure.exception.receipt)

    def test_unrelated_script_error_and_disabled_calculation_are_not_retried(self):
        c = Controller([RuntimeError('Original class error')], [])
        with self.assertRaises(ReceiptObservationError):
            collect(c, REQUEST, 'runs/test.pdf')
        self.assertEqual(len(c.calls), 1)
        c = Controller([{'value': True}], [RuntimeError('Calculations not ready')])
        with self.assertRaises(ReceiptObservationError) as failure:
            collect(c, REQUEST, 'runs/test.pdf')
        self.assertEqual(len(c.calls), 2)
        self.assertEqual(failure.exception.receipt, {'value': True})

    def test_focus_phrase_inside_document_error_is_not_desktop_refusal(self):
        c = Controller([RuntimeError(json.dumps({'ok': True, 'error': FOCUS_REFUSAL}))], [])
        with self.assertRaises(ReceiptObservationError):
            collect(c, REQUEST, 'runs/test.pdf')
        self.assertEqual(len(c.calls), 1)


if __name__ == '__main__':
    unittest.main()
