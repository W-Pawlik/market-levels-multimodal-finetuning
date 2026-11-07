"""Zatwierdzone reguły 3.2/3.4; bez dostępu do metadanych generatora."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
import json
from statistics import median

from ..core.candles import Candle
from ..data_processing.synthetic.quality import validate_values

VERSION = "sr-extreme-first-1.0.0"
# Stały kontekst uniezależnia wynik od kontekstu Decimal procesu wywołującego.
DECIMAL_CONTEXT = Context(prec=50, rounding=ROUND_HALF_UP)
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


def true_ranges(candles: list[Candle]) -> tuple[Decimal, ...]:
    return tuple(max(c.high-c.low, abs(c.high-candles[i-1].close),
                     abs(c.low-candles[i-1].close)) if i else c.high-c.low
                 for i, c in enumerate(candles))


def wilder_atr(tr: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    """Pierwszy element odpowiada świecy 13; ostatni końcowi okna."""
    if len(tr) < 14:
        raise ValueError("ATR(14) wymaga minimum 14 TR")
    values = [sum(tr[:14], Decimal(0))/14]
    for value in tr[14:]:
        values.append((values[-1]*13+value)/14)
    return tuple(values)


def find_extrema(candles: list[Candle]) -> tuple[Extremum, ...]:
    result = []
    for i in range(3, len(candles)-3):
        neighbors = candles[i-3:i] + candles[i+1:i+4]
        for kind, field in (("H", "high"), ("L", "low")):
            price = getattr(candles[i], field)
            if all((price > getattr(c, field) if kind == "H" else price < getattr(c, field)) for c in neighbors):
                result.append(Extremum(i, price, kind))
    return tuple(result)


def price_groups(extrema: tuple[Extremum, ...], delta: Decimal) -> list[tuple[Extremum, ...]]:
    groups: list[list[Extremum]] = []
    for item in sorted(extrema, key=lambda e: (e.price, e.index, e.kind)):
        if not groups or item.price-groups[-1][0].price > delta:
            groups.append([])
        groups[-1].append(item)
    return [tuple(group) for group in groups]


def independent_reactions(extrema: tuple[Extremum, ...], level: Decimal):
    """Priorytet H: cena−mediana, L: mediana−cena; remis: późniejsza, H przed L."""
    ordered = sorted(extrema, key=lambda e: (-(e.price-level if e.kind == "H" else level-e.price),
                                             -e.index, e.kind))
    kept, suppressed = [], []
    for item in ordered:
        blocker = next((e for e in kept if abs(e.index-item.index) < 5), None)
        if blocker is None:
            kept.append(item)
        else:
            suppressed.append({"extremum": asdict(item), "blocked_by": asdict(blocker),
                               "reason": "distance_less_than_5"})
    return tuple(sorted(kept, key=lambda e: (e.index, e.kind))), tuple(suppressed)


def rank_groups(groups: list[Group], last_close: Decimal) -> list[Group]:
    return sorted(groups, key=lambda g: (-len(g.reactions), -max(e.index for e in g.reactions),
                                        abs(g.level-last_close), g.level, g.id))


def select_groups(groups: list[Group], last_close: Decimal):
    selected, collisions = {"supports": [], "resistances": []}, []
    # Kolizje są rozstrzygane w kolejności rankingu, przed limitem trzech.
    seen = {}
    for group in rank_groups([g for g in groups if not g.reason], last_close):
        rounded = group.level.quantize(CENT, rounding=ROUND_HALF_UP)
        if rounded in seen:
            collisions.append({"side": group.side, "rounded_price": str(rounded),
                               "kept_group": seen[rounded], "discarded_group": group.id})
        elif len(selected[group.side]) < 3:
            seen[rounded] = group.id
            selected[group.side].append(group)
    return {side: tuple(kept) for side, kept in selected.items()}, tuple(collisions)


def label_window(candles: list[Candle]) -> LabelResult:
    if len(candles) != 120:
        raise ValueError("Etykietowanie wymaga dokładnie 120 świec")
    if any(not isinstance(getattr(c, k), Decimal) for c in candles for k in ("open", "high", "low", "close")):
        raise ValueError("Ceny muszą mieć typ Decimal")
    if validate_values(candles)["missing_total"]:
        raise ValueError("Wymagane kolejne świece 4h bez luk")
    with localcontext(DECIMAL_CONTEXT):
        tr = true_ranges(candles)
        atr = wilder_atr(tr)
        delta, last = atr[-1]/2, candles[-1].close
        extrema = find_extrema(candles)
        groups = []
        for identifier, members in enumerate(price_groups(extrema, delta)):
            level = median([e.price for e in members])
            reactions, suppressed = independent_reactions(members, level)
            side = "supports" if level < last else "resistances"
            reason = ("fewer_than_2_reactions" if len(reactions) < 2 else
                      "within_delta_of_close" if abs(level-last) <= delta else "")
            groups.append(Group(identifier, level, members, reactions, suppressed, side, reason))
        selected, collisions = select_groups(groups, last)
        chosen = {g.id for side in selected.values() for g in side}
        collided = {c["discarded_group"] for c in collisions}
        diagnosed = tuple(Group(g.id, g.level, g.extrema, g.reactions, g.suppressed, g.side,
                               g.reason or ("" if g.id in chosen else
                                            "rounding_collision" if g.id in collided else "ranking_limit")) for g in groups)
        return LabelResult(tr, atr, delta, last, extrema, diagnosed,
                           selected["supports"], selected["resistances"], collisions)
