import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from automation import stock
from automation.state import PipelineError


def candidate():
    return {'asset_id': 'pexels-123', 'provider': 'pexels', 'provider_id': 123,
            'source_url': 'https://www.pexels.com/video/soft-food-123/',
            'creator': {'name': 'Example Creator', 'url': 'https://www.pexels.com/@example/'},
            'license_url': stock.LICENSE, 'duration': 8, 'width': 1080, 'height': 1920,
            'minimum_duration': 4, 'download_url': 'https://videos.pexels.com/video-files/123/clip.mp4',
            'requires_review': True}


def response(status=200, *, body=None, chunks=None, headers=None):
    value = Mock(status_code=status)
    value.json.return_value = body
    value.headers = headers or {}
    value.iter_content.return_value = iter(chunks or [b'example-moving-video'])
    return value


def client_with(value):
    client = requests.Session()
    client.request = Mock(return_value=value)
    return client


def search_video():
    return {'id': 123, 'url': candidate()['source_url'], 'duration': 8,
            'user': candidate()['creator'], 'video_files': [
                {'file_type': 'video/mp4', 'width': 2160, 'height': 3840,
                 'link': 'https://videos.pexels.com/video-files/123/4k.mp4'},
                {'file_type': 'video/mp4', 'width': 720, 'height': 1280,
                 'link': 'https://videos.pexels.com/video-files/123/720p.mp4'},
                {'file_type': 'video/mp4', 'width': 1080, 'height': 1920,
                 'link': candidate()['download_url']}]}


class PexelsSearchTests(unittest.TestCase):
    def test_missing_key_stops_before_http(self):
        with patch.dict(os.environ, {}, clear=True), patch('automation.stock.session') as factory:
            with self.assertRaisesRegex(PipelineError, 'PEXELS_API_KEY'):
                stock.search_clips('soft food')
            factory.assert_not_called()

    def test_search_bounds_portrait_results_and_preserves_attribution(self):
        too_short = {**search_video(), 'duration': 2}
        landscape = copy.deepcopy(search_video())
        for item in landscape['video_files']:
            item['width'], item['height'] = item['height'], item['width']
        client = client_with(response(body={'videos': [too_short, landscape, search_video()]}))
        with patch.dict(os.environ, {'PEXELS_API_KEY': 'test-placeholder'}), \
                patch('automation.stock.session', return_value=client):
            found = stock.search_clips('soft food')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0], candidate())
        call = client.request.call_args
        self.assertEqual(call.args[1], stock.API)
        self.assertEqual(call.kwargs['params']['orientation'], 'portrait')
        self.assertLessEqual(call.kwargs['params']['per_page'], 10)
        self.assertFalse(call.kwargs['allow_redirects'])
        self.assertEqual(call.kwargs['headers'], {'Authorization': 'test-placeholder'})

    def test_unapproved_download_host_is_not_offered(self):
        item = search_video()
        for file in item['video_files']:
            file['link'] = 'https://videos.pexels.com.attacker.example/video.mp4'
        client = client_with(response(body={'videos': [item]}))
        with patch.dict(os.environ, {'PEXELS_API_KEY': 'test-placeholder'}), \
                patch('automation.stock.session', return_value=client):
            self.assertEqual(stock.search_clips('soft food'), [])


class PexelsImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'automation'
        self.metadata = {'format': {'duration': '8'}, 'streams': [
            {'codec_type': 'video', 'duration': '8', 'width': 1080, 'height': 1920, 'nb_frames': '192'}]}
        for target in ['automation.media.probe', 'automation.stock.probe']:
            check = patch(target, return_value=self.metadata)
            check.start()
            self.addCleanup(check.stop)

    def test_cdn_never_receives_search_authorization_and_catalog_preserves_source(self):
        api = client_with(response(body={'videos': [search_video()]}))
        cdn = client_with(response(headers={'Content-Type': 'video/mp4'}))
        with patch.dict(os.environ, {'PEXELS_API_KEY': 'test-placeholder'}), \
                patch('automation.stock.session', side_effect=[api, cdn]):
            found = stock.search_clips('soft food')
            asset_id = stock.import_clip(found[0], root=self.root)
        self.assertEqual(asset_id, 'pexels-123')
        self.assertNotIn('Authorization', cdn.headers)
        self.assertIsNone(cdn.auth)
        self.assertNotIn('headers', cdn.request.call_args.kwargs)
        self.assertFalse(cdn.request.call_args.kwargs['allow_redirects'])
        self.assertTrue(cdn.request.call_args.kwargs['stream'])
        entry = json.loads((self.root/'media/catalog.json').read_text())['assets'][asset_id]
        self.assertEqual(entry['source_url'], candidate()['source_url'])
        self.assertEqual(entry['creator'], candidate()['creator'])
        self.assertEqual(entry['provider'], 'pexels')
        self.assertEqual(entry['license_url'], stock.LICENSE)
        self.assertIn('Example Creator', entry['license'])
        self.assertTrue(entry['requires_review'])

    def test_existing_verified_asset_is_reused_without_redownload(self):
        client = client_with(response())
        with patch('automation.stock.session', return_value=client) as factory:
            identifier = stock.import_clip(candidate(), root=self.root)
            factory.reset_mock()
            self.assertEqual(stock.import_clip(candidate(), root=self.root), identifier)
            factory.assert_not_called()
            target = self.root/'media/library/pexels-123.mp4'
            target.write_bytes(b'changed-file')
            with self.assertRaisesRegex(PipelineError, 'missing or changed'):
                stock.import_clip(candidate(), root=self.root)
            factory.assert_not_called()

    def test_invalid_or_private_download_urls_fail_before_network(self):
        urls = ['http://videos.pexels.com/x.mp4', 'https://127.0.0.1/x.mp4',
                'https://[::1]/x.mp4', 'https://10.0.0.1/x.mp4',
                'https://videos.pexels.com.attacker.example/x.mp4',
                'https://name:password@videos.pexels.com/x.mp4',
                'https://videos.pexels.com:444/x.mp4', 'https://videos.pexels.com/page.html']
        with patch('automation.stock.session') as factory:
            for url in urls:
                with self.subTest(url=url), self.assertRaises(PipelineError):
                    stock.import_clip({**candidate(), 'download_url': url}, root=self.root)
            factory.assert_not_called()

    def test_redirect_is_not_followed(self):
        client = client_with(response(status=302, headers={'Location': 'http://127.0.0.1/private'}))
        with patch('automation.stock.session', return_value=client):
            with self.assertRaisesRegex(PipelineError, 'HTTP 302'):
                stock.import_clip(candidate(), root=self.root)
        self.assertEqual(client.request.call_count, 1)
        self.assertFalse(client.request.call_args.kwargs['allow_redirects'])
        self.assertFalse((self.root/'media/catalog.json').exists())

    def test_stream_limit_rejects_oversized_file_without_catalog_import(self):
        client = client_with(response(chunks=[b'123456', b'789012']))
        with patch('automation.stock.session', return_value=client), patch('automation.stock.MAX_BYTES', 10):
            with self.assertRaisesRegex(PipelineError, '100 MB limit'):
                stock.import_clip(candidate(), root=self.root)
        self.assertFalse((self.root/'media/catalog.json').exists())

    def test_declared_size_limit_stops_before_reading_body(self):
        data = response(headers={'Content-Length': str(stock.MAX_BYTES+1)})
        client = client_with(data)
        with patch('automation.stock.session', return_value=client):
            with self.assertRaisesRegex(PipelineError, '100 MB limit'):
                stock.import_clip(candidate(), root=self.root)
        data.iter_content.assert_not_called()

    def test_short_download_is_not_imported(self):
        self.metadata['streams'][0]['duration'] = '2'
        client = client_with(response())
        with patch('automation.stock.session', return_value=client):
            with self.assertRaisesRegex(PipelineError, 'portrait interval'):
                stock.import_clip(candidate(), root=self.root)
        self.assertFalse((self.root/'media/catalog.json').exists())

    def test_source_identity_and_license_cannot_be_fabricated(self):
        with patch('automation.stock.session') as factory:
            for change in [{'provider_id': 999}, {'source_url': 'https://example.com/video/123/'},
                           {'license_url': 'https://example.com/license'}, {'creator': {}}]:
                with self.subTest(change=change), self.assertRaises(PipelineError):
                    stock.import_clip({**candidate(), **change}, root=self.root)
            factory.assert_not_called()


if __name__ == '__main__':
    unittest.main()
