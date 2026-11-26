"""Three distinct jobs, restart safety and copy tied to the actual narration."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from automation import batch_studio, daily, editorial, publishing
from automation.state import LocalJournal, PipelineError
from automation.tests.test_editorial import script as old_script, topics, evidence

DAY = '2026-11-18'


def warm_script(topic, *, label_speakers=False):
    value = old_script(topic['id'])
    value.update(title=topic['title'], age_group=topic['age_group'], sources=topic['sources'])
    chunks = value.pop('scenes')
    value.pop('narration')
    value['speech_sections'] = {
        'intro': ' '.join(s['speech'] for s in chunks[:3]),
        'body': ' '.join(s['speech'] for s in chunks[3:12]),
        'outro': ' '.join(s['speech'] for s in chunks[12:])}
    if label_speakers:
        opening = value['hooks'][value['selected_hook']]['text']
        intro = value['speech_sections']['intro']
        assert intro.startswith(opening)
        value['speech_sections']['intro'] = f"Dış ses: {opening} Dr. Mustafa Burak Seven: {intro[len(opening):].strip()}"
    value['broll'] = [{k: chunks[1][k] for k in ('visual', 'screen_text', 'motion_prompt')} for _ in range(13)]
    result = editorial.compile_storyboard({'scripts': [value]}, 'warm-office-60')
    return editorial.validate_response(result, [topic], 1)[0]


def completed_batch(day, selected, sources, journal, output, provider, model, videos, profile):
    scripts = [warm_script(topic) for topic in selected[:videos]]
    return {'schema': 'daily-editorial-v1', 'date': day, 'topics': selected,
            'provider': provider, 'model': model, 'selected_topic_ids': [s['topic_id'] for s in scripts],
            'scripts': scripts, 'status': 'drafts_ready', 'auto_published': False}


class ThreeDailyTests(unittest.TestCase):
    def test_three_topics_survive_restart_without_new_model_or_source_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            catalog = root/'catalog.json'
            catalog.write_text(json.dumps({'topics': topics(8)}))
            journal = LocalJournal(root/'journal')
            with patch.object(daily, 'fetch_sources', return_value=evidence()), \
                    patch.object(editorial, 'create_daily', side_effect=completed_batch) as create:
                first = daily.run_daily(DAY, root/'one', journal=journal, catalog_path=catalog,
                                        videos=3, profile='warm-office-60')
            self.assertEqual(first['scripts'], 3)
            create.assert_called_once()
            with patch.object(editorial, 'create_daily') as create, patch.object(daily, 'fetch_sources') as fetch:
                second = daily.run_daily(DAY, root/'two', journal=journal, videos=3, profile='warm-office-60')
            self.assertTrue(second['reused'])
            create.assert_not_called()
            fetch.assert_not_called()
            history = journal.load(daily.HISTORY_NAME)['entries']
            self.assertEqual(len(set(history[0]['selected_topic_ids'])), 3)
            self.assertEqual(len(list((root/'two'/DAY).glob('*/reels.txt'))), 3)
            self.assertEqual(len(list((root/'two'/DAY).glob('*/shorts.txt'))), 3)
            with self.assertRaisesRegex(PipelineError, 'farklı video sayısıyla'):
                daily.run_daily(DAY, root/'two', journal=journal, videos=1, profile='warm-office-60')

    def test_spoken_text_excludes_gemini_speaker_labels(self):
        topic = topics()[0]
        self.assertEqual(warm_script(topic, label_speakers=True), warm_script(topic))

    def test_warm_timeline_starts_and_ends_with_doctor(self):
        script = warm_script(topics()[0])
        scenes = script['scenes']
        self.assertEqual([(s['start'], s['duration']) for s in scenes if s['kind'] == 'avatar'], [(0, 10), (50, 10)])
        self.assertEqual(sum(s['duration'] for s in scenes), 60)
        self.assertTrue(all(s['duration'] in (3, 4) for s in scenes[1:-1]))
        self.assertEqual(' '.join(s['speech'] for s in scenes).split(), script['narration'].split())

    def test_one_missing_package_does_not_erase_two_successes_or_social_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            journal = LocalJournal(root/'journal')
            selected = topics()
            batch = completed_batch(DAY, selected, {}, journal, root, 'gemini', 'model', 3, 'warm-office-60')
            journal.save('daily-'+DAY, {'date': DAY, 'topics': selected, 'provider': 'gemini',
                                       'model': 'model', 'videos': 3, 'profile': 'warm-office-60',
                                       'complete': True, 'batch': batch})
            with patch.object(batch_studio.ready_reel, 'prepare', side_effect=[{}, PipelineError('missing'), {}]), \
                    patch.object(batch_studio.ready_reel, 'render', side_effect=lambda s, m, d: d/'video.mp4'):
                result = batch_studio.run(DAY, root/'out', journal=journal)
            self.assertEqual(result['status'], 'partially_completed')
            self.assertEqual(result['completed_videos'], 2)
            self.assertEqual([i['status'] for i in result['items']], ['completed', 'needs_inputs', 'completed'])
            self.assertFalse(result['auto_published'])
            for item in result['items']:
                self.assertTrue((Path(item['directory'])/'paylasim.md').is_file())


class PublishingTests(unittest.TestCase):
    def test_exact_narration_and_sources_no_new_provider_call(self):
        script = old_script()
        with tempfile.TemporaryDirectory() as folder:
            package = publishing.write(script, folder)
            self.assertEqual(package['reels']['caption'], script['narration'])
            self.assertEqual(package['narration_sha256'], publishing.narration_hash(script))
            self.assertIn(script['sources'][0], (Path(folder)/'shorts.txt').read_text())
            self.assertNotIn('@kullaniciadin', (Path(folder)/'reels.txt').read_text())

    def test_invalid_platform_copy_is_rejected(self):
        script = old_script()
        base = publishing.package(script)
        for field, value in [('title', 'x'*101), ('description', 'See https://unverified.example'),
                              ('hashtags', ['#foo', '#FOO']), ('hashtags', ['#not a tag'])]:
            changed = copy.deepcopy(base)
            changed['youtube_shorts'][field] = value
            with self.subTest(field=field), self.assertRaises(PipelineError):
                publishing.package(script, changed)

    def test_long_title_gets_a_complete_short_title_not_over_100(self):
        script = old_script()
        script['title'] = 'Bebeğinize yeni besinleri sunarken ' * 5
        package = publishing.package(script)
        self.assertLessEqual(len(package['youtube_shorts']['title']), 100)
        self.assertTrue(package['youtube_shorts']['title'].endswith('…'))


if __name__ == '__main__':
    unittest.main()
