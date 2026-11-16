"""Schedule boundaries and once-per-day receipts without sleeping or providers."""
import contextlib
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from automation import worker

DAY = '2026-11-16'
AT_NINE = datetime(2026, 11, 16, 6, tzinfo=timezone.utc)


class ScheduleTests(unittest.TestCase):
    def test_nine_boundary_and_late_start_catch_up_today_only(self):
        before = datetime(2026, 11, 16, 5, 59, tzinfo=timezone.utc)
        late = datetime(2026, 11, 16, 18, tzinfo=timezone.utc)
        self.assertIsNone(worker.due_date(before, {}))
        self.assertEqual(worker.next_due(before, {}).hour, 9)
        self.assertEqual(worker.due_date(AT_NINE, {}), DAY)
        self.assertEqual(worker.due_date(late, {}), DAY)
        self.assertEqual(worker.next_due(late, {}), worker.local_now(late))

    def test_failure_or_started_receipt_defers_until_next_day(self):
        for status in ['blocked', 'started', 'timed_out', 'finished']:
            attempts = {DAY: {'status': status}}
            with self.subTest(status=status):
                self.assertIsNone(worker.due_date(AT_NINE, attempts))
                self.assertEqual(worker.next_due(AT_NINE, attempts).isoformat(), '2026-11-17T09:00:00+03:00')

    def test_turkey_midnight_and_weekends(self):
        midnight = datetime(2026, 11, 16, 22, tzinfo=timezone.utc)
        self.assertEqual(worker.effective_date(midnight), '2026-11-17')
        self.assertIsNone(worker.due_date(midnight, {}))
        saturday = datetime(2026, 11, 21, 6, tzinfo=timezone.utc)
        self.assertEqual(worker.due_date(saturday, {}), '2026-11-21')


class ReceiptTests(unittest.TestCase):
    def test_saved_intent_survives_restart_and_blocks_second_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'status.json').write_text(json.dumps({'date': DAY, 'status': 'editorial_ready'}))
            state = worker.load_state(root)
            runner = Mock(return_value=Mock(returncode=0, stdout='PRIVATE-EXAMPLE', stderr='PRIVATE-EXAMPLE'))
            result = worker.attempt_once(DAY, root, state, now=AT_NINE, runner=runner)
            self.assertEqual(result['status'], 'finished')
            self.assertFalse(result['video_created'])
            worker.attempt_once(DAY, root, worker.load_state(root), now=AT_NINE, runner=runner)
            runner.assert_called_once()
            self.assertNotIn('PRIVATE-EXAMPLE', (root/'worker-state.json').read_text())
            command = runner.call_args.args[0]
            self.assertIn('automation.studio', command)
            self.assertIn(DAY, command)

    def test_failed_or_timed_out_child_is_not_automatically_retried(self):
        for error in [subprocess.TimeoutExpired('studio', 3), OSError('private-error')]:
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as directory:
                state = worker.load_state(directory)
                runner = Mock(side_effect=error)
                result = worker.attempt_once(DAY, directory, state, now=AT_NINE, runner=runner)
                self.assertIn(result['status'], ['timed_out', 'launch_failed'])
                restarted = worker.load_state(directory)
                self.assertIsNone(worker.due_date(AT_NINE, restarted['attempts']))
                worker.attempt_once(DAY, directory, restarted, runner=runner)
                runner.assert_called_once()

    def test_checkpoint_failure_never_launches_child(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch('automation.worker.save_state', side_effect=OSError('disk unavailable')):
            runner = Mock()
            with self.assertRaises(OSError):
                worker.attempt_once(DAY, directory, {'version': 1, 'attempts': {}}, runner=runner)
            runner.assert_not_called()

    def test_stale_success_status_is_not_attributed_to_today(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'status.json').write_text(json.dumps({'date': '2026-11-15', 'status': 'completed'}))
            result = worker.attempt_once(DAY, root, worker.load_state(root), now=AT_NINE,
                                         runner=Mock(return_value=Mock(returncode=0)))
            self.assertEqual(result['status'], 'blocked')
            self.assertFalse(result['video_created'])

    def test_check_only_has_no_subprocess_or_sleep(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch('automation.worker.subprocess.run') as runner, \
                patch('automation.worker.time.sleep') as sleep, \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(worker.main(['--output', directory, '--check-only']), 0)
            status = json.loads(stdout.getvalue())
            self.assertTrue(status['check_only'])
            self.assertEqual(status['daily_attempt_limit'], 1)
            self.assertFalse((Path(directory)/'worker-state.json').exists())
        runner.assert_not_called()
        sleep.assert_not_called()

    def test_once_reports_blocked_child_as_nonzero_and_does_not_sleep(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch('automation.worker.local_now', return_value=datetime(2026, 11, 16, 9, tzinfo=worker.TURKEY)), \
                patch('automation.worker.subprocess.run', return_value=Mock(returncode=2)) as runner, \
                patch('automation.worker.time.sleep') as sleep, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(worker.main(['--output', directory, '--once']), 2)
            self.assertEqual(worker.load_state(directory)['attempts'][DAY]['status'], 'blocked')
        runner.assert_called_once()
        sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
