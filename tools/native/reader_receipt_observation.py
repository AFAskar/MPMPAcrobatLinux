"""Collect one original Reader request and verify readiness without replay.

Only the exact desktop title-bar focus refusal is retried. All failed
observations remain in the result/error; document functions are never resubmitted.
"""
import json

FOCUS_REFUSAL = 'Another application covers the Acrobat title bar; focus refused'


class ReceiptObservationError(RuntimeError):
    def __init__(self, message, request_id, attempts, receipt):
        super().__init__(message)
        self.request_id = request_id
        self.read_attempts = attempts
        self.receipt = receipt


def focus_refused(error):
    try:
        data = json.loads(str(error))
    except (ValueError, TypeError):
        return False
    return (isinstance(data, dict) and data.get('ok') is False
            and data.get('error') == FOCUS_REFUSAL)


def collect(controller, request_id, path, *, timeout=120, max_attempts=3):
    """Caller owns the desktop lock and has already persisted request_id."""
    if not isinstance(request_id, str) or len(request_id) != 32 or any(
            char not in '0123456789abcdef' for char in request_id):
        raise ValueError('Original request ID required')
    if not 1 <= max_attempts <= 3:
        raise ValueError('One to three observations required')
    receipt = None
    attempts = []
    for index in range(max_attempts):
        observation = {'attempt': index + 1, 'phase': 'result' if receipt is None else 'readiness'}
        try:
            if receipt is None:
                receipt = controller.script_result(request_id, timeout=timeout)
                observation['receipt_received'] = True
            observation['phase'] = 'readiness'
            ready = controller.ensure_document(path)
        except RuntimeError as error:
            observation['error'] = str(error)
            attempts.append(observation)
            if not focus_refused(error) or index + 1 == max_attempts:
                raise ReceiptObservationError(str(error), request_id, attempts, receipt) from error
            continue
        observation['succeeded'] = True
        attempts.append(observation)
        return {'request': request_id, 'completion': receipt, 'ready': ready,
                'read_attempts': attempts}
    raise AssertionError('Unreachable receipt observation')
