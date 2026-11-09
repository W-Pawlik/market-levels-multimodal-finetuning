"""Predict Windows output paths without changing seeds or identities."""
from __future__ import annotations

from pathlib import Path, PureWindowsPath

from .config import SYMBOLS, VARIANTS, SEEDS, FRESH_SEEDS, WINDOWS_MAX_PATH


def longest_output_path(root: Path | PureWindowsPath, mode: str, *, fresh: bool = False) -> PureWindowsPath:
    """Przewidź pliki staging/final i raporty, bez generowania ani skracania ID.

    Aktualny tempfile używa 8 znaków losowych; identyfikatory partii/raportów
    mają 24 znaki, seedy przykładów 64 hex. Sprawdzamy oba warianty, ponieważ
    bridge_volatility ma dłuższy katalog niż full. Limit stosujemy przenośnie,
    bez polegania na ustawieniu LongPathsEnabled konkretnego Windows.
    """
    root = PureWindowsPath(root)
    seeds = FRESH_SEEDS if fresh else ((20261107,) if mode == 'smoke' else SEEDS)
    paths = [root/'run.json', root/('error-'+'f'*32+'.log')]
    for seed in seeds:
        for variant in (('v1','original',*VARIANTS) if fresh else VARIANTS):
            stage = f'{variant}-{seed}'
            batch = root/stage
            locations = (batch/('.synthetic-'+'x'*8)/'batch', batch/'diagnostics'/('f'*24))
            for location in locations:
                paths.append(location/'manifest.json')
                for symbol in SYMBOLS:
                    for suffix in ('.csv', '.json'):
                        paths.append(location/symbol/(symbol+'_000000_'+'f'*64+suffix))
            paths.append(root/'completed'/(stage+'.json'))
            for symbol in SYMBOLS:
                report_stage = stage+'-'+symbol
                paths.extend((root/'completed'/(report_stage+'.json'),
                              root/'logs'/(report_stage+'-'+'f'*32+'.log')))
                outputs = [root/'comparisons'/report_stage]
                if mode != 'smoke' or fresh:
                    outputs.append(root/'summary'/symbol)
                for output in outputs:
                    for location in (output/('.comparison-'+'x'*8)/'report', output/('f'*24)):
                        paths.extend((location/(symbol+'_comparison.json'), location/(symbol+'_summary.md')))
    return max(paths, key=lambda path: len(str(path).encode('utf-16-le'))//2)


def validate_output_paths(root: Path | PureWindowsPath, mode: str, *, fresh: bool = False) -> int:
    """Odmów przed tworzeniem katalogów i uruchamianiem generatora."""
    path = longest_output_path(root, mode, fresh=fresh)
    length = len(str(path).encode('utf-16-le'))//2
    if length >= WINDOWS_MAX_PATH:
        raise ValueError(f'Zbyt długa ścieżka Windows: {length} znaków UTF-16 (wymagane <260). '
                         f'Najdłuższa przewidywana ścieżka: {path}. '
                         'Użyj -OutputDirectory z krótszą ścieżką, np. D:\\rc\\nowy. '
                         'Nie przenoś ani nie nadpisuj wcześniejszych wyników.')
    return length
