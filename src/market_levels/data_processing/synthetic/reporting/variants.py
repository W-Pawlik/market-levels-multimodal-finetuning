"""data_processing / synthetic / reporting / variants."""
from __future__ import annotations

import json


def variant_summary_markdown(report: dict) -> str:
    preferred = ("V1", "V2-base", "V2-bridge", "V2-tails", "V2-volatility", "V2-full",
                 "V2-full-original", "V2-full-refined", "V2-bridge_volatility-refined")
    order = [name for name in preferred if name in report["variants"]]
    order += sorted(set(report["variants"]) - set(order))
    lines = [f"# {report['symbol']}: V1 i warianty V2", "",
             "| Metryka | Realne | " + " | ".join(order) + " |",
             "| --- | ---: | " + " | ".join("---:" for _ in order) + " |"]
    fmt = lambda v: "nieokreślona" if v is None else f"{v:.7g}"
    for name, target in report["real_metrics"].items():
        lines.append("| " + name + " | " + fmt(target) + " | " + " | ".join(
            fmt(report["variants"][variant]["metrics"][name]["value"]) for variant in order) + " |")
    lines.extend(["", "| Wariant / metryka | Śr. błąd bezwzględny | Zmiana błędu względem V1 | Ocena kierunku |",
                  "| --- | ---: | ---: | --- |"])
    for label in order:
        for name, metric in report["variants"][label]["metrics"].items():
            lines.append(f"| {label}/{name} | {fmt(metric.get('mean_absolute_error'))} | "
                         f"{fmt(metric.get('absolute_error_change_vs_v1'))} | {metric.get('error_direction', 'undefined')} |")
    lines.extend(["", "| Wariant / metryka | Odchylenie standardowe między seedami |",
                  "| --- | ---: |"])
    for label in order:
        for name, metric in report["variants"][label]["metrics"].items():
            lines.append(f"| {label}/{name} | {fmt(metric.get('std_between_seeds'))} |")
    if "refinement_review" in report:
        lines.extend(["", "## Diagnostyka refinement", "", "```json",
                      json.dumps(report["refinement_review"], ensure_ascii=False, indent=2), "```"])
    lines.extend(["", "Liczba powtórzeń: " + ", ".join(f"{v}={report['variants'][v]['run_count']}" for v in order), ""])
    lines.extend("- " + warning for warning in report["warnings"])
    return "\n".join(lines) + "\n"
