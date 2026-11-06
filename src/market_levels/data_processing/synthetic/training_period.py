"""Odczyt zatwierdzonego podziału; granice eksperymentu są tylko w JSON."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

from ...core.candles import CANDLE_DELTA
from .calibration import validate_period


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


def load_chronological_split(path: Path) -> ChronologicalSplit:
    """Wczytaj i sprawdź granice, bez implementowania podziału zbiorów."""
    try:
        options = json.loads(Path(path).read_text(encoding="utf-8-sig"))["chronological_split"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Niepoprawna sekcja chronological_split: {exc}") from exc
    return split_from_document(options)


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
