"""Distinct diagnostic and production output policies."""
from __future__ import annotations

from pathlib import Path

from ...shared.paths import require_short_path


def diagnostic_output(output: Path, *, source: Path | None = None) -> Path:
    output = Path(output).resolve()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Odmowa nadpisania: {output}")
    allowed = Path("results/diagnostics").resolve()
    if allowed not in output.parents or (source is not None and source.resolve() in output.parents):
        raise ValueError("Wynik wymaga nowego katalogu results/diagnostics poza źródłem")
    for root in (output, output.parent/(".ds-"+"x"*8)/"batch"):
        require_short_path(root/"metadata/007.json")
        require_short_path(root/"SOURCE_INTEGRITY.json")
    return output


def production_output(output: Path) -> Path:
    output = output.resolve()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Odmowa nadpisania: {output}')
    if Path('data/datasets').resolve() not in output.parents:
        raise ValueError('Produkcja wymaga nowego katalogu pod data/datasets')
    for base in (output, output.parent/('.dataset-'+'x'*8)/'batch'):
        for name in ('metadata/'+'x'*24+'.json', 'profiles/BTCUSDT.json', 'SOURCE_INTEGRITY.json'):
            require_short_path(base/name)
    return output
