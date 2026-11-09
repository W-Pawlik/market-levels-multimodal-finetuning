"""Download only public official safetensors after transfer and disk checks."""
from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path

from ...shared.integrity import sha256_file


def download_plan(config: dict) -> dict:
    models = []
    cache = Path(config['cache']).resolve()
    # Resolve an existing parent without creating anything before the checks.
    parent = cache
    while not parent.exists():
        parent = parent.parent
    for spec in config['models'].values():
        request = urllib.request.Request(f"https://huggingface.co/api/models/{spec['id']}/revision/{spec['revision']}?blobs=true")
        with urllib.request.urlopen(request, timeout=60) as response:
            info = json.load(response)
        if (info['sha'] != spec['revision'] or info['id'] != spec['id'] or info.get('gated') is not False
                or info.get('private') or info.get('cardData', {}).get('license') != 'apache-2.0'):
            raise ValueError('Niezweryfikowana tożsamość, dostęp lub licencja checkpointu')
        files = [f for f in info['siblings'] if '/' not in f['rfilename'] and
                 (f['rfilename'].endswith(('.safetensors', '.json', '.jinja', '.txt')) or f['rfilename'] in ('README.md', 'LICENSE'))]
        if not any(f['rfilename'].endswith('.safetensors') for f in files):
            raise ValueError('Brak oficjalnych safetensors')
        if any(type(f.get('size')) is not int or f['size'] < 0 for f in files):
            raise ValueError('Nieznany rozmiar pliku')
        models.append({**spec, 'files': files, 'bytes': sum(f['size'] for f in files)})
    total = sum(m['bytes'] for m in models)
    free = shutil.disk_usage(parent).free
    if total > 18_000_000_000 or free - total < 20_000_000_000:
        raise ValueError('Limit 18 GB transferu lub 20 GB wolnego miejsca nie jest spełniony')
    return {'models': models, 'total_bytes': total, 'free_before_bytes': free, 'cache': str(cache)}


def download_models(plan: dict) -> list[dict]:
    """Stream pinned HTTPS files; no login, remote Python, or duplicate weight copy."""
    saved = []
    for spec in plan['models']:
        folder = Path(plan['cache']) / spec['id'].replace('/', '--') / spec['revision']
        folder.mkdir(parents=True, exist_ok=True)
        records = []
        for entry in spec['files']:
            name = entry['rfilename']
            path = folder / name
            expected = entry.get('lfs', {}).get('sha256')
            if not path.exists():
                partial = path.with_name(name + '.partial')
                if partial.exists():
                    raise ValueError(f'Niekompletne pobranie wymaga diagnozy: {partial}')
                url = f"https://huggingface.co/{spec['id']}/resolve/{spec['revision']}/{name}"
                print(f"download {spec['id']} {name} ({entry['size']} bytes)", flush=True)
                with urllib.request.urlopen(url, timeout=90) as response, partial.open('xb') as target:
                    shutil.copyfileobj(response, target, 4 * 1024 * 1024)
                if partial.stat().st_size != entry['size'] or (expected and sha256_file(partial) != expected):
                    raise ValueError(f'Niezgodny rozmiar lub SHA-256: {partial}')
                partial.rename(path)
            digest = sha256_file(path)
            if path.stat().st_size != entry['size'] or (expected and digest != expected):
                raise ValueError(f'Niezgodny cache: {path}')
            records.append({'file': name, 'bytes': path.stat().st_size, 'sha256': digest})
        saved.append({'id': spec['id'], 'revision': spec['revision'], 'path': str(folder), 'files': records})
    return saved


def local_checkpoint(config: dict, key: str) -> Path:
    spec = config['models'][key]
    path = Path(config['cache']) / spec['id'].replace('/', '--') / spec['revision']
    if not (path / 'config.json').is_file():
        raise ValueError('Brak lokalnego checkpointu; najpierw wykonaj download')
    return path
