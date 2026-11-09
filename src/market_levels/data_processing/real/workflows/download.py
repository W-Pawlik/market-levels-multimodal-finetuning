"""data_processing / real / workflows / download."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from ....core.ohlc.model import CANDLE_DELTA, DataValidationError
from ....core.time.calendar import iter_months
from ..binance_vision.archives import acquire_month
from ..binance_vision.client import INTERVAL
from ..binance_vision.parsing import read_spot_klines_zip, verify_archive_period
from ...io.candles import write_candles_csv
from ....shared.json_io import write_json
from ....core.ohlc.validation import check_series


def run(start: str, end: str, output: Path, offline: bool,
        strict_gaps: bool, daily_fallback: bool, symbols: tuple[str, ...]) -> None:
    """Pozyskaj i zweryfikuj archiwa, następnie zapisz CSV, raporty i manifest."""
    months = list(iter_months(start, end))
    output = Path(output)
    raw_dir = output / "raw"
    processed = output / "processed"
    reports = output / "reports"
    processed.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    manifest = {"created_at_utc": datetime.now(timezone.utc).isoformat(),
                "start_month": start, "end_month": end, "interval": INTERVAL,
                "market": "spot", "sources": {}, "license_url":
                "https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md"}
    for symbol in symbols:
        candles = []
        entries = []
        for month in months:
            items = acquire_month(symbol, month, raw_dir, offline, daily_fallback)
            for path, metadata in items:
                data = read_spot_klines_zip(path)
                verify_archive_period(data, metadata["period"])
                candles.extend(data)
                metadata["candle_count"] = len(data)
                entries.append(metadata)
            print(f"{symbol} {month:%Y-%m}: OK", flush=True)
        report = check_series(candles)
        # Gdy brakuje pierwszej lub ostatniej świecy, sama kontrola odstępów
        # między rekordami nie wykryłaby luki. Liczymy również brzegi zakresu.
        expected_first = datetime(months[0].year, months[0].month, 1, tzinfo=timezone.utc)
        last_month = months[-1]
        following = date(last_month.year + (last_month.month == 12),
                         last_month.month % 12 + 1, 1)
        expected_last = datetime(following.year, following.month, 1,
                                 tzinfo=timezone.utc) - CANDLE_DELTA
        observed_first = datetime.fromisoformat(report["start"])
        observed_last = datetime.fromisoformat(report["end"])
        if observed_first < expected_first or observed_last > expected_last:
            raise DataValidationError(f"{symbol}: dane znajdują się poza zamówionym okresem")
        missing_head = int((observed_first - expected_first) / CANDLE_DELTA)
        missing_tail = int((expected_last - observed_last) / CANDLE_DELTA)
        report["missing_at_start"] = missing_head
        report["missing_at_end"] = missing_tail
        report["missing_total"] += missing_head + missing_tail
        final_path = processed / f"{symbol}_{INTERVAL}_{start}_{end}.csv"
        write_candles_csv(final_path, candles)
        report.update({"symbol": symbol, "market": "spot", "interval": INTERVAL,
                       "processed_csv": str(final_path), "archive_count": len(entries),
                       "coverage_note": "Nie uzupełniano brakujących świec; okna z lukami należy odrzucić."})
        write_json(reports / f"{symbol}_{start}_{end}.json", report)
        if strict_gaps and report["missing_total"]:
            raise DataValidationError(f"{symbol}: znaleziono {report['missing_total']} brakujących świec; raport zapisany")
        manifest["sources"][symbol] = entries
        print(f"{symbol}: {report['count']} świec; brakujących: {report['missing_total']}")
    write_json(reports / f"manifest_{start}_{end}.json", manifest)
