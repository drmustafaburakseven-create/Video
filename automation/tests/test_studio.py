"""Daily studio must preserve receipts and stop before paid media when inputs lack."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from automation import daily, editorial, studio
from automation.state import LocalJournal, PipelineError
from automation.tests.test_editorial import script as script_fixture, topics

DAY = '2026-11-16'


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.code = self.root/'automation'
        self.output = self.root/'output'
        self.journal = LocalJournal(self.root/'journal')
        self.portrait = self.root/'own-portrait.png'
        Image.new('RGB', (256, 256)).save(self.portrait)
        selected = topics()
        script = script_fixture()
        script['scenes'][5]['kind'] = 'generated'
        script['scenes'][6]['kind'] = 'generated'
        scripts = editorial.validate_response({'scripts': [script]}, selected, 1)
        batch = {'schema': 'daily-editorial-v1', 'date': DAY, 'topics': selected,
                 'provider': 'gemini', 'model': editorial.DEFAULT_MODELS['gemini'],
                 'selected_topic_ids': ['topic-0'], 'scripts': scripts}
        self.journal.save('daily-'+DAY, {'date': DAY, 'topics': selected, 'provider': 'gemini',
                                      'model': batch['model'], 'videos': 1, 'complete': True, 'batch': batch})
        self.assets = {'reviewed-stock': {'kind': 'stock', 'duration': 60,
                       'path': 'media/library/reviewed-stock.mp4',
                       'sha256': hashlib.sha256(b'fixture').hexdigest(),
                       'approved_topics': ['topic-0'], 'description': 'Soft food in a high chair.'}}
        self.stack = contextlib.ExitStack()
        self.stack.enter_context(patch.object(studio, 'ROOT', self.code))
        self.stack.enter_context(patch.dict(os.environ, {}, clear=True))
        self.fetch = self.stack.enter_context(patch.object(daily, 'fetch_sources', side_effect=AssertionError('Research must reuse receipt')))
        self.create = self.stack.enter_context(patch.object(editorial, 'create_daily', side_effect=AssertionError('No second paid draft')))
        self.catalog = self.stack.enter_context(patch.object(studio.hybrid, 'catalog', return_value=self.assets))
        self.preflight = self.stack.enter_context(patch.object(studio.produce, '_preflight_media', return_value=([], [])))
        self.produce = self.stack.enter_context(patch.object(studio.produce, 'produce'))

    def tearDown(self):
        self.stack.close()
        self.temp.cleanup()

    def run_studio(self, portrait=None, **kwargs):
        return studio.run_studio(DAY, self.output, portrait, journal=self.journal, **kwargs)

    def test_missing_portrait_preserves_daily_draft_and_never_calls_production(self):
        result = self.run_studio()
        self.assertEqual(result['status'], 'needs_inputs')
        self.assertEqual([item['name'] for item in result['inputs']], ['portrait'])
        self.assertTrue(result['editorial_reused'])
        self.assertTrue(result['video_not_created'])
        self.assertFalse(json.loads(Path(result['compiled_plan']).read_text())['enabled'])
        self.assertTrue((self.output/'studio'/DAY/'daily.md').is_file())
        self.produce.assert_not_called()
        self.fetch.assert_not_called()
        self.create.assert_not_called()

    def test_missing_library_reports_it_with_portrait_without_tts_or_video(self):
        self.catalog.return_value = {}
        result = self.run_studio(self.portrait)
        self.assertEqual(result['status'], 'needs_inputs')
        self.assertEqual([item['name'] for item in result['inputs']], ['approved_footage'])
        self.assertNotIn('compiled_plan', result)
        self.assertEqual(self.journal.load('studio-'+DAY), {})
        self.produce.assert_not_called()
        self.preflight.assert_not_called()

    def test_changed_media_integrity_is_not_treated_as_ready(self):
        self.preflight.side_effect = PipelineError('Media hash mismatch: reviewed-stock')
        result = self.run_studio(self.portrait)
        self.assertEqual(result['status'], 'needs_inputs')
        self.assertIn('hash mismatch', result['inputs'][0]['message'])
        self.produce.assert_not_called()

    def test_editorial_only_never_needs_portrait_or_media(self):
        result = self.run_studio(editorial_only=True)
        self.assertEqual(result['status'], 'editorial_ready')
        self.assertEqual((result['topics'], result['scripts']), (5, 1))
        self.assertTrue(result['video_not_created'])
        self.catalog.assert_not_called()
        self.produce.assert_not_called()
        self.create.assert_not_called()

    def test_completed_mock_production_uses_frozen_plan_and_stays_unpublished(self):
        final = self.output/'render'/'video.mp4'
        self.produce.return_value = final
        first = self.run_studio(self.portrait)
        self.assertEqual(first['status'], 'completed')
        self.assertFalse(first['video_not_created'])
        self.assertFalse(first['auto_published'])
        self.assertEqual(first['clinical_review'], 'required')
        draft, portrait, provider, output = self.produce.call_args.args
        self.assertEqual(draft.parent, self.code/'drafts')
        self.assertFalse(json.loads(draft.read_text())['enabled'])
        self.assertEqual((portrait, provider, output), (self.portrait, 'fal', self.output))
        self.assertIs(self.produce.call_args.kwargs['journal'], self.journal)
        # A richer later library cannot silently change an already frozen plan.
        self.catalog.return_value = {}
        second = self.run_studio(self.portrait)
        self.assertEqual(first['compiled_plan'], second['compiled_plan'])
        self.create.assert_not_called()

    def test_existing_user_edited_compiled_plan_is_never_overwritten(self):
        first = self.run_studio()
        path = Path(first['compiled_plan'])
        path.write_text('{"user_edit": true}')
        with self.assertRaisesRegex(PipelineError, 'üzerine yazılmadı'):
            self.run_studio(self.portrait)
        self.assertEqual(path.read_text(), '{"user_edit": true}')
        self.produce.assert_not_called()

    def test_invalid_cached_plan_id_cannot_escape_draft_directory(self):
        self.run_studio()
        state = self.journal.load('studio-'+DAY)
        state['plan']['id'] = '../../../outside'
        self.journal.save('studio-'+DAY, state)
        with self.assertRaisesRegex(PipelineError, 'kurgu eşleşmiyor'):
            self.run_studio(self.portrait)
        self.produce.assert_not_called()


class StudioCliTests(unittest.TestCase):
    def test_needs_inputs_has_nonzero_exit_and_secret_free_error(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(studio, 'run_studio', side_effect=RuntimeError('sensitive-provider-body')), \
                contextlib.redirect_stdout(io.StringIO()) as stdout:
            code = studio.main(['--date', DAY, '--output', directory])
            result = (Path(directory)/'status.json').read_text()
        self.assertEqual(code, 2)
        self.assertNotIn('sensitive-provider-body', stdout.getvalue()+result)
        self.assertIn('RuntimeError', result)

    def test_invalid_date_does_not_make_date_based_paths(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            code = studio.main(['--date', '../../escape', '--output', directory])
            self.assertEqual(code, 2)
            self.assertEqual([p.name for p in Path(directory).iterdir()], ['status.json'])


if __name__ == '__main__':
    unittest.main()
