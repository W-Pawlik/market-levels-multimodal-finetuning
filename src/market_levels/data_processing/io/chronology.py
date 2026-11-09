"""Load the approved chronological split from configuration."""
from __future__ import annotations

import json
from pathlib import Path

from ...core.time.periods import ChronologicalSplit, split_from_document


def load_chronological_split(path: Path) -> ChronologicalSplit:
    """Wczytaj i sprawdź granice, bez implementowania podziału zbiorów."""
    try:
        options = json.loads(Path(path).read_text(encoding="utf-8-sig"))["chronological_split"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Niepoprawna sekcja chronological_split: {exc}") from exc
    return split_from_document(options)
