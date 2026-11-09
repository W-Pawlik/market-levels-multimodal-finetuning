"""charts / reporting / audit."""
from __future__ import annotations


def _audit_markdown(report: dict) -> str:
    lines = ["# Audyt różnorodności OHLC", "", f"Przeanalizowano **{report['analyzed_count']} syntetycznych wykresów**. Status: diagnostyczny; profile i pilotaż niezatwierdzone.",
             "", "Nie generowano OHLC i nie zmieniano matematyki ani profili. Każdy reżim liczony jest oddzielnie; pełnego wykresu nie klasyfikuje pierwszy segment.",
             "", "## Metody", "", report["methodology"], "", "## Rozkłady", ""]
    for symbol, summary in report["symbols"].items():
        lines += [f"### {symbol}", "", f"Liczba: {summary['charts']}; seedy: `{summary['master_seeds']}`.",
                  f"Liczba faz 1/2/3: `{summary['regime_count']}`.",
                  "", "| Reżim deklarowany | Wystąpienia | Świece | Udział świec | Długość min/mediana/max |", "|---|---:|---:|---:|---|"]
        for kind, count in summary["regime_occurrences"].items():
            d = summary["regime_lengths"][kind]["distribution"]
            length = f"{d['min']}/{d['quantiles']['0.5']}/{d['max']}" if d else "brak"
            lines.append(f"| {kind} | {count} | {summary['candle_counts'][kind]} | {summary['candle_shares'][kind]:.2%} | {length} |")
        lines += ["", f"Najczęstsze przejścia: `{dict(list(summary['transitions'].items())[:8])}`.",
                  f"Konsolidacja → wybicie → trend: {summary['consolidation_breakout_trend']}.",
                  f"Zgodność znaku ruchu w segmentach trendu: `{summary['declared_segment_direction_agreement']}`.",
                  f"Rzeczywista kierunkowość segmentów według deklaracji: `{summary['declared_vs_observed_segments']}`.",
                  f"Ruch zaobserwowany (reguła diagnostyczna): `{summary['observed_motion']}`.",
                  f"Zmienność low/medium/high: `{summary['volatility_bands']}`.",
                  f"Progi treningowe: `{report['thresholds'][symbol]}`.", "",
                  "| Metryka | Min | Mediana | Max |", "|---|---:|---:|---:|"]
        for metric, d in summary["metric_distributions"].items():
            lines.append(f"| {metric} | {d['min']:.5g} | {d['quantiles']['0.5']:.5g} | {d['max']:.5g} |")
        comparison = report["training_reference"][symbol]
        ratio = comparison['window_std_dispersion_ratio']
        ratio_text = f"{ratio:.1%}" if ratio is not None else "brak danych syntetycznych"
        lines += ["", f"Zróżnicowanie std między oknami synthetic/train: {ratio_text}. Referencja: {comparison['window_count']} rozłącznych okien, jawna siatka od początku każdego ciągłego odcinka.", ""]
    lines += ["## Kontrola jakości i kompletność", "", f"Błędy wejść: {len(report['quality_errors'])}; grupy identycznych hashy: {len(report['duplicate_ohlc'])}.",
              f"Brakujące seedy: `{report['discovery']['missing_seeds']}`.",
              "Weryfikowane: 120 świec, UTC i kolejność 4h bez luk, OHLC dodatnie i skończone, seed/id, manifest, diagnostic, wariant full, zgodność osadzonych i dostępnych lokalnych profili refined/unapproved, hashe i udziały faz.",
              "W JSON: pełne listy błędów, brakujących indeksów, długości, sekwencji, pominiętych mniejszych partii, metryk i hashy wejść.",
              "", "## Ograniczenia i dobór próbek", "", *[f"- {finding}" for finding in report["findings"]],
              "", "Rekomendacja: przyszły dobór kontrolować osobno po symbolu, rzeczywistej zmienności, kierunkowości i pełnych sekwencjach faz. Obejrzeć skrajności i przypadki niezgodności deklaracji z ceną. Zachować rozdział pochodzenia w metadanych, kontrolować duplikaty oraz nakładanie okien. Nie ustalono nowych wag, limitów ani parametrów generatora.",
              "", "## Przykłady do obejrzenia", "", "Poniższe ID pochodzą z rzeczywiście wyrenderowanego pilotażu. Pełne metryki i mapowanie PNG → CSV: pilot/manifest.json.", ""]
    lines += [f"- `{r['png']}` — {r['symbol']}, {r['source']}, `{r['id']}`; {', '.join(r['selection_tags'])}." for r in report["pilot"]["images"]]
    return "\n".join(lines)+"\n"
