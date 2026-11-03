"""Argumenty CLI pobierania danych i prezentacja błędów."""
from __future__ import annotations

import argparse
from pathlib import Path

from ..configuration import load_download_settings
from ..core.periods import iter_months
from ..data_processing.pipelines.download import run
from ..data_processing.real.binance_vision.client import DownloadError, SYMBOLS, _remote_url


def main() -> None:
    """Uruchom pobieranie danych z argumentami użytkownika."""
    parser = argparse.ArgumentParser(description="Archiwa Binance Vision spot 4h, SHA-256 i walidacja OHLC")
    parser.add_argument("--config", type=Path, default=Path("configs/experiment.json"),
                        help="Plik JSON (domyślnie configs/experiment.json); argumenty CLI nadpisują jego ustawienia")
    parser.add_argument("--start", help="YYYY-MM; domyślnie history_start_month z konfiguracji")
    parser.add_argument("--end", help="YYYY-MM; domyślnie history_end_month z konfiguracji")
    parser.add_argument("--output", type=Path, help="Katalog wyników; domyślnie download.output z konfiguracji")
    parser.add_argument("--symbols", nargs="+", choices=SYMBOLS, help="Domyślnie symbols z konfiguracji")
    parser.add_argument("--offline", action=argparse.BooleanOptionalAction, default=None,
                        help="Tylko wcześniej pobrane archiwa; domyślnie ustawienie konfiguracji")
    parser.add_argument("--strict-gaps", action=argparse.BooleanOptionalAction, default=None,
                        help="Przerwij przy brakujących świecach; domyślnie ustawienie konfiguracji")
    parser.add_argument("--daily-fallback", action=argparse.BooleanOptionalAction, default=None,
                        help="Dopuść fallback dzienny; domyślnie ustawienie konfiguracji")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        settings = load_download_settings(args.config)
        start = args.start if args.start is not None else settings.start
        end = args.end if args.end is not None else settings.end
        symbols = tuple(args.symbols) if args.symbols is not None else settings.symbols
        output = args.output if args.output is not None else settings.output
        offline = args.offline if args.offline is not None else settings.offline
        strict_gaps = args.strict_gaps if args.strict_gaps is not None else settings.strict_gaps
        daily_fallback = args.daily_fallback if args.daily_fallback is not None else settings.daily_fallback
        months = list(iter_months(start, end))
        if args.dry_run:
            for symbol in symbols:
                for month in months:
                    print(_remote_url(symbol, month.strftime("%Y-%m")))
            print(f"Archiwa miesięczne do pobrania: {len(months) * len(symbols)} (plus pliki CHECKSUM)")
            return
        run(start, end, output, offline, strict_gaps, daily_fallback, symbols)
    except (DownloadError, ValueError, OSError) as exc:
        parser.exit(1, f"BŁĄD: {exc}\n")


if __name__ == "__main__":
    main()
