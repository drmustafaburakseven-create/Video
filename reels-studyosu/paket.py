"""Move a strict set of media files between the studio and GitHub, encrypted."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

INPUT = {'bolum.json', 'zamanlar.json', 'hizalama.json', 'giris.mp4', 'cikis.mp4',
         'giris.wav', 'cikis.wav', 'anlatim.wav', *(f'stok-{i}.mp4' for i in range(1, 5))}
OUTPUT = {'Video-1080p.mp4', 'Video-Telefon.mp4', 'paylasim.md'}


def transfer(action, stage, source, target):
    password = os.environ.get('REELS_MEDIA_KEY', '')
    if len(password) < 32 or '\n' in password or '\r' in password:
        raise ValueError('REELS_MEDIA_KEY için en az 32 karakterlik rastgele gizli anahtar gerekli.')
    required = INPUT if stage == 'girdi' else OUTPUT
    allowed = required | ({'muzik.wav', *(f'stok-{i}.mp4' for i in range(5, 9))} if stage == 'girdi' else set())
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp)/'paket.zip'
        # Use a private, short-lived GnuPG home. Passphrase never appears in argv.
        args = ['gpg', '--homedir', tmp, '--batch', '--quiet', '--pinentry-mode', 'loopback',
                '--passphrase-fd', '0']
        if action == 'kilitle':
            if stage == 'girdi':
                count = len(json.loads((source/'bolum.json').read_text())['stocks'])
                if not 4 <= count <= 8:
                    raise ValueError('Bölümde 4–8 stok çekimi olmalı.')
                required = INPUT | {f'stok-{i}.mp4' for i in range(5, count+1)}
                allowed = required | {'muzik.wav'}
            with zipfile.ZipFile(archive, 'w') as z:
                for name in sorted(allowed):
                    path = source/name
                    if name in required or path.exists():
                        if path.is_symlink() or not path.is_file():
                            raise ValueError(f'Eksik medya dosyası: {name}')
                        z.write(path, name)
            if target.exists():
                raise ValueError('Yeni bir paket dosya adı kullanın.')
            args += ['--output', str(target), '--symmetric', '--cipher-algo', 'AES256', str(archive)]
        else:
            args += ['--output', str(archive), '--decrypt', str(source)]
        subprocess.run(args, input=(password+'\n').encode(), check=True)
        if action == 'ac':
            with zipfile.ZipFile(archive) as z:
                names = set(z.namelist())
                if (not required <= names <= allowed or len(names) != len(z.infolist())
                        or sum(item.file_size for item in z.infolist()) > 2_000_000_000):
                    raise ValueError('Medya paketinin içeriği geçersiz.')
                target.mkdir(parents=True, exist_ok=False)
                for name in sorted(names):
                    with z.open(name) as src, (target/name).open('xb') as dst:
                        shutil.copyfileobj(src, dst)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['kilitle','ac'])
    p.add_argument('stage', choices=['girdi','sonuc'])
    p.add_argument('source', type=Path)
    p.add_argument('target', type=Path)
    a = p.parse_args()
    transfer(a.action, a.stage, a.source, a.target)
