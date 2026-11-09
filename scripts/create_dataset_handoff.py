"""Mały handoff 3.5 z inwentarzem SHA; bez dużych danych i bez nadpisywania."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from market_levels.shared.configuration import read_configuration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    checksum = output.with_suffix(output.suffix+'.sha256')
    if output.exists() or checksum.exists():
        raise FileExistsError('Odmowa nadpisania ZIP lub sumy kontrolnej')
    paths = []
    for name in ('src/market_levels', 'tests', 'configs', 'docs', 'scripts', '.ai',
                 'results/diagnostics/ds35-pre-20261107-b',
                 'results/diagnostics/ds35-smoke-20261107-a',
                 'results/diagnostics/ds35-check-20261107-a',
                 'results/diagnostics/dc-20261106-c/pilot',
                 'results/diagnostics/sr-20261106-a'):
        directory = root/name
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        paths.extend(p for p in directory.rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo'))
    paths.extend(root/name for name in ('AGENTS.md', 'README.md', 'LICENSE', 'pyproject.toml', '.gitignore'))
    config = read_configuration(root/'configs/experiment.json')
    paths.extend(root/name for name in config['dataset_build']['profiles'].values())
    payloads = {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(set(paths))}
    inventory = {name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in payloads.items():
            archive.writestr(name, payload)
        archive.writestr('HANDOFF_SHA256.json', json.dumps(inventory, indent=2, ensure_ascii=False))
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError('Uszkodzone archiwum')
        for name, digest in inventory.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f'Niezgodna zawartość: {name}')
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    with checksum.open('x', encoding='utf-8') as stream:
        stream.write(f'{digest}  {output.name}\n')
    print(f'{output}: {len(inventory)} plików, {output.stat().st_size} bajtów, SHA-256 {digest}')


if __name__ == '__main__':
    main()
