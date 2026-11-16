import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from automation.restore_media import restore_asset
from automation.state import PipelineError


class RestoreMediaTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.content = b'fixture-video-bytes'
        self.asset = {'kind': 'stock', 'provider': 'pexels', 'source_duration': 12,
                      'path': 'media/library/pexels-123.mp4',
                      'sha256': hashlib.sha256(self.content).hexdigest(),
                      'download_url': 'https://videos.pexels.com/video-files/123/video.mp4'}
        self.probe = patch('automation.restore_media.probe', return_value={
            'streams': [{'codec_type': 'video', 'duration': '12'}], 'format': {'duration': '12'}})
        self.probe.start()
        self.addCleanup(self.probe.stop)

    def client(self, status=200, content=None):
        client, response = Mock(), Mock()
        response.status_code = status
        response.iter_content.return_value = [self.content if content is None else content]
        client.get.return_value = response
        return client, response

    def test_exact_download_installed_without_credentials_or_redirects(self):
        client, response = self.client()
        with patch('automation.restore_media.session', return_value=client):
            path = restore_asset('pexels-123', self.asset, self.root)
        self.assertEqual(path.read_bytes(), self.content)
        client.get.assert_called_once_with(self.asset['download_url'], timeout=120, stream=True, allow_redirects=False)
        response.close.assert_called_once()
        client.close.assert_called_once()

    def test_valid_existing_file_needs_no_network(self):
        path = self.root/self.asset['path']
        path.parent.mkdir(parents=True)
        path.write_bytes(self.content)
        with patch('automation.restore_media.session') as network:
            self.assertEqual(restore_asset('pexels-123', self.asset, self.root), path)
        network.assert_not_called()

    def test_hash_mismatch_never_installs_or_changes_catalog(self):
        client, _ = self.client(content=b'changed-provider-file')
        original = dict(self.asset)
        with patch('automation.restore_media.session', return_value=client):
            with self.assertRaisesRegex(PipelineError, 'differs'):
                restore_asset('pexels-123', self.asset, self.root)
        self.assertFalse((self.root/self.asset['path']).exists())
        self.assertEqual(self.asset, original)
        self.assertEqual(list((self.root/'media/library').iterdir()), [])

    def test_existing_corrupted_file_preserved_without_redownload(self):
        path = self.root/self.asset['path']
        path.parent.mkdir(parents=True)
        path.write_bytes(b'corrupted')
        with patch('automation.restore_media.session') as network:
            with self.assertRaises(PipelineError):
                restore_asset('pexels-123', self.asset, self.root)
        network.assert_not_called()
        self.assertEqual(path.read_bytes(), b'corrupted')

    def test_redirect_is_not_followed(self):
        client, response = self.client(status=302)
        with patch('automation.restore_media.session', return_value=client):
            with self.assertRaisesRegex(PipelineError, '302'):
                restore_asset('pexels-123', self.asset, self.root)
        response.iter_content.assert_not_called()
        response.close.assert_called_once()

    def test_untrusted_url_and_path_rejected_before_download(self):
        for field, value in [('download_url', 'https://evil.example/video.mp4'),
                             ('download_url', 'https://user:secret@videos.pexels.com/video.mp4'),
                             ('path', 'media/../../outside.mp4')]:
            asset = {**self.asset, field: value}
            with self.subTest(field=field), patch('automation.restore_media.session') as network:
                with self.assertRaises(PipelineError):
                    restore_asset('pexels-123', asset, self.root)
                network.assert_not_called()

    def test_short_video_is_not_installed_even_when_hash_matches(self):
        client, _ = self.client()
        with patch('automation.restore_media.session', return_value=client), patch(
                'automation.restore_media.probe', return_value={'streams': [{'codec_type': 'video', 'duration': '3'}]}):
            with self.assertRaisesRegex(PipelineError, 'duration'):
                restore_asset('pexels-123', self.asset, self.root)
        self.assertFalse((self.root/self.asset['path']).exists())


if __name__ == '__main__':
    unittest.main()
