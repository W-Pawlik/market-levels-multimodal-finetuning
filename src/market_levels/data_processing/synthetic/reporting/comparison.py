"""data_processing / synthetic / reporting / comparison."""
from __future__ import annotations

import json


def comparison_summary(report: dict) -> str:
    """Zwięzła tabela do terminala i udostępnienia autorowi pracy."""
    lines = [f"# {report['symbol']} — opisowe porównanie z treningiem",
             f"Porównanie: {report['comparison_id']}; podział: {report['split']['split_id']}",
             f"Generator: {report['synthetic_source'].get('generator_version', '1.0.0')}; wariant: {report['synthetic_source'].get('variant', 'v1')}; seed: {report['synthetic_source'].get('master_seed', 'brak w starszym raporcie')}",
             f"Okna rzeczywiste: {report['real']['window_count']}; syntetyczne: {report['synthetic']['window_count']}",
             "", "| Metryka | Rzeczywiste | Syntetyczne | Różnica S-R |",
             "| --- | ---: | ---: | ---: |"]
    def row(label, a, b):
        if a is None or b is None:
            show = lambda value: "nieokreślona" if value is None else f"{value:.8g}"
            lines.append(f"| {label} | {show(a)} | {show(b)} | nieokreślona |")
        else:
            lines.append(f"| {label} | {a:.8g} | {b:.8g} | {b-a:.8g} |")
    for name in report["real"]["pooled_observations"]:
        a, b = (report[side]["pooled_observations"][name] for side in ("real", "synthetic"))
        row(f"{name}: średnia", a["mean"], b["mean"])
        if name == "log_returns":
            for metric in ("std", "min", "max"):
                row(f"{name}: {metric}", a[metric], b[metric])
    for name in report["real"]["window_distributions"]:
        a, b = (report[side]["window_distributions"][name] for side in ("real", "synthetic"))
        for metric in ("mean", "std"):
            row(f"okna/{name}: {metric}", a[metric], b[metric])
    row("abs(r): korelacja lag 1", report["real"]["absolute_return_lag1"]["value"],
        report["synthetic"]["absolute_return_lag1"]["value"])
    lines.extend(["", "Pełne kwantyle i statystyki są w JSON. Reżimy wyłącznie syntetyczne:",
                  json.dumps(report["synthetic_source"]["regimes"]["occurrences"], ensure_ascii=False), ""])
    lines.extend(f"- {warning}" for warning in report["warnings"])
    return "\n".join(lines) + "\n"
