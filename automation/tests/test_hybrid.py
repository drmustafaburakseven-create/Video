"""Cost, media integrity and exact avatar-audio checks without provider calls."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

from automation import hybrid, pipeline
from automation.render import probe
from automation.state import LocalJournal, PipelineError


PROMPT = 'A real moving close-up of an adult gently mashing soft cooked vegetables.'


def plan_fixture():
    return {
        'format': 'hybrid-v1',
        'id': 'hybrid-test',
        'title': 'Hybrid test',
        'duration_seconds': 60,
        'narration': 'Bu bir test anlatımıdır. ' * 24,
        'sources': ['https://www.cdc.gov/infant-toddler-nutrition/'],
        'shots': [{'kind': 'stock', 'asset_id': 'kitchen', 'duration': 4}
                  for _ in range(15)],
    }


def generated_shot(name='vegetables', offset=0, prompt=PROMPT):
    return {'kind': 'generated', 'generation_id': name, 'generation_seconds': 8,
            'duration': 4, 'source_start': offset, 'prompt': prompt}


class HybridValidationTests(unittest.TestCase):
    def test_segments_total_exactly_sixty_seconds(self):
        plan = plan_fixture()
        self.assertEqual(hybrid.validate(plan)['stock_seconds'], 60)
        for duration in [3.9, 4.1]:
            with self.subTest(duration=duration):
                plan['shots'][0]['duration'] = duration
                with self.assertRaisesRegex(PipelineError, 'exactly 60'):
                    hybrid.validate(plan)

    def test_reused_generation_counts_source_once_and_enforces_cap(self):
        plan = plan_fixture()
        plan['shots'][0:2] = [generated_shot(), generated_shot(offset=4)]
        budget = hybrid.validate(plan)
        self.assertEqual((budget['new_clip_count'], budget['generated_seconds']), (1, 8))
        plan['shots'][2] = generated_shot('second')
        self.assertEqual(hybrid.validate(plan)['generated_seconds'], 16)
        plan['shots'][3] = generated_shot('third')
        with self.assertRaisesRegex(PipelineError, 'Cost cap'):
            hybrid.validate(plan)

    def test_generation_id_cannot_describe_different_paid_requests(self):
        plan = plan_fixture()
        plan['shots'][0:2] = [generated_shot(), generated_shot(prompt=PROMPT + ' In daylight.')]
        with self.assertRaisesRegex(PipelineError, 'identical duration and prompt'):
            hybrid.validate(plan)

    def test_generation_must_cover_selected_source_interval(self):
        plan = plan_fixture()
        plan['shots'][0] = generated_shot(offset=5)
        with self.assertRaisesRegex(PipelineError, 'cover all selected frames'):
            hybrid.validate(plan)

    def test_avatar_has_twelve_second_cap_and_starts_at_first_frame(self):
        plan = plan_fixture()
        for index in range(3):
            plan['shots'][index] = {'kind': 'avatar', 'asset_id': 'doctor', 'duration': 4}
        self.assertEqual(hybrid.validate(plan)['avatar_seconds'], 12)
        plan['shots'][3] = {'kind': 'avatar', 'asset_id': 'doctor', 'duration': 4}
        with self.assertRaisesRegex(PipelineError, 'Cost cap'):
            hybrid.validate(plan)
        plan['shots'][3] = {'kind': 'stock', 'asset_id': 'kitchen', 'duration': 4}
        plan['shots'][0]['source_start'] = 0.25
        with self.assertRaisesRegex(PipelineError, 'first frame'):
            hybrid.validate(plan)

    def test_source_offsets_must_be_finite_numbers_not_booleans(self):
        for offset in [True, False, float('nan'), float('inf'), -1]:
            with self.subTest(offset=offset):
                plan = plan_fixture()
                plan['shots'][0]['source_start'] = offset
                with self.assertRaisesRegex(PipelineError, 'source_start'):
                    hybrid.validate(plan)

    def test_enabling_a_plan_does_not_change_paid_job_identity(self):
        plan = plan_fixture()
        plan['enabled'] = False
        with patch('automation.hybrid.fingerprint', return_value='same-media'):
            disabled = pipeline.job_name(plan, 'test-model', 'test-voice', False)
            plan['enabled'] = True
            enabled = pipeline.job_name(plan, 'test-model', 'test-voice', False)
        self.assertEqual(disabled, enabled)


class HybridMediaTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root/'media').mkdir()
        self.clip = self.root/'media/clip.mp4'
        self.clip.write_bytes(b'fixture: no real video needed for metadata validation')
        self.plan = plan_fixture()
        self.plan['shots'][0] = {'kind': 'avatar', 'asset_id': 'doctor', 'duration': 4}
        metadata = {'path': 'media/clip.mp4',
                    'sha256': hashlib.sha256(self.clip.read_bytes()).hexdigest()}
        self.assets = {
            'kitchen': {**metadata, 'kind': 'stock', 'license': 'Test fixture only',
                        'source_url': 'https://example.com/licensed-fixture'},
            'doctor': {**metadata, 'kind': 'avatar', 'timeline_start': 0,
                       'narration_sha256': hashlib.sha256(self.plan['narration'].encode()).hexdigest(),
                       'audio_sha256': 'a' * 64},
        }
        prober = patch('automation.hybrid.probe', return_value={
            'streams': [{'codec_type': 'video', 'duration': '8.0'}],
            'format': {'duration': '8.0'},
        })
        self.probe = prober.start()
        self.addCleanup(prober.stop)

    def write_catalog(self):
        (self.root/'media/catalog.json').write_text(json.dumps({'version': 1, 'assets': self.assets}))

    def test_resolve_keeps_exact_timeline_and_checks_media_hash(self):
        self.write_catalog()
        segments = hybrid.resolve(self.plan, self.root)
        self.assertEqual([segment['start'] for segment in segments], list(range(0, 60, 4)))
        self.assertTrue(all(segment['path'] == self.clip for segment in segments))
        self.clip.write_bytes(b'changed after catalog import')
        with self.assertRaisesRegex(PipelineError, 'hash mismatch'):
            hybrid.resolve(self.plan, self.root)

    def test_media_path_and_symlink_cannot_escape_media_directory(self):
        outside = self.root/'outside.mp4'
        outside.write_bytes(self.clip.read_bytes())
        (self.root/'media/link.mp4').symlink_to(outside)
        for path in ['outside.mp4', 'media/../outside.mp4', 'media/link.mp4']:
            with self.subTest(path=path):
                self.assets['doctor']['path'] = path
                self.write_catalog()
                with self.assertRaisesRegex(PipelineError, 'stay inside'):
                    hybrid.resolve(self.plan, self.root)

    def test_avatar_rejects_wrong_narration_offset_or_audio_hash(self):
        original = copy.deepcopy(self.assets['doctor'])
        for field, value in [('narration_sha256', 'b' * 64), ('timeline_start', 4),
                             ('audio_sha256', 'not-a-hash')]:
            with self.subTest(field=field):
                self.assets['doctor'] = {**original, field: value}
                self.write_catalog()
                with self.assertRaisesRegex(PipelineError, 'exact exported timeline slice'):
                    hybrid.resolve(self.plan, self.root)

    def test_avatar_rejects_nonfinite_or_boolean_timeline_start(self):
        for start in [float('nan'), float('inf'), False]:
            with self.subTest(start=start):
                self.assets['doctor']['timeline_start'] = start
                self.write_catalog()
                with self.assertRaisesRegex(PipelineError, 'exact exported timeline slice'):
                    hybrid.resolve(self.plan, self.root)

    def test_missing_reusable_media_fails_before_any_paid_operation(self):
        plan = plan_fixture()
        plan['shots'][1] = generated_shot()
        with patch('automation.hybrid.catalog', return_value={}), \
                patch('automation.hybrid.prepare') as prepare, \
                patch('automation.hybrid.paid_once') as paid, \
                patch('automation.pipeline.Omni') as provider, \
                patch('automation.pipeline.synthesize') as synthesize:
            with self.assertRaisesRegex(PipelineError, 'Missing reusable media'):
                hybrid.make(plan, 'job', {}, LocalJournal(self.root/'journal'),
                            self.root/'output', 'test-model', 'test-voice')
        prepare.assert_not_called()
        paid.assert_not_called()
        provider.assert_not_called()
        synthesize.assert_not_called()


class HybridPaidOperationTests(unittest.TestCase):
    def test_durable_voice_cache_survives_visual_plan_changes_without_second_tts(self):
        plan = plan_fixture()
        response = {'audio_base64': base64.b64encode(b'saved audio').decode(),
                    'alignment': {'characters': ['a']}}
        with tempfile.TemporaryDirectory() as directory, \
                patch('automation.pipeline.prepared_voice', return_value=None), \
                patch('automation.pipeline.synthesize', return_value=response) as synthesize:
            with patch.dict(os.environ, {'ELEVENLABS_API_KEY': 'test-placeholder'}, clear=True):
                first = hybrid.voice_result(plan, 'test-voice', LocalJournal(directory))
            revised = copy.deepcopy(plan)
            revised['id'] = 'revised-visuals'
            revised['shots'][0] = generated_shot()
            revised['shots'][1]['asset_id'] = 'different-stock'
            with patch.dict(os.environ, {}, clear=True):
                second = hybrid.voice_result(revised, 'test-voice', LocalJournal(directory))
            self.assertEqual(first, second)
            synthesize.assert_called_once_with(plan['narration'], 'test-voice')
            self.assertEqual(len(list(Path(directory).glob('narration-*.json'))), 1)

    def test_repeated_generation_id_submits_and_downloads_once(self):
        plan = plan_fixture()
        plan['shots'][0:2] = [generated_shot(), generated_shot(offset=4)]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            segments = [dict(shot, start=4 * index) for index, shot in enumerate(plan['shots'])]
            for segment in segments[2:]:
                segment['path'] = output/'stock.mp4'
            provider = Mock()
            provider.submit.return_value = {'interaction_id': 'already-paid'}
            provider.download.side_effect = lambda receipt, path: path.write_bytes(b'generated clip')

            def render(resolved, audio, alignment, target):
                (target/'video.mp4').write_bytes(b'composed video')

            with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-placeholder'}, clear=True), \
                    patch('automation.hybrid.resolve', return_value=segments), \
                    patch('automation.hybrid.prepare', return_value=(output/'voice.mp3', {}, 'a' * 64)), \
                    patch('automation.pipeline.Omni', return_value=provider), \
                    patch('automation.hybrid_render.render_hybrid', side_effect=render) as renderer:
                hybrid.make(plan, 'job', {}, LocalJournal(output/'journal'),
                            output, 'test-model', 'test-voice')
            provider.submit.assert_called_once_with(PROMPT, duration=8)
            provider.download.assert_called_once()
            rendered = renderer.call_args.args[0]
            self.assertEqual(rendered[0]['path'], rendered[1]['path'])
            self.assertEqual(rendered[1]['source_start'], 4)
            self.assertTrue(LocalJournal(output/'journal').load('job')['complete'])

    def test_generated_receipt_survives_new_job_changed_stock_and_generation_id(self):
        first = plan_fixture()
        first['shots'][0] = generated_shot()
        revised = copy.deepcopy(first)
        revised['id'] = 'new-visual-cut'
        revised['shots'][0]['generation_id'] = 'renamed-vegetables'
        revised['shots'][1]['asset_id'] = 'replacement-stock'

        def resolve(plan):
            return [dict(shot, start=4 * index,
                         **({'path': Path('/test/stock.mp4')} if shot['kind'] == 'stock' else {}))
                    for index, shot in enumerate(plan['shots'])]

        def render(segments, audio, alignment, output):
            (output/'video.mp4').write_bytes(b'composed video')

        provider = Mock()
        provider.submit.return_value = {'interaction_id': 'durable-existing-generation'}
        provider.download.side_effect = lambda receipt, path: path.write_bytes(b'recovered clip')
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {'GEMINI_API_KEY': 'test-placeholder'}, clear=True), \
                patch('automation.hybrid.resolve', side_effect=resolve), \
                patch('automation.hybrid.prepare', return_value=(Path('/test/voice.mp3'), {}, 'a' * 64)), \
                patch('automation.pipeline.Omni', return_value=provider), \
                patch('automation.hybrid_render.render_hybrid', side_effect=render):
            root = Path(directory)
            for index, plan in enumerate([first, revised]):
                output = root/str(index)
                output.mkdir()
                hybrid.make(plan, plan['id'], {}, LocalJournal(root/'journal'),
                            output, 'test-model', 'test-voice')
            provider.submit.assert_called_once_with(PROMPT, duration=8)
            self.assertEqual(provider.download.call_count, 2)
            self.assertTrue(all(call.args[0] == provider.submit.return_value
                                for call in provider.download.call_args_list))
            self.assertEqual(len(list((root/'journal').glob('generated-*.json'))), 1)

    def test_avatar_for_different_audio_take_blocks_generated_video_call(self):
        plan = plan_fixture()
        plan['shots'][0] = {'kind': 'avatar', 'asset_id': 'doctor', 'duration': 4}
        plan['shots'][1] = generated_shot()
        segments = [dict(shot, start=4 * index) for index, shot in enumerate(plan['shots'])]
        segments[0].update(path=Path('/test/avatar.mp4'), asset={'audio_sha256': 'b' * 64})
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {'GEMINI_API_KEY': 'test-placeholder'}, clear=True), \
                patch('automation.hybrid.resolve', return_value=segments), \
                patch('automation.hybrid.prepare', return_value=(Path('/test/voice.mp3'), {}, 'a' * 64)), \
                patch('automation.pipeline.Omni') as provider:
            journal = LocalJournal(Path(directory)/'journal')
            journal.save(hybrid.voice_cache_name(plan, 'test-voice'), {
                'voice': {'status': 'received', 'response': {'audio_base64': 'cached-voice'}},
            })
            with self.assertRaisesRegex(PipelineError, 'another audio take'):
                hybrid.make(plan, 'job', {}, journal, Path(directory), 'test-model', 'test-voice')
            provider.assert_not_called()

    def test_avatar_without_original_narration_blocks_tts_and_video_calls(self):
        plan = plan_fixture()
        plan['shots'][0] = {'kind': 'avatar', 'asset_id': 'doctor', 'duration': 4}
        segments = [dict(shot, start=4 * index, path=Path('/test/clip.mp4'))
                    for index, shot in enumerate(plan['shots'])]
        for status in [None, 'submitting']:
            with self.subTest(saved_status=status), tempfile.TemporaryDirectory() as directory, \
                    patch('automation.hybrid.resolve', return_value=segments), \
                    patch('automation.pipeline.prepared_voice', return_value=None), \
                    patch('automation.hybrid.prepare') as prepare, \
                    patch('automation.pipeline.synthesize') as synthesize, \
                    patch('automation.pipeline.Omni') as provider:
                journal = LocalJournal(Path(directory)/'journal')
                if status:
                    journal.save(hybrid.voice_cache_name(plan, 'test-voice'), {'voice': {'status': status}})
                with self.assertRaisesRegex(PipelineError, 'Import the original voice package'):
                    hybrid.make(plan, 'job', {}, journal, Path(directory), 'test-model', 'test-voice')
                prepare.assert_not_called()
                synthesize.assert_not_called()
                provider.assert_not_called()

    def test_missing_ffmpeg_or_ffprobe_blocks_voice_request(self):
        for missing in ['ffmpeg', 'ffprobe']:
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as directory, \
                    patch('automation.hybrid.shutil.which',
                          side_effect=lambda command: None if command == missing else '/test/bin/' + command), \
                    patch('automation.hybrid.voice_result') as voice:
                with self.assertRaisesRegex(PipelineError, 'Install ffmpeg and ffprobe'):
                    hybrid.prepare(plan_fixture(), 'test-voice', LocalJournal(Path(directory)/'journal'),
                                   Path(directory)/'output')
                voice.assert_not_called()
                self.assertFalse((Path(directory)/'output').exists())


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg tools required')
class AvatarPreparationTests(unittest.TestCase):
    def test_existing_clone_exports_exact_four_second_audio_and_hashes_without_network(self):
        plan = pipeline.load_plan(pipeline.ROOT/'plans/ek-gida-baslangic.json')
        plan['format'] = 'hybrid-v1'
        plan['shots'] = plan_fixture()['shots']
        for index, asset_id in [(0, 'doctor-opening'), (8, 'doctor-middle')]:
            plan['shots'][index] = {'kind': 'avatar', 'asset_id': asset_id, 'duration': 4}
        self.assertEqual(hybrid.validate(plan)['avatar_seconds'], 8)
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {}, clear=True), \
                patch('automation.pipeline.synthesize', side_effect=AssertionError('Unexpected TTS')) as synthesize, \
                patch('requests.sessions.Session.request', side_effect=AssertionError('Unexpected network')) as network:
            output = Path(directory)/'prepared'
            audio, alignment, audio_hash = hybrid.prepare(
                plan, pipeline.VOICE_ID, LocalJournal(Path(directory)/'journal'), output)
            self.assertEqual(audio.read_bytes(), (pipeline.ROOT/plan['prepared_voice']['audio']).read_bytes())
            self.assertEqual(audio_hash, hashlib.sha256(audio.read_bytes()).hexdigest())
            self.assertTrue(alignment['characters'])
            alignment_path = output/'alignment.json'
            self.assertEqual(json.loads(alignment_path.read_text()), alignment)
            manifest = json.loads((output/'voice-manifest.json').read_text())
            self.assertEqual(manifest['voice_id'], pipeline.VOICE_ID)
            self.assertEqual(manifest['audio_sha256'], audio_hash)
            self.assertEqual(manifest['narration_sha256'], hashlib.sha256(plan['narration'].encode()).hexdigest())
            self.assertEqual(manifest['alignment_sha256'], hashlib.sha256(alignment_path.read_bytes()).hexdigest())
            requests = json.loads((output/'avatar-requests.json').read_text())
            self.assertEqual([request['timeline_start'] for request in requests], [0, 32])
            for request, asset_id in zip(requests, ['doctor-opening', 'doctor-middle']):
                self.assertEqual(request['asset_id'], asset_id)
                self.assertEqual(request['duration'], 4)
                self.assertEqual(request['audio_sha256'], audio_hash)
                self.assertEqual(request['voice_id'], pipeline.VOICE_ID)
                self.assertEqual(request['narration_sha256'], hashlib.sha256(plan['narration'].encode()).hexdigest())
                self.assertTrue(request['portrait_required'])
                exported = output/request['audio_file']
                self.assertEqual(request['slice_sha256'], hashlib.sha256(exported.read_bytes()).hexdigest())
                self.assertAlmostEqual(float(probe(exported)['format']['duration']), 4, places=4)
                with wave.open(str(exported), 'rb') as wav:
                    self.assertEqual(wav.getframerate(), 48000)
                    self.assertEqual(wav.getnframes(), 4 * 48000)
                    if request['timeline_start'] == 0:
                        silence = wav.readframes(12000)
                        self.assertEqual(silence, b'\x00' * len(silence))
            synthesize.assert_not_called()
            network.assert_not_called()


if __name__ == '__main__':
    unittest.main()
