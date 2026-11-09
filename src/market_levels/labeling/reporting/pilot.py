"""labeling / reporting / pilot."""
from __future__ import annotations

import json
from collections import Counter

from ..domain.models import LabelResult


def summarize(results: list[tuple[dict, LabelResult]]) -> dict:
    return {"count": len(results),
            "support_counts": dict(sorted(Counter(len(r.supports) for _, r in results).items())),
            "resistance_counts": dict(sorted(Counter(len(r.resistances) for _, r in results).items())),
            "without_supports": sum(not r.supports for _, r in results),
            "without_resistances": sum(not r.resistances for _, r in results),
            "without_either": sum(not r.supports and not r.resistances for _, r in results),
            "extrema_before": sum(len(r.extrema) for _, r in results),
            "reactions_after": sum(len(g.reactions) for _, r in results for g in r.groups),
            "rounding_collisions": sum(len(r.collisions) for _, r in results),
            "rejection_reasons": dict(Counter(g.reason for _, r in results for g in r.groups if g.reason))}


def report_markdown(results, summary):
    lines = ["# Etykietowanie pilotażu 3.4", "", "Status: diagnostyczny, oczekuje ręcznej oceny autora. Obrazy z liniami nie są wejściami VLM.",
             "", "Algorytm: ścisłe ekstrema 3+3, końcowy Wilder ATR(14), delta=ATR/2, wspólne grupy H/L o pełnej rozpiętości ≤ delta. Mediana wszystkich ekstremów przed filtrowaniem.",
             "Najpierw zachowujemy najsilniejsze ekstremum (H: cena−mediana, L: mediana−cena), usuwając reakcje bliższe niż 5 świec. Remis wygrywa późniejsza świeca, następnie H przed L. To może dać mniej reakcji niż maksymalizacja ich liczby.",
             "Ranking: liczba reakcji, ostatnia reakcja, odległość od Close, cena i ID. Kolizje po ROUND_HALF_UP rozstrzyga ranking przed limitem trzech; pominięcie jest jawne w diagnostyce.",
             "Obliczenia Decimal: stały kontekst 50 cyfr znaczących, bez zaokrąglania do centów przed serializacją odpowiedzi. ATR jest rekurencją skończonej precyzji (nie dokładną liczbą wymierną). Indeksy diagnostyki od zera.",
             "", "## Wyniki", "", "```json", json.dumps(summary, ensure_ascii=False, indent=2), "```", "",
             "Liczba reakcji po filtrowaniu obejmuje wszystkie grupy, także później odrzucone jako poziomy.", "",
             "| Plik | Symbol / źródło | Wsparcia | Opory | Ekstrema → reakcje |", "|---|---|---|---|---|"]
    for i, (record, result) in enumerate(results):
        target = json.loads(result.target_json())
        lines.append(f"| {i:03d} | {record['symbol']} / {record['source']} | {target['supports']} | {target['resistances']} | {len(result.extrema)} → {sum(len(g.reactions) for g in result.groups)} |")
    lines += ["", "## Przykłady do ręcznej kontroli", ""]
    picks = [min(range(len(results)), key=lambda i: len(results[i][1].supports)+len(results[i][1].resistances)),
             max(range(len(results)), key=lambda i: len(results[i][1].supports)+len(results[i][1].resistances)),
             max(range(len(results)), key=lambda i: len(results[i][1].extrema)-sum(len(g.reactions) for g in results[i][1].groups)),
             max(range(len(results)), key=lambda i: sum({e.kind for e in g.extrema} == {"H", "L"} for g in results[i][1].groups))]
    for i, reason in zip(picks, ("najmniej poziomów", "najwięcej poziomów", "najwięcej odrzuconych bliskich reakcji", "najwięcej grup mieszanych H/L")):
        lines.append(f"- `overlays/{i:03d}.png`, `diagnostics/{i:03d}.json`: {reason}; ID `{results[i][0]['id']}`.")
    lines += ["", "Nie przeprowadzono niezależnej eksperckiej oceny poziomów. Pilotaż celowo pokrywa różne sytuacje i nie jest reprezentatywną próbą rynku. Brak poziomów stanowi wynik reguł; nie dopasowywano parametrów do obrazu. Nie zmieniano generatora, statusów profili ani oryginałów; nie generowano OHLC, nie pobierano danych i nie wykonywano etapu 3.5.", ""]
    return "\n".join(lines)
