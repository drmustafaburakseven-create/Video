"""Daily orchestration recovery, topic history and local concurrency behavior."""
import contextlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from automation import daily, editorial
from automation.state import LocalJournal, PipelineError
from automation.tests.test_editorial import script as script_fixture, topics as topic_fixture, evidence


DAY = '2026-11-16'


def complete_batch(day, topics, sources, journal, output, provider, model, videos):
    script = script_fixture(topics[0]['id'])
    script['age_group'] = topics[0]['age_group']
    script['sources'] = topics[0]['sources']
    validated = editorial.validate_response({'scripts': [script]}, topics, videos)
    return {'schema': 'daily-editorial-v1', 'date': day, 'topics': topics,
            'provider': provider, 'model': model, 'selected_topic_ids': [topics[0]['id']],
            'scripts': validated, 'status': 'drafts_ready', 'auto_published': False}


class DailyRunTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.catalog = self.root/'catalog.json'
        self.catalog.write_text(json.dumps({'version': 1, 'topics': topic_fixture(9)}))
        self.journal = LocalJournal(self.root/'persistent-journal')

    def tearDown(self):
        self.temporary.cleanup()

    def run_day(self, output='output', **kwargs):
        return daily.run_daily(DAY, self.root/output, journal=self.journal,
                               catalog_path=self.catalog, **kwargs)

    def test_completed_day_restores_on_fresh_runner_without_source_or_llm_calls(self):
        with patch('automation.daily.fetch_sources', return_value=evidence()) as fetch, \
                patch('automation.daily.editorial.create_daily', side_effect=complete_batch) as create:
            first = self.run_day('first')
        self.assertEqual(first['status'], 'editorial_ready')
        self.assertTrue(first['video_not_created'])
        self.assertFalse(first['reused'])
        fetch.assert_called_once()
        create.assert_called_once()
        # A new output directory has no local source cache or rendered draft artifacts.
        with patch('automation.daily.fetch_sources', side_effect=AssertionError('Unexpected research')) as fetch, \
                patch('automation.daily.editorial.create_daily', side_effect=AssertionError('Unexpected paid call')) as create:
            second = self.run_day('fresh-runner', provider='claude')
        self.assertTrue(second['reused'])
        self.assertEqual(second['provider'], first['provider'])
        self.assertTrue((self.root/'fresh-runner'/DAY/'daily.json').exists())
        self.assertTrue((self.root/'fresh-runner'/DAY/'daily.md').exists())
        self.assertEqual(len(list((self.root/'fresh-runner'/DAY).glob('*.editorial.json'))), 1)
        fetch.assert_not_called()
        create.assert_not_called()

    def test_failed_draft_freezes_topics_and_sources_without_marking_success(self):
        with patch('automation.daily.fetch_sources', return_value=evidence()) as fetch, \
                patch('automation.daily.editorial.create_daily', side_effect=PipelineError('Provider stopped')):
            with self.assertRaisesRegex(PipelineError, 'Provider stopped'):
                self.run_day()
        frozen = self.journal.load('daily-'+DAY)
        self.assertNotIn('complete', frozen)
        self.assertEqual(len(frozen['topics']), 5)
        self.assertIn('sources', frozen)
        self.assertEqual(self.journal.load(daily.HISTORY_NAME), {})
        # Altering catalog/research/provider cannot silently buy another attempt.
        self.catalog.write_text('{}')
        with patch('automation.daily.fetch_sources', side_effect=AssertionError('Must reuse evidence')) as fetch, \
                patch('automation.daily.editorial.create_daily', side_effect=complete_batch) as create:
            result = self.run_day('retry', provider='claude', model='another-model')
        fetch.assert_not_called()
        self.assertEqual(create.call_args.args[1], frozen['topics'])
        self.assertEqual(create.call_args.args[2], frozen['sources'])
        self.assertEqual(create.call_args.kwargs['provider'], frozen['provider'])
        self.assertEqual(create.call_args.kwargs['model'], frozen['model'])
        self.assertEqual(result['status'], 'editorial_ready')

    def test_history_only_records_the_selected_script_and_is_idempotent(self):
        with patch('automation.daily.fetch_sources', return_value=evidence()), \
                patch('automation.daily.editorial.create_daily', side_effect=complete_batch):
            self.run_day()
            self.run_day()
        state = self.journal.load('daily-'+DAY)
        history = self.journal.load(daily.HISTORY_NAME)['entries']
        self.assertEqual(history, [{'date': DAY, 'selected_topic_ids': [state['topics'][0]['id']]}])
        self.assertEqual(len(state['topics']), 5)

    def test_history_is_recovered_after_completed_batch_save(self):
        with patch('automation.daily.fetch_sources', return_value=evidence()), \
                patch('automation.daily.editorial.create_daily', side_effect=complete_batch), \
                patch('automation.daily._record_success', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                self.run_day()
        self.assertTrue(self.journal.load('daily-'+DAY)['complete'])
        with patch('automation.daily.fetch_sources') as fetch, \
                patch('automation.daily.editorial.create_daily') as create:
            result = self.run_day('recovered')
        self.assertTrue(result['reused'])
        fetch.assert_not_called()
        create.assert_not_called()
        self.assertEqual(len(self.journal.load(daily.HISTORY_NAME)['entries']), 1)

    def test_checkpoint_failure_prevents_research_and_model_calls(self):
        with patch.object(self.journal, 'save', side_effect=OSError('cannot persist')), \
                patch('automation.daily.fetch_sources') as fetch, \
                patch('automation.daily.editorial.create_daily') as create:
            with self.assertRaises(OSError):
                self.run_day()
        fetch.assert_not_called()
        create.assert_not_called()

    def test_changed_completed_script_is_rejected_without_repurchase(self):
        with patch('automation.daily.fetch_sources', return_value=evidence()), \
                patch('automation.daily.editorial.create_daily', side_effect=complete_batch):
            self.run_day()
        state = self.journal.load('daily-'+DAY)
        state['batch']['scripts'][0]['sources'] = ['https://unverified.example/claim']
        self.journal.save('daily-'+DAY, state)
        with patch('automation.daily.editorial.create_daily') as create:
            with self.assertRaisesRegex(PipelineError, 'outside the verified'):
                self.run_day('changed')
        create.assert_not_called()

    def test_offline_preview_does_not_fetch_generate_or_freeze_day(self):
        with patch('automation.daily.fetch_sources') as fetch, \
                patch('automation.daily.editorial.create_daily') as create:
            result = self.run_day(offline_topics=True)
        self.assertEqual(result['scripts'], 0)
        self.assertTrue((self.root/'output'/DAY/'topics.json').exists())
        self.assertFalse((self.root/'output'/DAY/'daily.json').exists())
        self.assertEqual(self.journal.load('daily-'+DAY), {})
        fetch.assert_not_called()
        create.assert_not_called()

    def test_held_outer_lock_rejects_second_run_before_provider_work(self):
        folder = self.root/'output'
        with daily.RunLock(folder/'.daily.lock'), \
                patch('automation.daily.fetch_sources') as fetch, \
                patch('automation.daily.editorial.create_daily') as create:
            with self.assertRaisesRegex(PipelineError, 'Başka bir günlük'):
                self.run_day()
        fetch.assert_not_called()
        create.assert_not_called()
        # The losing contender did not unlock the original owner's descriptor.
        with daily.RunLock(folder/'.daily.lock'):
            pass


class DailyCliTests(unittest.TestCase):
    def test_date_uses_turkey_midnight_not_utc(self):
        self.assertEqual(daily.today_in_turkey(datetime(2026, 11, 16, 22, tzinfo=timezone.utc)), '2026-11-17')

    def test_offline_mode_works_without_github_credentials_or_network(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}, clear=True), \
                patch('automation.daily.GitHubJournal') as github, \
                patch('automation.daily.fetch_sources') as fetch, \
                patch('automation.daily.editorial.create_daily') as create, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(daily.main(['--date', DAY, '--output', directory, '--offline-topics']), 0)
            result = json.loads((Path(directory)/'status.json').read_text())
        self.assertEqual(result['status'], 'topic_suggestions_only')
        self.assertTrue(result['video_not_created'])
        github.assert_not_called()
        fetch.assert_not_called()
        create.assert_not_called()

    def test_github_mode_uses_separate_journal_and_checks_required_fields(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}, clear=True), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(daily.main(['--date', DAY, '--output', directory]), 2)
            result = json.loads((Path(directory)/'status.json').read_text())
            self.assertIn('GITHUB_REPOSITORY', result['message'])
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'owner/repo',
                                    'GITHUB_TOKEN': 'test-placeholder', 'GITHUB_SHA': 'a'*40}, clear=True), \
                patch('automation.daily.GitHubJournal') as factory:
            daily._journal(Path('/tmp/output'))
            factory.assert_called_once_with('owner/repo', 'test-placeholder', 'a'*40)

    def test_provider_exception_body_does_not_reach_status(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {}, clear=True), \
                patch('automation.daily.run_daily', side_effect=RuntimeError('SECRET-EXAMPLE')), \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(daily.main(['--date', DAY, '--output', directory]), 2)
            text = (Path(directory)/'status.json').read_text()
        self.assertNotIn('SECRET-EXAMPLE', text+stdout.getvalue())
        self.assertIn('RuntimeError', text)


if __name__ == '__main__':
    unittest.main()
