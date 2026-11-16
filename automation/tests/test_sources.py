"""Bounded official-source retrieval and cache checks without external requests."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from automation import sources
from automation.state import PipelineError

URL = 'https://www.cdc.gov/infant-toddler-nutrition/example'
NOW = datetime(2026, 11, 16, 9, tzinfo=timezone.utc)


def page(text='Safe food advice for parents. ' * 20):
    return ('<html><head><style>hidden-style</style></head><body><header>outside-main</header>'
            '<main><nav>hidden-menu</nav><p>'+text+'</p><script>hidden-script</script>'
            '<footer>hidden-footer</footer></main><p>outside-after-main</p></body></html>').encode()


def response(body=None, status=200, headers=None):
    item = Mock(status_code=status, headers=headers if headers is not None else {'Content-Type': 'text/html; charset=utf-8'})
    item.iter_content.return_value = [page() if body is None else body]
    return item


class SourceTextTests(unittest.TestCase):
    def test_main_text_excludes_navigation_scripts_styles_and_outer_chrome(self):
        parser = sources.MainText()
        parser.feed(page('Useful clinical sentence. '*20).decode())
        text = parser.text()
        self.assertIn('Useful clinical sentence.', text)
        for marker in ['hidden-menu', 'hidden-script', 'hidden-style', 'hidden-footer',
                       'outside-main', 'outside-after-main']:
            self.assertNotIn(marker, text)

    def test_fallback_for_page_without_main_still_removes_script_and_navigation(self):
        parser = sources.MainText()
        parser.feed('<nav>menu</nav><article>Clinical guidance</article><script>private-js</script>')
        self.assertEqual(parser.text(), 'Clinical guidance')


class SourceFetchTests(unittest.TestCase):
    def test_unapproved_origin_is_rejected_before_client_creation(self):
        with tempfile.TemporaryDirectory() as cache, patch('automation.sources.session') as client:
            for url in ['http://www.cdc.gov/page', 'https://www.cdc.gov.evil.example/page',
                        'https://user:secret@www.cdc.gov/page', 'https://www.cdc.gov:444/page']:
                with self.subTest(url=url), self.assertRaisesRegex(PipelineError, 'official HTTPS'):
                    sources.fetch_source(url, cache, now=NOW)
            client.assert_not_called()

    def test_redirect_outside_official_hosts_is_not_followed(self):
        redirect = response(status=302, headers={'Location': 'https://untrusted.example/page'})
        with tempfile.TemporaryDirectory() as cache, patch('automation.sources.session') as factory:
            client = factory.return_value
            client.get.return_value = redirect
            with self.assertRaisesRegex(PipelineError, 'official HTTPS'):
                sources.fetch_source(URL, cache, now=NOW)
            client.get.assert_called_once()
            redirect.close.assert_called_once()
            self.assertEqual(list(Path(cache).glob('*.json')), [])

    def test_relative_official_redirect_preserves_original_and_final_urls(self):
        redirect = response(status=301, headers={'Location': '/updated-guidance'})
        final = response()
        with tempfile.TemporaryDirectory() as cache, patch('automation.sources.session') as factory:
            factory.return_value.get.side_effect = [redirect, final]
            saved = sources.fetch_source(URL, cache, now=NOW)
        self.assertEqual(saved['url'], URL)
        self.assertEqual(saved['final_url'], 'https://www.cdc.gov/updated-guidance')
        self.assertEqual(saved['sha256'], hashlib.sha256(saved['text'].encode()).hexdigest())
        self.assertEqual(saved['retrieved_at'], NOW.isoformat())
        self.assertTrue(all(call.kwargs['allow_redirects'] is False
                            for call in factory.return_value.get.call_args_list))
        redirect.close.assert_called_once()
        final.close.assert_called_once()

    def test_valid_cache_prevents_network_and_corrupted_hash_triggers_refresh(self):
        with tempfile.TemporaryDirectory() as cache, patch('automation.sources.session') as factory:
            factory.return_value.get.return_value = response()
            first = sources.fetch_source(URL, cache, now=NOW)
            with patch('automation.sources.session', side_effect=AssertionError('Unexpected network')):
                cached = sources.fetch_source(URL, cache, now=NOW+timedelta(days=1))
            self.assertEqual(first, cached)
            path = next(Path(cache).glob('*.json'))
            corrupted = json.loads(path.read_text())
            corrupted['text'] += ' altered'
            path.write_text(json.dumps(corrupted))
            refreshed = sources.fetch_source(URL, cache, now=NOW+timedelta(days=1))
            self.assertEqual(factory.return_value.get.call_count, 2)
            self.assertNotIn(' altered', refreshed['text'])

    def test_expired_future_or_explicit_refresh_cache_is_not_reused(self):
        with tempfile.TemporaryDirectory() as cache, patch('automation.sources.session') as factory:
            factory.return_value.get.return_value = response()
            sources.fetch_source(URL, cache, now=NOW)
            sources.fetch_source(URL, cache, now=NOW+timedelta(days=7))
            self.assertEqual(factory.return_value.get.call_count, 2)
            # The previous response is now dated in the future relative to this call.
            sources.fetch_source(URL, cache, now=NOW)
            sources.fetch_source(URL, cache, now=NOW+timedelta(minutes=1), refresh=True)
            self.assertEqual(factory.return_value.get.call_count, 4)

    def test_oversized_non_html_and_empty_pages_are_closed_without_caching(self):
        cases = [response(b'x'*2_000_001), response(headers={'Content-Type': 'application/pdf'}),
                 response(b'<main>Too little text.</main>')]
        for item in cases:
            with self.subTest(headers=item.headers), tempfile.TemporaryDirectory() as cache, \
                    patch('automation.sources.session') as factory:
                factory.return_value.get.return_value = item
                with self.assertRaises(PipelineError):
                    sources.fetch_source(URL, cache, now=NOW)
                item.close.assert_called_once()
                self.assertEqual(list(Path(cache).glob('*.json')), [])

    def test_redirect_limit_and_http_failure_do_not_cache_or_retry(self):
        with tempfile.TemporaryDirectory() as cache, patch('automation.sources.session') as factory:
            redirects = [response(status=302, headers={'Location': f'/redirect-{i}'}) for i in range(4)]
            factory.return_value.get.side_effect = redirects
            with self.assertRaisesRegex(PipelineError, 'too many times'):
                sources.fetch_source(URL, cache, now=NOW)
            self.assertEqual(factory.return_value.get.call_count, 4)
            self.assertTrue(all(item.close.call_count == 1 for item in redirects))
        denied = response(status=429)
        with tempfile.TemporaryDirectory() as cache, patch('automation.sources.session') as factory:
            factory.return_value.get.return_value = denied
            with self.assertRaisesRegex(PipelineError, 'HTTP 429'):
                sources.fetch_source(URL, cache, now=NOW)
            factory.return_value.get.assert_called_once()
            denied.close.assert_called_once()

    def test_duplicate_sources_are_fetched_once_in_deterministic_order(self):
        urls = ['https://www.nhs.uk/b', URL, URL]
        with patch('automation.sources.fetch_source', side_effect=lambda url, cache: {'url': url}) as fetch:
            result = sources.fetch_sources(urls, '/tmp/not-used')
        self.assertEqual(list(result), sorted(set(urls)))
        self.assertEqual(fetch.call_count, 2)


if __name__ == '__main__':
    unittest.main()
