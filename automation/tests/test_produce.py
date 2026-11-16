from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from automation import hybrid, pipeline, produce
from automation.state import LocalJournal, PipelineError


VIDEO_META = {'format': {'duration': '8'}, 'streams': [
    {'codec_type': 'video', 'duration': '8', 'nb_frames': '192', 'width': 720, 'height': 1280}]}


class ProduceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'automation'
        for folder in ['drafts', 'plans', 'media/library']:
            (self.root/folder).mkdir(parents=True)
        self.output = Path(self.temp.name)/'output'
        self.portrait = Path(self.temp.name)/'portrait.png'
        # A plain synthetic test image, never a user-facing doctor avatar.
        Image.new('RGB', (320, 480), 'navy').save(self.portrait)
        self.plan = {'id': 'test-reel', 'title': 'Test', 'format': 'hybrid-v1',
                     'duration_seconds': 60, 'enabled': False, 'narration': 'Anlatım. ' * 60,
                     'sources': ['https://www.cdc.gov/'], 'shots': [
                         {'kind': 'avatar' if i in [0, 14] else 'stock',
                          'asset_id': 'old-doctor' if i in [0, 14] else 'stock', 'duration': 4}
                         for i in range(15)]}
        self.plan_path = self.root/'drafts/test-reel.json'
        self.plan_path.write_text(json.dumps(self.plan))
        clip = self.root/'media/library/stock.mp4'
        clip.write_bytes(b'test-stock')
        self.catalog = {'version': 1, 'assets': {'stock': {
            'path': 'media/library/stock.mp4', 'kind': 'stock',
            'sha256': hashlib.sha256(clip.read_bytes()).hexdigest(),
            'source_url': 'https://example.org/licensed-stock', 'license': 'Test license'}}}
        self._write_catalog()
        self.addCleanup(patch.stopall)
        patch.object(produce, 'ROOT', self.root).start()
        patch.object(hybrid, 'probe', return_value=VIDEO_META).start()
        patch.object(produce.media, 'probe', return_value=VIDEO_META).start()
        patch.object(pipeline, 'job_name', side_effect=self._job_name).start()
        patch.dict(produce.os.environ, {}, clear=True).start()

    def _write_catalog(self):
        (self.root/'media/catalog.json').write_text(json.dumps(self.catalog))

    def _job_name(self, plan, model, voice, director):
        fingerprint = hybrid.fingerprint(plan, self.root)
        return plan['id']+'-'+fingerprint[:12]

    def _prepare(self, plan, voice, journal, output):
        output.mkdir(parents=True, exist_ok=True)
        audio = output/'voice.mp3'
        audio.write_bytes(b'original-take')
        voice_hash = hashlib.sha256(audio.read_bytes()).hexdigest()
        journal.save(hybrid.voice_cache_name(plan, voice), {'voice': {
            'status': 'received', 'response': {'audio_base64': 'b3JpZ2luYWwtdGFrZQ==', 'alignment': {}}}})
        requests = []
        start = 0
        for i, shot in enumerate(plan['shots']):
            if shot['kind'] == 'avatar':
                wav = output/f'avatar-{i+1:02}-speech.wav'
                wav.write_bytes(f'exact speech {start}'.encode())
                requests.append({'asset_id': shot['asset_id'], 'audio_file': wav.name,
                                 'timeline_start': start, 'duration': shot['duration'],
                                 'voice_id': voice, 'audio_sha256': voice_hash,
                                 'narration_sha256': hashlib.sha256(plan['narration'].encode()).hexdigest(),
                                 'slice_sha256': hashlib.sha256(wav.read_bytes()).hexdigest()})
            start += shot['duration']
        (output/'avatar-requests.json').write_text(json.dumps(requests))
        return audio, {}, voice_hash

    def _avatar(self, picture, speech, request, journal, output):
        self.assertTrue(picture.is_file())
        self.assertEqual(hashlib.sha256(speech.read_bytes()).hexdigest(), request['slice_sha256'])
        output.write_bytes(('avatar '+request['asset_id']).encode())
        return output

    def _make(self, plan, name, state, journal, output, model, voice):
        # The compositor must see all avatars and the very same saved take.
        hybrid.resolve(plan, self.root)
        saved = hybrid.voice_result(plan, voice, journal)
        self.assertEqual(saved['audio_base64'], 'b3JpZ2luYWwtdGFrZQ==')
        output.mkdir(parents=True, exist_ok=True)
        result = output/'video.mp4'
        result.write_bytes(b'composed test video')
        journal.save(name, {'complete': True, 'video_sha256': hashlib.sha256(result.read_bytes()).hexdigest()})

    def test_missing_stock_stops_before_tts_or_provider(self):
        self.catalog['assets'] = {}
        self._write_catalog()
        with patch.object(hybrid, 'prepare') as prepare, \
                patch.object(produce.avatar_fal, 'ensure_available') as provider:
            with self.assertRaisesRegex(PipelineError, 'Missing reusable media'):
                produce.produce(self.plan_path, self.portrait, 'fal', self.output)
        prepare.assert_not_called()
        provider.assert_not_called()

    def test_invalid_portrait_stops_before_any_generation(self):
        self.portrait.write_bytes(b'not an image')
        with patch.object(hybrid, 'prepare') as prepare:
            with self.assertRaisesRegex(PipelineError, 'PNG/JPEG'):
                produce.produce(self.plan_path, self.portrait, 'fal', self.output)
        prepare.assert_not_called()

    def test_real_image_dimensions_are_verified(self):
        Image.new('RGB', (100, 100)).save(self.portrait)
        with self.assertRaisesRegex(PipelineError, '256 pixels'):
            produce._portrait(self.portrait)
        Image.new('RGB', (300, 400)).save(self.portrait)
        data, digest, extension = produce._portrait(self.portrait)
        self.assertEqual(digest, hashlib.sha256(data).hexdigest())
        self.assertEqual(extension, '.png')

    def test_provider_unavailable_stops_before_voice(self):
        with patch.object(hybrid, 'prepare') as prepare, \
                patch.object(produce.avatar, 'ensure_available', side_effect=PipelineError('Pro required')):
            with self.assertRaisesRegex(PipelineError, 'Pro required'):
                produce.produce('test-reel.json', self.portrait, 'elevenlabs', self.output)
        prepare.assert_not_called()

    def test_plan_path_cannot_escape_or_follow_a_symlink(self):
        external = Path(self.temp.name)/'external.json'
        external.write_text(self.plan_path.read_text())
        with self.assertRaisesRegex(PipelineError, 'stay inside'):
            produce._plan_path(external)
        link = self.root/'drafts/link.json'
        link.symlink_to(external)
        with self.assertRaisesRegex(PipelineError, 'stay inside'):
            produce._plan_path(link)

    def test_new_avatar_ids_bind_face_narration_voice_provider_and_timeline(self):
        args = (self.plan, 'a'*64, 'voice', 'fal')
        one = produce._avatar_ids(*args)['shots'][0]['asset_id']
        for plan, picture, voice, provider in [
                (self.plan, 'b'*64, 'voice', 'fal'),
                ({**self.plan, 'narration': self.plan['narration']+' different'}, 'a'*64, 'voice', 'fal'),
                (self.plan, 'a'*64, 'other', 'fal'), (self.plan, 'a'*64, 'voice', 'elevenlabs')]:
            self.assertNotEqual(one, produce._avatar_ids(plan, picture, voice, provider)['shots'][0]['asset_id'])
        self.assertEqual(self.plan['shots'][0]['asset_id'], 'old-doctor')

    def test_complete_production_imports_two_avatars_then_reuses_without_new_calls(self):
        with patch.object(hybrid, 'prepare', side_effect=self._prepare) as prepare, \
                patch.object(hybrid, 'make', side_effect=self._make) as make, \
                patch.object(produce.avatar_fal, 'ensure_available', return_value=True) as available, \
                patch.object(produce.avatar_fal, 'create_avatar', side_effect=self._avatar) as create, \
                patch.object(pipeline, 'synthesize', side_effect=AssertionError('No second TTS')):
            first = produce.produce('test-reel.json', self.portrait, 'fal', self.output)
            second = produce.produce(self.plan_path, self.portrait, 'fal', self.output)
        self.assertEqual(first, second)
        self.assertTrue(first.is_file())
        self.assertEqual(create.call_count, 2)
        self.assertEqual(available.call_count, 1)
        self.assertEqual(prepare.call_count, 1)
        self.assertEqual(make.call_count, 1)
        assets = hybrid.catalog(self.root)
        self.assertEqual(len(assets), 3)
        self.assertEqual({a['timeline_start'] for a in assets.values() if a['kind']=='avatar'}, {0, 56})
        self.assertEqual(pipeline.load_plan(self.plan_path)['shots'][0]['asset_id'], 'old-doctor')

    def test_existing_avatars_without_original_voice_cannot_trigger_new_tts(self):
        with patch.object(hybrid, 'prepare', side_effect=self._prepare), \
                patch.object(hybrid, 'make', side_effect=self._make), \
                patch.object(produce.avatar_fal, 'ensure_available', return_value=True), \
                patch.object(produce.avatar_fal, 'create_avatar', side_effect=self._avatar):
            produce.produce(self.plan_path, self.portrait, 'fal', self.output)
        with patch.object(hybrid, 'prepare') as prepare:
            with self.assertRaisesRegex(PipelineError, 'original narration'):
                produce.produce(self.plan_path, self.portrait, 'fal', self.output/'fresh-runner',
                                journal=LocalJournal(self.output/'fresh-journal'))
        prepare.assert_not_called()

    def test_missing_gemini_key_stops_before_avatar_or_tts(self):
        plan = deepcopy(self.plan)
        plan['shots'][1] = {'kind': 'generated', 'duration': 4, 'generation_id': 'new-clip',
                            'generation_seconds': 8, 'prompt': 'A clear moving scene showing a hand mashing fully cooked food.'}
        self.plan_path.write_text(json.dumps(plan))
        with patch.object(hybrid, 'prepare') as prepare, \
                patch.object(produce.avatar_fal, 'ensure_available') as provider:
            with self.assertRaisesRegex(PipelineError, 'GEMINI_API_KEY'):
                produce.produce(self.plan_path, self.portrait, 'fal', self.output)
        prepare.assert_not_called()
        provider.assert_not_called()

    def test_nonblocking_lock_prevents_a_second_production(self):
        with produce._production_lock(self.output):
            with patch.object(hybrid, 'prepare') as prepare:
                with self.assertRaisesRegex(PipelineError, 'Another production'):
                    produce.produce(self.plan_path, self.portrait, 'fal', self.output)
                prepare.assert_not_called()


if __name__ == '__main__':
    unittest.main()
