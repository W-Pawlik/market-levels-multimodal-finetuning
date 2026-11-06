"""CLI generatora: ustawienia, diagnostyka i jawne profile treningowe."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from ..data_processing.pipelines.synthetic import prepare_profiles, run
from ..data_processing.synthetic.settings import SYMBOLS, load_synthetic_settings
from ..data_processing.synthetic.v2_parameters import VARIANTS


def main() -> None:
    parser = argparse.ArgumentParser(description="Niezależne syntetyczne OHLC 4h; 120 świec, 12 kroków")
    parser.add_argument("--config", type=Path, default=Path("configs/experiment.json"))
    parser.add_argument("--count", type=int, help="Liczba przykładów NA KAŻDY wskazany instrument")
    parser.add_argument("--symbols", nargs="+", choices=SYMBOLS)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--profile", action="append", metavar="SYMBOL=PATH", help="Powtarzalne, nadpisuje profil instrumentu z JSON")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--diagnostic", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--generator-version", choices=("v1", "v2"))
    parser.add_argument("--v2-variant", choices=VARIANTS)
    parser.add_argument("--experiment-id")
    parser.add_argument("--dry-run", action="store_true", help="Walidacja ustawień i profili, bez zapisu")
    args = parser.parse_args()
    try:
        overrides = {key: getattr(args, key) for key in ("count", "symbols", "seed", "output", "diagnostic",
                                                       "generator_version", "v2_variant", "experiment_id")}
        if args.v2_variant is not None and args.generator_version != "v2":
            raise ValueError("--v2-variant wymaga jawnego --generator-version v2")
        if args.experiment_id is not None and args.generator_version != "v2":
            raise ValueError("--experiment-id wymaga jawnego --generator-version v2")
        if args.profile:
            base = load_synthetic_settings(args.config, **overrides)
            profiles = dict(base.profiles)
            for item in args.profile:
                symbol, separator, path = item.partition("=")
                if not separator or symbol not in SYMBOLS or not path.strip():
                    raise ValueError("--profile wymaga SYMBOL=PATH")
                profiles[symbol] = path
            overrides["profiles"] = profiles
        settings = load_synthetic_settings(args.config, **overrides)
        prepare_profiles(settings)
        if settings.diagnostic:
            print("UWAGA: tryb diagnostyczny; wyniki nie stanowią zatwierdzonego zbioru treningowego.", file=sys.stderr)
        if args.dry_run:
            print(json.dumps(settings.document(), ensure_ascii=False, indent=2))
            return
        destination = run(settings)
        print(f"Zapisano {settings.count * len(settings.symbols)} przykładów: {destination}")
    except (ValueError, OSError, TypeError) as exc:
        parser.exit(1, f"BŁĄD: {exc}\n")


if __name__ == "__main__":
    main()
