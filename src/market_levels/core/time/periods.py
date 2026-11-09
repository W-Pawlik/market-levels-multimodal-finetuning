"""Explicit UTC periods and approved chronological splits."""
from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass

from ..ohlc.validation import validate_candle_timestamp
from ..ohlc.model import CANDLE_DELTA


def validate_period(start: datetime | None, end: datetime | None) -> None:
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        raise ValueError("Kalibracja wymaga jawnego początku i końca dozwolonego okresu")
    for stamp in (start, end):
        if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
            raise ValueError("Okres kalibracji wymaga UTC")
        validate_candle_timestamp(stamp, "calibration", 0)
    if start >= end:
        raise ValueError("Początek okresu musi poprzedzać koniec (granice włącznie)")


@dataclass(frozen=True)
class ChronologicalSplit:
    split_id: str
    periods: dict[str, tuple[datetime, datetime]]

    def require_training(self, start: datetime, end: datetime) -> None:
        """Wymagaj jawnego okresu mieszczącego się w zatwierdzonym treningu."""
        validate_period(start, end)
        first, last = self.periods["train"]
        if not first <= start < end <= last:
            raise ValueError(f"Zakres musi mieścić się w treningu {first.isoformat()} – {last.isoformat()}")

    def document(self) -> dict:
        return {"split_id": self.split_id, "status": "approved", "bounds": "inclusive",
                "timestamp_role": "candle_open_utc", "periods": {
                    name: {"start": start.isoformat(), "end": end.isoformat()}
                    for name, (start, end) in self.periods.items()}}


def split_from_document(options: dict) -> ChronologicalSplit:
    """Sprawdź ten sam podział w konfiguracji lub zapisanej metadanej profilu."""
    try:
        if set(options) != {"split_id", "status", "bounds", "timestamp_role", "periods"}:
            raise ValueError("Nieobsługiwane lub brakujące pola chronological_split")
        if (options["status"] != "approved" or options["bounds"] != "inclusive"
                or options["timestamp_role"] != "candle_open_utc"
                or not isinstance(options["split_id"], str) or not options["split_id"].strip()):
            raise ValueError("Wymagany zatwierdzony podział z granicami otwarcia świecy UTC włącznie")
        if set(options["periods"]) != {"train", "validation", "test"}:
            raise ValueError("Wymagane okresy train, validation i test")
        periods = {}
        for name in ("train", "validation", "test"):
            period = options["periods"][name]
            if set(period) != {"start", "end"}:
                raise ValueError(f"Okres {name} wymaga dokładnie start i end")
            start, end = (datetime.fromisoformat(period[k]) for k in ("start", "end"))
            validate_period(start, end)
            periods[name] = (start, end)
        if (periods["train"][1] + CANDLE_DELTA != periods["validation"][0]
                or periods["validation"][1] + CANDLE_DELTA != periods["test"][0]):
            raise ValueError("Okresy muszą być rozłączne i kolejne z krokiem 4h")
        return ChronologicalSplit(options["split_id"], periods)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"Niepoprawna sekcja chronological_split: {exc}") from exc
