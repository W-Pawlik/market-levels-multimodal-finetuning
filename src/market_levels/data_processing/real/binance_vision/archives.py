"""Pozyskiwanie archiwów, kontrola SHA-256 i fallback na archiwa dzienne."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from zipfile import is_zipfile
from datetime import date

from .client import DownloadError, INTERVAL, _get, _remote_url
from ....core.time.calendar import _days_in_month, _last_closed_month
from ....shared.integrity import sha256_file as _sha256_file


def _expected_sha256(checksum_path: Path, zip_name: str) -> str:
    lines = checksum_path.read_text(encoding="utf-8").strip().splitlines()
    if len(lines) != 1:
        raise DownloadError(f"Nieoczekiwany format sumy kontrolnej: {checksum_path}")
    match = re.fullmatch(r"([a-fA-F0-9]{64})\s+\*?(.+)", lines[0].strip())
    if not match:
        raise DownloadError(f"Niepoprawna suma kontrolna: {checksum_path}")
    if Path(match.group(2)).name != zip_name:
        raise DownloadError(f"Suma kontrolna dotyczy innego archiwum: {checksum_path}")
    return match.group(1).lower()


def acquire_archive(symbol: str, period: str, category: str,
                    raw_dir: Path, offline: bool) -> tuple[Path, dict]:
    """Pozyskaj zweryfikowany ZIP i metadane źródła, zachowując lokalny cache."""
    url = _remote_url(symbol, period, category)
    basename = url.rsplit("/", 1)[-1]
    dest = raw_dir / symbol / INTERVAL / category / basename
    checksum = dest.with_name(basename + ".CHECKSUM")
    _get(url + ".CHECKSUM", checksum, offline=offline)
    expected = _expected_sha256(checksum, basename)
    if dest.exists() and _sha256_file(dest) != expected:
        if offline:
            raise DownloadError(f"Błędna suma SHA-256 istniejącego archiwum: {dest}")
        dest.unlink()  # ponownie pobierz zmienione/uszkodzone archiwum
    _get(url, dest, offline=offline)
    actual = _sha256_file(dest)
    if actual != expected:
        raise DownloadError(f"Niezgodność SHA-256 dla {basename}; oczekiwano {expected}, jest {actual}")
    if not is_zipfile(dest):
        raise DownloadError(f"Plik nie jest archiwum ZIP: {dest}")
    return dest, {"url": url, "file": str(dest), "sha256": actual,
                  "checksum_file": str(checksum), "period": period,
                  "source": "Binance Vision Spot Klines", "license": "CC BY-NC-SA 4.0 + Vision Dataset Terms"}


def acquire_month(symbol: str, month: date, raw_dir: Path,
                  offline: bool, daily_fallback: bool = True) -> list[tuple[Path, dict]]:
    """Pozyskaj miesiąc lub dopuszczone archiwa dzienne ostatniego miesiąca."""
    period = month.strftime("%Y-%m")
    try:
        return [acquire_archive(symbol, period, "monthly", raw_dir, offline)]
    except DownloadError as exc:
        # Tylko brak ostatniego ZAKOŃCZONEGO miesiąca uzasadnia pobranie plików dziennych.
        if (not daily_fallback or month != _last_closed_month(date.today())
                or not (str(exc).startswith("404:") or (offline and str(exc).startswith("Brak pliku")))):
            raise
        print(f"Brak miesięcznego {symbol} {period}; przechodzę na archiwa dzienne.", file=sys.stderr)
        return [acquire_archive(symbol, day.isoformat(), "daily", raw_dir, offline)
                for day in _days_in_month(month)]
