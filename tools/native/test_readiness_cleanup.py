"""Readiness failure must retain and close its disposable document before releasing desktop_lock."""
import contextlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'acrobat'))
import control as c
import readiness


class ReadinessCleanupTests(unittest.TestCase):
    def _run_failed_first_read(self, *, save_error=None, open_windows=None):
        events = []
        lock_held = {'value': False}

        @contextlib.contextmanager
        def fake_lock():
            lock_held['value'] = True
            events.append(('lock_enter',))
            try:
                yield
            finally:
                events.append(('lock_exit',))
                lock_held['value'] = False

        inspect_calls = {'n': 0}

        def fake_command(action, **kwargs):
            self.assertTrue(lock_held['value'], f'{action} called outside desktop_lock')
            events.append(('command', action, kwargs))
            if action == 'inspect':
                inspect_calls['n'] += 1
                if inspect_calls['n'] == 1:
                    return []
                return open_windows if open_windows is not None else [
                    {'class': 'AcrobatSDIWindow', 'name': 'blank-2024-readiness.pdf - Adobe Acrobat Reader'}
                ]
            if action == 'health':
                return {'ok': True}
            if action == 'open' and kwargs.get('path') == r'C:\Windows\win.ini':
                raise RuntimeError('Path outside testing workspace')
            if action == 'close_document':
                return {'closed': True, 'process_terminated': True}
            raise AssertionError(f'Unexpected command {action} {kwargs}')

        def fake_script(op, **kwargs):
            self.assertTrue(lock_held['value'], f'script({op}) called outside desktop_lock')
            events.append(('script', op, kwargs))
            if op == 'ping':
                return {'session': 'test'}
            if op == 'read':
                raise RuntimeError('Injected first-read failure after opening document')
            raise AssertionError(f'Unexpected script {op} {kwargs}')

        def fake_raw_script(op, **kwargs):
            self.assertTrue(lock_held['value'], f'raw_script({op}) called outside desktop_lock')
            events.append(('raw_script', op, kwargs))
            if op == 'save':
                if save_error is not None:
                    raise RuntimeError(save_error)
                return {'saved': kwargs['output']}
            raise AssertionError(f'Unexpected raw_script {op} {kwargs}')

        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            session_file = state / 'reader-session.json'
            session_file.write_text('{"session": "test"}')
            with (
                mock.patch.object(c, 'STATE', state),
                mock.patch.object(c, 'desktop_lock', fake_lock),
                mock.patch.object(c, 'command', fake_command),
                mock.patch.object(c, 'script', fake_script),
                mock.patch.object(c, 'raw_script', fake_raw_script),
                mock.patch.object(c, 'powershell', lambda _script, timeout=45: ''),
                mock.patch.object(c, 'harness_fingerprint', lambda: {'test': 'abc'}),
                mock.patch.object(readiness.resources, 'host', lambda: {'oom_kills': 0}),
                mock.patch.object(sys, 'argv', ['readiness.py', '--fixture', '2024']),
            ):
                with self.assertRaisesRegex(RuntimeError, 'blank-2024-read'):
                    readiness.main()
            report = json.loads((state / 'readiness-latest.json').read_text())
            session_exists = session_file.exists()
        return events, report, session_exists

    def test_first_read_failure_retains_and_closes_before_releasing_lock(self):
        events, report, session_exists = self._run_failed_first_read()
        self.assertFalse(report['passed'])
        self.assertEqual(report['status'], 'failed')
        self.assertIn('cleanup', report)
        cleanup = report['cleanup']
        self.assertTrue(cleanup['closed'])
        self.assertTrue(cleanup['retained_path'].endswith('-failed-retained.pdf'))
        self.assertFalse(session_exists)

        save_idx = next(i for i, ev in enumerate(events) if ev[0] == 'raw_script' and ev[1] == 'save')
        close_idx = next(i for i, ev in enumerate(events) if ev[0] == 'command' and ev[1] == 'close_document')
        exit_idx = next(i for i, ev in enumerate(events) if ev[0] == 'lock_exit')
        self.assertLess(save_idx, close_idx)
        self.assertLess(close_idx, exit_idx)
        self.assertEqual(events[close_idx][2]['path'], cleanup['retained_path'])

    def test_save_failure_still_closes_active_path_under_lock(self):
        events, report, session_exists = self._run_failed_first_read(save_error='Modal dialog blocked save')
        cleanup = report['cleanup']
        self.assertEqual(cleanup['save_error'], 'Modal dialog blocked save')
        self.assertIsNone(cleanup['retained_path'])
        self.assertTrue(cleanup['closed'])
        self.assertFalse(session_exists)

        close_idx = next(i for i, ev in enumerate(events) if ev[0] == 'command' and ev[1] == 'close_document')
        exit_idx = next(i for i, ev in enumerate(events) if ev[0] == 'lock_exit')
        self.assertLess(close_idx, exit_idx)
        self.assertEqual(events[close_idx][2]['path'], cleanup['active_path'])

    def test_no_open_pdf_skips_save_and_close(self):
        events, report, session_exists = self._run_failed_first_read(open_windows=[])
        cleanup = report['cleanup']
        self.assertTrue(cleanup['closed'])
        self.assertEqual(cleanup['open_windows'], [])
        self.assertIsNone(cleanup['retained_path'])
        self.assertTrue(session_exists)
        self.assertFalse(any(ev[0] == 'raw_script' and ev[1] == 'save' for ev in events))
        self.assertFalse(any(ev[0] == 'command' and ev[1] == 'close_document' for ev in events))


if __name__ == '__main__':
    unittest.main()
