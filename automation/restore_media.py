"""Restore pinned public Pexels footage without redistributing original binaries."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile

import requests

from automation import hybrid
from automation.render import probe
from automation.state import PipelineError, session
from automation.stock import _url

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 100_000_000


def _verify(path, asset):
    if hashlib.sha256(path.read_bytes()).hexdigest() != asset['sha256']:
        raise PipelineError('Stock file differs from its reviewed original; catalog was not changed.')
    media = probe(path)
    video = next((s for s in media.get('streams', []) if s.get('codec_type') == 'video'), None)
    duration = float(video.get('duration', media.get('format', {}).get('duration', 0))) if video else 0
    expected = asset.get('source_duration', asset.get('duration'))
    if (not isinstance(expected, (int, float)) or not math.isfinite(expected)
            or not math.isfinite(duration) or duration + 0.05 < expected):
        raise PipelineError('Restored stock footage does not cover its reviewed duration.')


def restore_asset(identifier, asset, root=ROOT):
    """Download to a temporary file; install only the exact reviewed bytes."""
    root = Path(root).resolve()
    if (not re.fullmatch(r'pexels-[0-9]+', identifier) or asset.get('kind') != 'stock'
            or asset.get('provider') != 'pexels'
            or not re.fullmatch(r'[0-9a-f]{64}', asset.get('sha256', ''))
            or asset.get('path') != f'media/library/{identifier}.mp4'):
        raise PipelineError('Stock restoration needs a pinned Pexels catalog entry.')
    url = _url(asset.get('download_url'), {'videos.pexels.com'}, mp4=True)
    destination = root/asset['path']
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or not destination.parent.resolve().is_relative_to(root):
        raise PipelineError('Stock paths must stay inside the local media library.')
    if destination.exists():
        _verify(destination, asset)
        return destination
    temporary = None
    client = session()  # Fresh client: no API key or authorization header.
    try:
        response = client.get(url, timeout=120, stream=True, allow_redirects=False)
        try:
            if response.status_code != 200:
                raise PipelineError(f'Public stock download failed (HTTP {response.status_code}).')
            with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.mp4', delete=False) as stream:
                temporary = Path(stream.name)
                size = 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise PipelineError('Public stock download exceeds 100 MB.')
                    stream.write(chunk)
            _verify(temporary, asset)
            # A concurrent restore can only install the same pinned bytes.
            temporary.replace(destination)
            return destination
        finally:
            response.close()
    except requests.RequestException:
        raise PipelineError('Public stock download failed; no catalog or existing media was changed.') from None
    finally:
        client.close()
        if temporary:
            temporary.unlink(missing_ok=True)


def restore(root=ROOT, topic=None):
    assets = hybrid.catalog(Path(root))
    selected = [(key, asset) for key, asset in assets.items()
                if asset.get('kind') == 'stock' and asset.get('provider') == 'pexels'
                and (topic is None or topic in asset.get('approved_topics', []))]
    return [restore_asset(key, asset, root) for key, asset in selected]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--topic', help='Restore only footage curated for this topic ID.')
    args = parser.parse_args(argv)
    try:
        paths = restore(args.root, args.topic)
    except (PipelineError, OSError, ValueError) as error:
        message = str(error) if isinstance(error, PipelineError) else 'Stock restoration stopped; original files preserved.'
        print(json.dumps({'status': 'blocked', 'message': message}))
        return 2
    print(json.dumps({'status': 'stock_ready', 'files': len(paths), 'paid_requests': 0}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
