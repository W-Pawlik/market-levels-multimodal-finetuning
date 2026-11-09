"""Evaluation output policy and exact Decimal JSON report writing."""
from __future__ import annotations

from pathlib import Path

from ...shared.paths import require_short_path
from ..protocol import dumps


def _output(output: Path) -> Path:
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Odmowa nadpisania: {output}')
    output = output.resolve()
    if not any(Path(folder).resolve() in output.parents for folder in ('results/evaluation','results/diagnostics')):
        raise ValueError('Wynik ewaluacji wymaga nowego katalogu w results/evaluation lub results/diagnostics')
    for root in (output, output.parent/('.eval-'+'x'*8)/'batch'):
        require_short_path(root/'per_example.jsonl')
        require_short_path(root/'SOURCE_INTEGRITY.json')
    return output


def _write(path: Path, value) -> None:
    path.write_text(dumps(value)+'\n', encoding='utf-8')
