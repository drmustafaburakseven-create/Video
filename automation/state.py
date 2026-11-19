"""Durable intent journal: a failed/uncertain paid request is never resubmitted."""
import base64
import json
import os
import re
import fcntl
from contextlib import contextmanager
import tempfile
from pathlib import Path

import requests

from automation.errors import PipelineError


def session():
    client = requests.Session()
    client.verify = os.environ.get('SSL_CERT_FILE', True)
    return client


def request(client, method, url, **kwargs):
    """No automatic retry, no response body/header/key in errors."""
    try:
        result = client.request(method, url, timeout=120, allow_redirects=False, **kwargs)
    except requests.RequestException:
        raise PipelineError('Network request failed; inspect the saved journal before retrying.') from None
    if not 200 <= result.status_code < 300:
        raise PipelineError(f'Provider rejected the request (HTTP {result.status_code}).')
    return result


class LocalJournal:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def load(self, name):
        path = self.root / (name + '.json')
        return json.loads(path.read_text()) if path.exists() else {}

    def save(self, name, data):
        path = self.root / (name + '.json')
        with tempfile.NamedTemporaryFile(mode='w', dir=self.root, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    @contextmanager
    def operation_lock(self, name):
        with (self.root/(name+'.lock')).open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


class GitHubJournal:
    """Receipts and TTS response on a separate branch; no credentials or video blobs."""
    branch = 'video-automation-state'

    def __init__(self, repository, token, base_sha):
        if not re.fullmatch(r'[\w.-]+/[\w.-]+', repository):
            raise PipelineError('Invalid GITHUB_REPOSITORY.')
        if not re.fullmatch(r'[a-f0-9]{40}', base_sha):
            raise PipelineError('Invalid GITHUB_SHA.')
        self.base = f'https://api.github.com/repos/{repository}'
        self.client = session()
        self.client.headers.update({'Authorization': f'Bearer {token}',
                                    'Accept': 'application/vnd.github+json',
                                    'X-GitHub-Api-Version': '2022-11-28'})
        self.base_sha = base_sha
        self.shas = {}
        self.branch_exists = False

    def load(self, name):
        response = self.client.get(f'{self.base}/contents/.video-state/{name}.json',
                                   params={'ref': self.branch}, timeout=30)
        if response.status_code == 404:
            self.shas[name] = None
            return {}
        if response.status_code != 200:
            raise PipelineError(f'Cannot read automation journal (HTTP {response.status_code}).')
        self.branch_exists = True
        value = response.json()
        self.shas[name] = value['sha']
        if value.get('encoding') == 'none':
            # TTS audio + alignment can exceed the Contents API's 1 MiB inline limit.
            raw = request(self.client, 'GET', f'{self.base}/contents/.video-state/{name}.json',
                          params={'ref': self.branch},
                          headers={'Accept': 'application/vnd.github.raw+json'})
            return raw.json()
        return json.loads(base64.b64decode(value['content']))

    def save(self, name, data):
        if not self.branch_exists:
            ref = self.client.get(f'{self.base}/git/ref/heads/{self.branch}', timeout=30)
            if ref.status_code == 404:
                request(self.client, 'POST', f'{self.base}/git/refs',
                        json={'ref': f'refs/heads/{self.branch}', 'sha': self.base_sha})
            elif ref.status_code != 200:
                raise PipelineError('Cannot inspect the automation state branch.')
            self.branch_exists = True
        encoded = base64.b64encode(json.dumps(data, ensure_ascii=False).encode()).decode()
        payload = {'message': f'video: checkpoint {name}', 'branch': self.branch, 'content': encoded}
        if self.shas.get(name):
            payload['sha'] = self.shas[name]
        response = request(self.client, 'PUT', f'{self.base}/contents/.video-state/{name}.json',
                           json=payload)
        self.shas[name] = response.json()['content']['sha']


def paid_once(journal, name, state, slot, submit):
    """Commit intent before submitting; preserve successful response before proceeding."""
    if isinstance(journal, LocalJournal):
        with journal.operation_lock(name):
            # A second local process may have loaded its stale state before the lock.
            state.update(journal.load(name))
            return _paid_once(journal, name, state, slot, submit)
    return _paid_once(journal, name, state, slot, submit)


def _paid_once(journal, name, state, slot, submit):
    if slot in state:
        value = state[slot]
        if value.get('status') != 'received':
            raise PipelineError(f'{slot}: previous submission is uncertain; automatic resubmission blocked.')
        return value['response']
    state[slot] = {'status': 'submitting'}
    journal.save(name, state)  # A failed checkpoint means no paid request is sent.
    response = submit()
    state[slot] = {'status': 'received', 'response': response}
    journal.save(name, state)
    return response
