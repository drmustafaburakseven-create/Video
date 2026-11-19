import json
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from automation.higgsfield_login import CALLBACK, ISSUER, begin, complete
from automation.state import PipelineError


class Response:
    status_code = 200
    def json(self):
        return {'access_token': 'test-access', 'refresh_token': 'test-refresh',
                'token_type': 'Bearer', 'expires_in': 3600}


class Client:
    def __init__(self): self.calls = []
    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return Response()


def setup_login(tmp_path):
    root, creds = tmp_path/'private', tmp_path/'credentials.json'
    url = begin(root, creds, now=100)
    state = parse_qs(urlsplit(url).query)['state'][0]
    return root, creds, state


def test_pending_login_survives_new_process_and_has_private_permissions(tmp_path):
    root, creds, state = setup_login(tmp_path)
    first = (root/'pending.json').read_text()
    assert state in begin(root, creds, now=110)
    assert (root/'pending.json').read_text() == first
    assert (root/'pending.json').stat().st_mode & 0o777 == 0o600
    assert root.stat().st_mode & 0o777 == 0o700
    pending = json.loads(first)
    assert pending['verifier'] not in begin(root, creds, now=120)
    assert state not in begin(root, creds, now=20000)


@pytest.mark.parametrize('mutation', ['wrong_state', 'wrong_origin', 'duplicate_code', 'expired'])
def test_bad_callback_cannot_exchange_or_save_credentials(tmp_path, mutation):
    root, creds, state = setup_login(tmp_path)
    url = CALLBACK + '?' + urlencode({'code': 'test-code', 'state': state})
    now = 200
    if mutation == 'wrong_state': url = url.replace(state, 'unrelated-state')
    if mutation == 'wrong_origin': url = url.replace('localhost', 'attacker.example')
    if mutation == 'duplicate_code': url += '&code=second'
    if mutation == 'expired': now = 20000
    client = Client()
    with pytest.raises(PipelineError): complete(url, root, creds, client=client, now=now)
    assert not client.calls and not creds.exists()
    assert (root/'pending.json').exists()


def test_code_exchange_saves_cli_credentials_once_without_exposing_them(tmp_path):
    root, creds, state = setup_login(tmp_path)
    url = CALLBACK + '?' + urlencode({'code': 'test-code', 'state': state})
    client = Client()
    message = complete(url, root, creds, client=client, now=200)
    assert 'test-access' not in message and 'test-refresh' not in message
    assert client.calls[0][0] == (ISSUER + '/oauth/token',)
    assert client.calls[0][1]['allow_redirects'] is False
    assert json.loads(creds.read_text())['expires_at'] == 3800
    assert json.loads(creds.read_text())['auth_version'] == 2
    assert creds.stat().st_mode & 0o777 == 0o600
    assert not (root/'pending.json').exists()
    with pytest.raises(PipelineError): complete(url, root, creds, client=client, now=201)
    assert len(client.calls) == 1


def test_existing_credentials_are_preserved(tmp_path):
    root, creds, state = setup_login(tmp_path)
    creds.write_text('existing-account')
    with pytest.raises(PipelineError): begin(root, creds, now=110)
    with pytest.raises(PipelineError):
        complete(CALLBACK + '?' + urlencode({'code': 'x', 'state': state}),
                 root, creds, client=Client(), now=120)
    assert creds.read_text() == 'existing-account'


def test_provider_error_body_is_not_logged(tmp_path):
    root, creds, state = setup_login(tmp_path)
    class BadClient:
        def post(self, *args, **kwargs):
            response = Response()
            response.status_code = 400
            response.text = 'sensitive-code-and-response'
            return response
    with pytest.raises(PipelineError) as error:
        complete(CALLBACK + '?' + urlencode({'code': 'x', 'state': state}),
                 root, creds, client=BadClient(), now=120)
    assert 'sensitive' not in str(error.value)
    assert not creds.exists()


@pytest.mark.parametrize('bad_tokens', [
    [], {'expires_in': True},
    {'access_token': 'x', 'refresh_token': 'y', 'expires_in': -1, 'token_type': 'Bearer'},
    {'access_token': 'x', 'refresh_token': 'y', 'expires_in': float('nan'), 'token_type': 'Bearer'},
    {'access_token': 'x', 'expires_in': 3600, 'token_type': 'Bearer'},
])
def test_malformed_token_response_never_replaces_private_credentials(tmp_path, bad_tokens):
    root, creds, state = setup_login(tmp_path)
    class BadClient:
        def post(self, *args, **kwargs):
            response = Response()
            response.json = lambda: bad_tokens
            return response
    with pytest.raises(PipelineError):
        complete(CALLBACK + '?' + urlencode({'code': 'x', 'state': state}),
                 root, creds, client=BadClient(), now=120)
    assert not creds.exists()
