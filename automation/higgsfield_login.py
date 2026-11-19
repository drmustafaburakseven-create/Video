"""Restartable PKCE login for the official Higgsfield CLI 1.2.2.

Only public OAuth endpoints are used. The verifier and tokens stay in private
0600 files. There is no generation, billing, password collection or auto-login.
"""
import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import tempfile
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

import requests

from automation.state import LocalJournal, PipelineError, session


CLIENT_ID = 'sRGCQJvvJkPrrtRj'  # Public client identifier shipped by the official CLI.
ISSUER = 'https://clerk.higgsfield.ai'
CALLBACK = 'http://localhost:8765/callback'
SCOPES = 'email profile offline_access user:org:read'
ROOT = Path(__file__).resolve().parent / 'private' / 'higgsfield-login'
CREDENTIALS = Path.home() / '.config/higgsfield/credentials.json'


def save_private(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as f:
        temporary = Path(f.name)
        os.fchmod(f.fileno(), 0o600)
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def authorize_url(pending):
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(pending['verifier'].encode()).digest()).rstrip(b'=').decode()
    return ISSUER + '/oauth/authorize?' + urlencode({
        'client_id': CLIENT_ID, 'redirect_uri': CALLBACK, 'response_type': 'code',
        'scope': SCOPES, 'code_challenge_method': 'S256',
        'code_challenge': challenge, 'state': pending['state'],
    })


def begin(root=ROOT, credentials=CREDENTIALS, now=None):
    now = time.time() if now is None else now
    if credentials.exists():
        raise PipelineError('Kayıtlı giriş korunuyor; önce resmi CLI ile bağlantıyı kontrol edin.')
    journal = LocalJournal(root)
    os.chmod(root, 0o700)
    with journal.operation_lock('login'):
        pending = journal.load('pending')
        if not pending or now >= pending['expires_at']:
            pending = {'state': secrets.token_urlsafe(32), 'verifier': secrets.token_urlsafe(48),
                       'created_at': now, 'expires_at': now + 4 * 60 * 60}
            save_private(root / 'pending.json', pending)
        return authorize_url(pending)


def callback_code(url, pending, now):
    parsed = urlsplit(url.strip())
    if (parsed.scheme, parsed.netloc, parsed.path) != ('http', 'localhost:8765', '/callback') or parsed.fragment:
        raise PipelineError('Beklenen Higgsfield dönüş adresi değil.')
    query = parse_qs(parsed.query, keep_blank_values=True)
    states = query.get('state', [])
    if len(states) != 1 or not secrets.compare_digest(states[0], pending['state']):
        raise PipelineError('Giriş bu bulutta başlatılan oturumla eşleşmiyor.')
    if now >= pending['expires_at']:
        raise PipelineError('Giriş süresi dolmuş; yeni bağlantı oluşturun.')
    if 'error' in query:
        raise PipelineError('Higgsfield yetkilendirmesi tamamlanmadı.')
    codes = query.get('code', [])
    if len(codes) != 1 or not codes[0] or len(codes[0]) > 8192:
        raise PipelineError('Dönüş adresinde tek bir geçerli giriş kodu olmalı.')
    return codes[0]


def complete(url, root=ROOT, credentials=CREDENTIALS, client=None, now=None):
    now = time.time() if now is None else now
    journal = LocalJournal(root)
    with journal.operation_lock('login'):
        pending = journal.load('pending')
        if not pending:
            raise PipelineError('Bekleyen giriş yok; yeni bağlantı oluşturun.')
        code = callback_code(url, pending, now)
        if credentials.exists():
            raise PipelineError('Kayıtlı giriş korunuyor; üzerine yazılmadı.')
        try:
            response = (client or session()).post(ISSUER + '/oauth/token', data={
                'grant_type': 'authorization_code', 'client_id': CLIENT_ID,
                'redirect_uri': CALLBACK, 'code_verifier': pending['verifier'], 'code': code,
            }, timeout=30, allow_redirects=False)
            if response.status_code != 200:
                raise PipelineError('Higgsfield giriş kodunu kabul etmedi; yeni giriş gerekebilir.')
            tokens = response.json()
        except (requests.RequestException, ValueError):
            raise PipelineError('Giriş yanıtı alınamadı; hesap bağlantısı doğrulanmadı.') from None
        lifetime = tokens.get('expires_in') if isinstance(tokens, dict) else None
        if (isinstance(lifetime, bool) or not isinstance(lifetime, (int, float))
                or not math.isfinite(lifetime) or lifetime <= 0
                or str(tokens.get('token_type', '')).lower() != 'bearer'
                or any(not isinstance(tokens.get(k), str) or not tokens[k]
                       for k in ('access_token', 'refresh_token'))):
            raise PipelineError('Giriş yanıtı resmi CLI biçimiyle uyuşmuyor; kaydedilmedi.')
        # auth_version=2 and Unix seconds verified against official CLI 1.2.2.
        save_private(credentials, {
            'auth_version': 2, 'access_token': tokens['access_token'],
            'refresh_token': tokens['refresh_token'], 'token_type': 'Bearer',
            'expires_at': int(now + lifetime),
        })
        (root / 'pending.json').unlink()
        save_private(root / 'status.json', {'status': 'credentials_saved', 'saved_at': now,
                     'account_access_verified': False})
    return 'Giriş kaydedildi. Hesap ve çalışma alanı erişimi ayrıca doğrulanacak.'


def listen(root=ROOT, credentials=CREDENTIALS):
    # No callback URLs/codes in HTTP logs. Loopback only; not a public web server.
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if not self.path.startswith('/callback?'):
                self.send_error(404)
                return
            try:
                message = complete('http://localhost:8765' + self.path, root, credentials)
                self.server.done = True
                status = 200
            except PipelineError as error:
                message, status = str(error), 400
            payload = ('<!doctype html><meta charset="utf-8"><title>Higgsfield bağlantısı</title>'
                       '<p>' + message + '</p><p>Codex sohbetine dönebilirsiniz.</p>').encode()
            self.send_response(status)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            self.wfile.write(payload)

    with HTTPServer(('127.0.0.1', 8765), Handler) as server:
        server.done, server.timeout = False, 30
        print('Bulut tarayıcısından Higgsfield dönüşü bekleniyor.', flush=True)
        deadline = time.monotonic() + 4 * 60 * 60
        while not server.done and time.monotonic() < deadline:
            server.handle_request()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['begin', 'listen', 'complete'])
    parser.add_argument('--callback-file', type=Path,
                        help='Özel dosyadaki tek kullanımlık dönüş adresi; komut satırına kod yazmayın.')
    args = parser.parse_args()
    try:
        if args.action == 'begin':
            print(begin())
        elif args.action == 'listen':
            listen()
        elif args.callback_file:
            print(complete(args.callback_file.read_text()))
        else:
            parser.error('complete için --callback-file gerekli')
    except (PipelineError, OSError, ValueError):
        # Never let file contents, URL codes or network responses reach a traceback/log.
        print('Giriş tamamlanamadı. Özel oturum dosyasını ve bağlantı durumunu kontrol edin.')
        raise SystemExit(2) from None


if __name__ == '__main__':
    main()
