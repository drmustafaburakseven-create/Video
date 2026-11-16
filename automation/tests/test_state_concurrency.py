"""Separate processes must not submit the same billable operation twice."""
import multiprocessing
from pathlib import Path
import tempfile
import unittest

from automation.state import LocalJournal, paid_once


def _submit_from_stale_state(directory, ready, start, results):
    journal = LocalJournal(Path(directory)/'journal')
    state = journal.load('same-video')
    ready.put(state)
    if not start.wait(timeout=15):
        raise RuntimeError('Test start barrier was not released.')

    def submit():
        with (Path(directory)/'submissions.txt').open('a') as stream:
            stream.write('paid request\n')
        return {'id': 'single-paid-operation'}

    receipt = paid_once(journal, 'same-video', state, 'generation', submit)
    results.put(receipt)


class LocalJournalConcurrencyTests(unittest.TestCase):
    def test_two_fresh_processes_refresh_stale_state_before_paid_submission(self):
        context = multiprocessing.get_context('spawn')
        with tempfile.TemporaryDirectory() as directory:
            ready, results = context.Queue(), context.Queue()
            start = context.Event()
            processes = [context.Process(target=_submit_from_stale_state,
                                         args=(directory, ready, start, results))
                         for _ in range(2)]
            try:
                for process in processes:
                    process.start()
                # Both interpreters must have read the same empty journal before
                # either enters paid_once. A per-process mutex cannot solve this.
                self.assertEqual([ready.get(timeout=15) for _ in processes], [{}, {}])
                start.set()
                receipts = [results.get(timeout=15) for _ in processes]
                for process in processes:
                    process.join(timeout=15)
                    self.assertEqual(process.exitcode, 0)
                expected = {'id': 'single-paid-operation'}
                self.assertEqual(receipts, [expected, expected])
                self.assertEqual((Path(directory)/'submissions.txt').read_text().splitlines(),
                                 ['paid request'])
                saved = LocalJournal(Path(directory)/'journal').load('same-video')
                self.assertEqual(saved['generation'], {'status': 'received', 'response': expected})
            finally:
                start.set()
                for process in processes:
                    if process.is_alive():
                        process.terminate()
                    if process.pid is not None:
                        process.join(timeout=5)
                ready.close()
                results.close()
                ready.join_thread()
                results.join_thread()
