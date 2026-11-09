"""Load the approved chronological split from configuration."""
from __future__ import annotations

from pathlib import Path

from ...core.time.periods import ChronologicalSplit, split_from_document
from ...shared.configuration import read_configuration
from ...shared.integrity import SourceLedger


def load_chronological_split(path: Path, *, ledger: SourceLedger | None = None) -> ChronologicalSplit:
    """Wczytaj i sprawdź granice, bez implementowania podziału zbiorów."""
    try:
        options = read_configuration(path, ledger=ledger)["chronological_split"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Niepoprawna sekcja chronological_split: {exc}") from exc
    return split_from_document(options)
