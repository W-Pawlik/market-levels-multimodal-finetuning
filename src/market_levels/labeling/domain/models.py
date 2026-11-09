"""labeling / domain / models."""
from __future__ import annotations

import json
from decimal import Decimal, localcontext
from dataclasses import dataclass, asdict

from ...core.numeric.atr import DECIMAL_CONTEXT


VERSION = "sr-extreme-first-1.0.0"


CENT = Decimal("0.01")


@dataclass(frozen=True)
class Extremum:
    index: int
    price: Decimal
    kind: str


@dataclass(frozen=True)
class Group:
    id: int
    level: Decimal
    extrema: tuple[Extremum, ...]
    reactions: tuple[Extremum, ...]
    suppressed: tuple[dict, ...]
    side: str
    reason: str


@dataclass(frozen=True)
class LabelResult:
    tr: tuple[Decimal, ...]
    atr: tuple[Decimal, ...]
    delta: Decimal
    last_close: Decimal
    extrema: tuple[Extremum, ...]
    groups: tuple[Group, ...]
    supports: tuple[Group, ...]
    resistances: tuple[Group, ...]
    collisions: tuple[dict, ...]

    def target_json(self) -> str:
        """Liczby JSON zapisane bez pośredniej konwersji Decimal → float."""
        with localcontext(DECIMAL_CONTEXT):
            def array(groups):
                return "[" + ", ".join(format(g.level.quantize(CENT), ".2f") for g in groups) + "]"
            return '{"supports": ' + array(self.supports) + ', "resistances": ' + array(self.resistances) + '}\n'

    def diagnostics(self) -> dict:
        # Decimal jako tekst tylko w diagnostyce, aby zachować wszystkie cyfry.
        return json.loads(json.dumps(dict(asdict(self), algorithm_version=VERSION,
                                        decimal_precision=50, index_base=0), default=str))
