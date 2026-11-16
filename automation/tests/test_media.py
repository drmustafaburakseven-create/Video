import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from automation.media import import_media
from automation.state import PipelineError


class MediaImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'automation'
        self.source = Path(self.temp.name)/'footage.mp4'
        self.source.write_bytes(b'local moving footage')
        self.metadata = {'format': {'duration': '8'},
                         'streams': [{'codec_type': 'video', 'duration': '8', 'nb_frames': '192'}]}
        self.probe = patch('automation.media.probe', return_value=self.metadata)
        self.probe.start()
        self.addCleanup(self.probe.stop)

    def stock(self, **kwargs):
        return import_media(self.source, 'kitchen-preparation', 'stock', root=self.root,
                            source_url='https://example.org/stock/kitchen', license_text='CC0', **kwargs)

    def avatar_requests(self, duration=5):
        request = {'asset_id': 'doctor-intro', 'timeline_start': 12, 'duration': duration,
                   'narration_sha256': 'a'*64, 'audio_sha256': 'b'*64,
                   'slice_sha256': 'c'*64, 'portrait_required': True}
        path = Path(self.temp.name)/'avatar-requests.json'
        path.write_text(json.dumps([request]))
        return path, request

    def test_import_attribution_hash_and_idempotent_catalog(self):
        entry = self.stock()
        self.assertEqual((self.root/entry['path']).read_bytes(), self.source.read_bytes())
        self.assertEqual(entry['sha256'], hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(entry['license'], 'CC0')
        self.assertEqual(self.stock(), entry)
        catalog = json.loads((self.root/'media/catalog.json').read_text())
        self.assertEqual(catalog, {'version': 1, 'assets': {'kitchen-preparation': entry}})

    def test_different_footage_cannot_replace_existing_id(self):
        original = self.stock()
        self.source.write_bytes(b'other video')
        with self.assertRaisesRegex(PipelineError, 'different footage'):
            self.stock()
        self.assertEqual((self.root/original['path']).read_bytes(), b'local moving footage')

    def test_avatar_preserves_exact_prepared_audio_identity(self):
        requests, expected = self.avatar_requests()
        entry = import_media(self.source, 'doctor-intro', 'avatar', avatar_requests=requests, root=self.root)
        for key in ('timeline_start', 'duration', 'narration_sha256', 'audio_sha256', 'slice_sha256'):
            self.assertEqual(entry[key], expected[key])
        self.assertEqual(entry['source_duration'], 8)
        self.assertNotIn('provider', entry)
        self.assertNotIn('portrait', entry)

    def test_avatar_must_cover_requested_speech(self):
        requests, _ = self.avatar_requests(duration=9)
        with self.assertRaisesRegex(PipelineError, 'shorter'):
            import_media(self.source, 'doctor-intro', 'avatar', avatar_requests=requests, root=self.root)
        self.assertFalse((self.root/'media/catalog.json').exists())

    def test_avatar_requires_matching_asset_id(self):
        requests, _ = self.avatar_requests()
        with self.assertRaisesRegex(PipelineError, 'matching asset_id'):
            import_media(self.source, 'doctor-other', 'avatar', avatar_requests=requests, root=self.root)

    def test_stock_requires_https_and_license(self):
        for url, license_text in [('http://example.org/clip', 'CC0'), ('https://example.org', '')]:
            with self.subTest(url=url), self.assertRaisesRegex(PipelineError, 'HTTPS source URL'):
                import_media(self.source, 'clip', 'stock', source_url=url,
                             license_text=license_text, root=self.root)

    def test_no_video_stream_and_portrait_are_rejected(self):
        self.metadata['streams'] = [{'codec_type': 'audio'}]
        with self.assertRaisesRegex(PipelineError, 'no video stream'):
            import_media(self.source, 'clip', 'generated', root=self.root)
        portrait = self.source.with_suffix('.jpg')
        portrait.write_bytes(b'portrait')
        with self.assertRaisesRegex(PipelineError, 'still image'):
            import_media(portrait, 'clip', 'generated', root=self.root)

    def test_asset_id_cannot_escape_library(self):
        with self.assertRaisesRegex(PipelineError, 'Media ID'):
            import_media(self.source, '../../outside', 'generated', root=self.root)

    def test_symlinked_library_catalog_and_destination_are_rejected(self):
        for target in ('library', 'catalog.json', 'library/kitchen-preparation.mp4'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)/'automation'
                media = root/'media'
                media.mkdir(parents=True)
                outside = Path(temporary)/'outside'
                outside.mkdir()
                symlink = media/target
                symlink.parent.mkdir(parents=True, exist_ok=True)
                symlink.symlink_to(outside)
                with self.assertRaisesRegex(PipelineError, 'symbolic links?'):
                    import_media(self.source, 'kitchen-preparation', 'generated', root=root)
                self.assertEqual(list(outside.iterdir()), [])

    def test_failed_atomic_catalog_replace_preserves_previous_catalog(self):
        original = self.stock()
        path = self.root/'media/catalog.json'
        before = path.read_bytes()
        with patch('automation.media.os.replace', side_effect=OSError('simulated disk failure')):
            with self.assertRaises(OSError):
                import_media(self.source, 'second-clip', 'generated', root=self.root)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(json.loads(before)['assets']['kitchen-preparation'], original)
        self.assertEqual(list((self.root/'media').glob('.catalog-*.json')), [])


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class NativeMediaImportTests(unittest.TestCase):
    def test_ffprobe_accepts_real_moving_video(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/'moving.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            'testsrc2=size=90x160:rate=24:duration=1', '-c:v', 'libx264',
                            '-preset', 'ultrafast', '-threads', '1', str(source)], check=True)
            entry = import_media(source, 'test-motion', 'generated', root=root/'automation')
            self.assertAlmostEqual(entry['duration'], 1)
            self.assertEqual((root/'automation'/entry['path']).read_bytes(), source.read_bytes())


if __name__ == '__main__':
    unittest.main()
