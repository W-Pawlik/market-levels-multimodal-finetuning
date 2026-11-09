"""Existing CLI subprocesses, run locks and checkpoint operations."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from contextlib import contextmanager

from ...shared.json_io import read_json


def resolve(project: Path, value: str | Path) -> Path:
    return (project / value).resolve()


def checked_report(path: Path) -> dict:
    report = read_json(path)
    payload = {k: v for k, v in report.items() if k != 'comparison_id'}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()[:24]
    if report.get('comparison_id') != digest:
        raise ValueError(f'Niezgodny hash raportu: {path}')
    return report


def cli(module: str, arguments: list[str], project: Path, log: Path | None = None) -> None:
    command = [sys.executable, '-I', '-X', 'utf8', '-m', 'market_levels.cli.' + module, *map(str, arguments)]
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    if log is not None:
        # Nowy log każdej próby, także przy wznowieniu; zachowuje pełny traceback.
        with log.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(command, ensure_ascii=False) + '\n'); stream.flush()
            process = subprocess.run(command, cwd=project, env=env, stdout=stream, stderr=subprocess.STDOUT)
    else:
        process = subprocess.run(command, cwd=project, env=env, capture_output=True, text=True,
                                 encoding='utf-8', errors='replace')
    if process.returncode:
        if log is None:
            sys.stderr.write(process.stderr)
        raise RuntimeError(f'CLI {module}: kod {process.returncode}; log: {log or "stderr"}')


def exclusive_json(path: Path, value: dict) -> None:
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


def unique_file(root: Path, pattern: str) -> Path | None:
    # Tylko opublikowany katalog <id>/<plik>; staging ma dodatkowy poziom
    # .synthetic-*/batch lub .comparison-*/report i nie jest wynikiem.
    matches = list(root.glob('*/'+pattern)) if root.exists() else []
    if len(matches) > 1:
        raise ValueError(f'Niejednoznaczny wynik: {root}/{pattern}')
    return matches[0] if matches else None


def incomplete_stage(path: Path) -> ValueError:
    return ValueError(f'Niekompletny etap: {path.resolve()}. Ukończone etapy zostaną zachowane. '
        'Po zatrzymaniu procesu ręcznie przenieś CAŁY ten niekompletny katalog do nowego, '
        'nieistniejącego katalogu kopii poza przebiegiem (Move-Item -LiteralPath ... -Destination ...). '
        'Sprawdź ścieżki i zachowaj kopię; nie usuwaj checkpointów ani poprawnych partii. '
        'Następnie uruchom ten sam skrypt i tryb z -ResumeDirectory wskazującym katalog przebiegu. '
        'Jeśli zmieniono kod od utworzenia run.json, kontrola SHA wymaga nowego przebiegu.')


@contextmanager
def run_lock(path: Path):
    """Blokadę zwalnia system także po twardym przerwaniu procesu."""
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0'); stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
