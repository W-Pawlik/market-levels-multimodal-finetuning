"""Package source and one bounded VLM run, excluding weights, data and caches."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    run = args.run.resolve()
    if not run.is_relative_to(root / 'results') or not run.is_dir():
        raise ValueError('Run must be a local results directory')
    output = args.output.resolve()
    manifest_path = output.with_suffix('.manifest.json')
    checksum_path = output.with_suffix('.zip.sha256')
    if any(p.exists() for p in (output, manifest_path, checksum_path)):
        raise FileExistsError('Handoff output already exists')
    paths = set()
    for folder in ('src/market_levels', 'configs', 'tests', 'docs', 'scripts', '.ai'):
        for path in (root / folder).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix.lower() in ('.py', '.ps1', '.md', '.json', '.jsonl', '.txt', '.csv', '.png'):
                paths.add(path)
    for name in ('AGENTS.md', 'README.md', 'LICENSE', 'pyproject.toml', '.gitignore'):
        paths.add(root / name)
    for path in run.rglob('*'):
        relative = path.relative_to(run)
        if (not path.is_file() or 'adapter' in relative.parts or 'sources' in relative.parts
                or path.suffix.lower() not in ('.json', '.jsonl', '.txt', '.log')
                or '-README_md' in path.name or path.name.endswith('-pypi.json')):
            continue
        paths.add(path)
    replacements = [(str(Path.home()), '<USERPROFILE>'), (Path.home().as_posix(), '<USERPROFILE>'),
                    (str(root), '<PROJECT>'), (root.as_posix(), '<PROJECT>')]
    payload = {}
    records = []
    for path in sorted(paths):
        if not path.resolve().is_relative_to(root):
            raise ValueError('Refusing a source symlink outside the project')
        raw = path.read_bytes()
        original_hash = sha(raw)
        anonymized = False
        if path.is_relative_to(run):
            encoding = 'utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
            text = raw.decode(encoding)
            for original, replacement in replacements:
                text = text.replace(original, replacement).replace(original.replace('\\', '\\\\'), replacement)
            raw = text.encode('utf-8')
            anonymized = sha(raw) != original_hash
        if len(raw) > 10_000_000:
            raise ValueError(f'Unexpected large handoff file: {path}')
        name = path.relative_to(root).as_posix()
        payload[name] = raw
        records.append({'path': name, 'bytes': len(raw), 'sha256': sha(raw),
                        'source_sha256': original_hash, 'copy_normalized_or_anonymized': anonymized})
    manifest = {'kind': 'vlm_feasibility_handoff', 'run': run.name, 'file_count': len(records),
                'excludes': ['data/', 'model weights', 'adapters', '.venv', 'external caches', 'third-party documentation copies'],
                'privacy': 'Result text copies use UTF-8 and redact user/project absolute paths; originals retained locally.',
                'files': records}
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in payload.items():
            archive.writestr(name, raw)
        archive.writestr('HANDOFF_MANIFEST.json', manifest_bytes)
    manifest_path.write_bytes(manifest_bytes)
    checksum_path.write_text(sha(output.read_bytes()) + '  ' + output.name + '\n', encoding='ascii')
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(payload) | {'HANDOFF_MANIFEST.json'}:
            raise ValueError('Handoff inventory/CRC mismatch')
        for entry in records:
            if sha(archive.read(entry['path'])) != entry['sha256']:
                raise ValueError('Handoff SHA mismatch')
        if archive.read('HANDOFF_MANIFEST.json') != manifest_path.read_bytes():
            raise ValueError('Handoff manifest mismatch')
    print(json.dumps({'archive': str(output), 'bytes': output.stat().st_size,
                      'files': len(records), 'sha256': sha(output.read_bytes()), 'verified': True}))


if __name__ == '__main__':
    main()
