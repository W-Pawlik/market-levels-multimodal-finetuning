"""CLI porównania faktycznie zapisanych syntetyków z oknami treningowymi."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from ..data_processing.pipelines.compare_synthetic import build_comparison, comparison_summary, save_comparison
from ..data_processing.synthetic.settings import SYMBOLS
from ..data_processing.synthetic.training_period import load_chronological_split


def main() -> None:
    parser = argparse.ArgumentParser(description="Opisowe porównanie syntetycznych OHLC z oknami treningowymi")
    parser.add_argument("--config", type=Path, default=Path("configs/experiment.json"))
    parser.add_argument("--symbol", required=True, choices=SYMBOLS)
    parser.add_argument("--real-csv", required=True, type=Path)
    parser.add_argument("--synthetic-manifest", required=True, type=Path)
    parser.add_argument("--start", required=True, type=datetime.fromisoformat)
    parser.add_argument("--end", required=True, type=datetime.fromisoformat)
    parser.add_argument("--window-count", type=int, default=60)
    parser.add_argument("--selection-seed", type=int, default=20261106)
    parser.add_argument("--output", type=Path, default=Path("data/synthetic/comparisons"))
    parser.add_argument("--dry-run", action="store_true", help="Oblicz i sprawdź raport bez zapisu")
    args = parser.parse_args()
    try:
        split = load_chronological_split(args.config)
        report = build_comparison(symbol=args.symbol, real_csv=args.real_csv, synthetic_manifest=args.synthetic_manifest,
            start=args.start, end=args.end, count=args.window_count, selection_seed=args.selection_seed, split=split)
        if args.dry_run:
            print(comparison_summary(report))
            print("Dry-run: bez zapisu raportów")
        else:
            directory = save_comparison(args.output, report)
            print(comparison_summary(report))
            print(f"Raport JSON: {directory / (args.symbol + '_comparison.json')}")
            print(f"Podsumowanie: {directory / (args.symbol + '_summary.md')}")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"BŁĄD: {exc}\n")


if __name__ == "__main__":
    main()
