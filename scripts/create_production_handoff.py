"""Code handoff plus a separate, complete local data ZIP; no overwriting."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def write_zip(output: Path, payloads: dict):
    checksum = output.with_suffix(output.suffix+'.sha256')
    if output.exists() or checksum.exists():
        raise FileExistsError(f'Odmowa nadpisania: {output}')
    inventory = {n: hashlib.sha256(b).hexdigest() for n, b in payloads.items()}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in sorted(payloads.items()):
            archive.writestr(name, payload)
        archive.writestr('HANDOFF_SHA256.json', json.dumps(inventory, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError('Uszkodzone archiwum')
        for name, digest in inventory.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f'Niezgodny SHA: {name}')
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    with checksum.open('x', encoding='ascii') as stream:
        stream.write(f'{digest}  {output.name}\n')
    print(f'{output}: {len(inventory)} plików, {output.stat().st_size} bajtów, SHA-256 {digest}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--preflight', type=Path, required=True)
    parser.add_argument('--approved', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--data-output', type=Path, required=True)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    paths = []
    for folder in ('src/market_levels', 'tests', 'configs', 'docs', 'scripts', '.ai',
                   args.review, args.control, args.preflight, args.approved):
        paths.extend(p for p in Path(folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts
                     and p.suffix not in ('.pyc', '.pyo'))
    paths.extend(Path(name) for name in ('README.md','AGENTS.md','LICENSE','pyproject.toml','.gitignore'))
    approval = json.loads((args.approved/'approval.json').read_text(encoding='utf-8'))
    paths.extend(Path(r['original_path']) for r in approval['profiles'])
    paths.extend(p for p in args.dataset.iterdir() if p.is_file())
    paths.extend((args.dataset/'splits').glob('*.jsonl'))
    payloads = {p.resolve().relative_to(root).as_posix(): p.read_bytes() for p in sorted(set(paths))}
    payloads['HANDOFF_README.md'] = (
        '# Handoff etapu 3.5, część 2\n\n'
        'Kod, konfiguracja, testy, raporty, profile, pełne manifesty/statystyki/JSONL i 16 próbek przeglądowych.\n'
        'Katalog produkcji w paczce kodu zawiera tylko manifesty i opis; pozostałe pliki są w osobnym ZIP danych.\n'
        'Próbki z własnym manifestem są w results/diagnostics/ds35-review-20261107-a.\n'
        'Obrazy overlays są diagnostyczne i nie mogą wejść do VLM.\n'
        'Pełne dane rozpakuj obok kodu. Weryfikacja: python -m market_levels.cli.build_dataset verify '
        '--output data/datasets/ds35-800-20261107-a\n'
        'Flaga --check-sources wymaga oryginalnych CSV i lokalnych ścieżek historycznych.\n'
        'Instrukcja: docs/datasets/INSTRUKCJA_POWERSHELL.md. Nie rozpoczynaj treningu.\n').encode('utf-8')
    for output in (args.output, args.data_output):
        if output.exists() or output.with_suffix(output.suffix+'.sha256').exists():
            raise FileExistsError(f'Odmowa nadpisania: {output}')
    write_zip(args.output, payloads)
    data = {p.resolve().relative_to(root).as_posix(): p.read_bytes() for p in args.dataset.rglob('*') if p.is_file()}
    write_zip(args.data_output, data)


if __name__ == '__main__':
    main()
