"""Fetch official medical references as bounded, dated text for the editor."""
from datetime import datetime, timedelta, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from automation.state import PipelineError, session

ALLOWED_HOSTS = {'www.cdc.gov', 'www.nhs.uk', 'www.healthychildren.org', 'www.who.int'}


class MainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_main = False
        self.skip = 0
        self.parts = []
        self.fallback = []

    def handle_starttag(self, tag, attrs):
        if tag == 'main':
            self.in_main = True
        if tag in {'script', 'style', 'nav', 'footer', 'noscript'}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag == 'main':
            self.in_main = False
        if tag in {'script', 'style', 'nav', 'footer', 'noscript'} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        value = ' '.join(data.split())
        if value and not self.skip:
            self.fallback.append(value)
            if self.in_main:
                self.parts.append(value)

    def text(self):
        return '\n'.join(self.parts or self.fallback)[:24000]


def validate_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise PipelineError('Medical sources must use an approved official HTTPS website.')


def fetch_source(url, cache, now=None, refresh=False):
    validate_url(url)
    now = now or datetime.now(timezone.utc)
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    target = cache/(hashlib.sha256(url.encode()).hexdigest()+'.json')
    if target.exists() and not refresh:
        try:
            saved = json.loads(target.read_text())
            age = now-datetime.fromisoformat(saved['retrieved_at'])
            if (timedelta(0) <= age < timedelta(days=7) and saved['url'] == url
                    and hashlib.sha256(saved['text'].encode()).hexdigest() == saved['sha256']):
                return saved
        except (ValueError, KeyError, TypeError):
            pass
    client = session()
    current = url
    for _ in range(4):
        validate_url(current)
        response = client.get(current, timeout=25, allow_redirects=False, stream=True)
        if response.status_code in (301, 302, 303, 307, 308):
            next_url = urljoin(current, response.headers.get('Location', ''))
            response.close()
            if next_url == current:
                raise PipelineError('Medical source returned an invalid redirect.')
            current = next_url
            continue
        if response.status_code != 200:
            code = response.status_code
            response.close()
            raise PipelineError(f'Medical source unavailable (HTTP {code}); no script generation started.')
        if 'text/html' not in response.headers.get('Content-Type', '').lower():
            response.close()
            raise PipelineError('Medical source returned an unsupported document type.')
        content = bytearray()
        try:
            for block in response.iter_content(65536):
                content.extend(block)
                if len(content) > 2_000_000:
                    raise PipelineError('Medical source is too large for the bounded research request.')
        finally:
            response.close()
        parser = MainText()
        parser.feed(content.decode('utf-8', errors='replace'))
        text = parser.text()
        if len(text) < 300:
            raise PipelineError('Medical source did not return enough readable text.')
        result = {'url': url, 'final_url': current, 'retrieved_at': now.isoformat(),
                  'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
                  'verification': 'official-page-fetched; individual script claims still require review'}
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        temp.replace(target)
        return result
    raise PipelineError('Medical source redirected too many times.')


def fetch_sources(urls, cache, **kwargs):
    return {url: fetch_source(url, cache, **kwargs) for url in sorted(set(urls))}
