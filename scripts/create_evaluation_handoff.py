"""Create a small evaluation code/fixture/results handoff without production data."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--diagnostic', type=Path, default=Path('results/diagnostics/ev36-20261107-a'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    checksum = args.output.with_suffix(args.output.suffix+'.sha256')
    if args.output.exists() or checksum.exists():
        raise FileExistsError('Odmowa nadpisania ZIP lub sumy kontrolnej')
    paths = []
    for name in ('src/market_levels','tests','configs','docs','scripts','.ai',args.diagnostic):
        folder = root/name
        if not folder.is_dir():
            raise FileNotFoundError(folder)
        paths.extend(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts
                     and p.suffix not in ('.pyc','.pyo'))
    paths.extend(root/name for name in ('AGENTS.md','README.md','LICENSE','pyproject.toml','.gitignore'))
    payloads = {p.relative_to(root).as_posix():p.read_bytes() for p in sorted(set(paths))}
    payloads['HANDOFF_README.md'] = (
        '# Etap 3.6, część 1\n\n'
        'Wyniki ewaluacji w paczce są testem technicznym ręcznych fixture, nie wynikiem VLM.\n'
        'Pełny zbiór 800 wykresów nie jest dołączony.\n'
        'Protokół: docs/evaluation/PROTOKOL_3_6.md. Polecenia: docs/evaluation/INSTRUKCJA_POWERSHELL.md.\n'
        'Sprawdź: python -m market_levels.cli.evaluate verify --output results/diagnostics/ev36-20261107-a/manual-a\n'
        'oraz analogicznie comparison. Nie rozpoczynaj inferencji ani treningu.\n').encode('utf-8')
    inventory = {n:hashlib.sha256(b).hexdigest() for n,b in payloads.items()}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in payloads.items():
            archive.writestr(name,content)
        archive.writestr('HANDOFF_SHA256.json',json.dumps(inventory,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(args.output) as archive:
        if archive.testzip() is not None:
            raise ValueError('Uszkodzone archiwum')
        for name, digest in inventory.items():
            if hashlib.sha256(archive.read(name)).hexdigest()!=digest:
                raise ValueError(f'Niezgodny SHA-256: {name}')
    digest=hashlib.sha256(args.output.read_bytes()).hexdigest()
    with checksum.open('x',encoding='ascii') as stream:
        stream.write(f'{digest}  {args.output.name}\n')
    print(f'{args.output}: {len(inventory)} plików, {args.output.stat().st_size} bajtów, SHA-256 {digest}')


if __name__ == '__main__':
    main()
