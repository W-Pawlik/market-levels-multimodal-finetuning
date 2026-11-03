"""Wczytywanie ustawień działającego etapu z konfiguracji eksperymentu."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .core.periods import iter_months
from .data_processing.real.binance_vision.client import INTERVAL, SYMBOLS


class ConfigurationError(ValueError):
    """Brakująca, niepoprawna lub nieobsługiwana konfiguracja."""


@dataclass(frozen=True)
class DownloadSettings:
    """Parametry pozyskiwania danych; pozostałe etapy nie są jeszcze aktywne."""

    start: str
    end: str
    symbols: tuple[str, ...]
    output: Path
    offline: bool
    strict_gaps: bool
    daily_fallback: bool


def load_download_settings(path: Path) -> DownloadSettings:
    """Wczytaj JSON, sprawdź obsługiwane źródło i zwróć ustawienia pobierania.

    Ścieżka output jest względna wobec katalogu uruchomienia, jak argument CLI.
    Pola przyszłych etapów pozostają w JSON, ale nie sterują tym pipeline.
    """
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ConfigurationError(f"Nie można wczytać konfiguracji {path}: {exc}") from exc
    try:
        if not isinstance(document, dict):
            raise ValueError("konfiguracja musi być obiektem JSON")
        for key, supported in (("source", "Binance Vision"), ("market", "spot"), ("interval", INTERVAL)):
            if document.get(key) != supported:
                raise ValueError(f"{key}: obecnie obsługiwana wartość to {supported!r}")
        symbols = document.get("symbols")
        if (not isinstance(symbols, list) or not symbols
                or any(not isinstance(symbol, str) or symbol not in SYMBOLS for symbol in symbols)):
            raise ValueError(f"symbols: oczekiwano niepustej listy symboli spośród {', '.join(SYMBOLS)}")
        start = document.get("history_start_month")
        end = document.get("history_end_month")
        if not isinstance(start, str) or not isinstance(end, str):
            raise ValueError("history_start_month i history_end_month muszą być tekstem YYYY-MM")
        list(iter_months(start, end))
        options = document.get("download", {})
        if not isinstance(options, dict):
            raise ValueError("download musi być obiektem JSON")
        output = options.get("output", "data")
        if not isinstance(output, str) or not output.strip():
            raise ValueError("download.output musi być niepustą ścieżką tekstową")
        flags = {}
        for key, default in (("offline", False), ("strict_gaps", False), ("daily_fallback", True)):
            value = options.get(key, default)
            if not isinstance(value, bool):
                raise ValueError(f"download.{key} musi mieć wartość true albo false")
            flags[key] = value
        return DownloadSettings(start, end, tuple(symbols), Path(output), **flags)
    except ValueError as exc:
        raise ConfigurationError(f"Niepoprawna konfiguracja {path}: {exc}") from exc
