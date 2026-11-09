"""Oddzielna, ograniczona kalibracja zmienności istniejącego profilu v2."""
import argparse
from datetime import datetime
from pathlib import Path

from ..data_processing.synthetic.domain.profiles.v1 import profile_hash
from ..data_processing.synthetic.io.profiles import save_profile
from ..data_processing.synthetic.config.refinement import (
    REFINEMENT_VARIANTS,
    load_refinement_settings,
)
from ..data_processing.synthetic.workflows.refinement import refine_v2_volatility
from ..data_processing.synthetic.domain.parameters import SYMBOLS
from ..data_processing.synthetic.config.generation import load_synthetic_settings
from ..data_processing.io.chronology import load_chronological_split


def main() -> None:
    parser = argparse.ArgumentParser(description="volatility_refinement_v1: tylko phi i stacjonarne std; profil unapproved")
    parser.add_argument("--config", type=Path, default=Path("configs/experiment.json"))
    parser.add_argument("--symbol", required=True, choices=SYMBOLS)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--source-profile", required=True, type=Path)
    parser.add_argument("--source-sha256", help="Oczekiwany SHA-256 bajtów pliku profilu źródłowego")
    parser.add_argument("--variant", required=True, choices=REFINEMENT_VARIANTS)
    parser.add_argument("--start", required=True, type=datetime.fromisoformat)
    parser.add_argument("--end", required=True, type=datetime.fromisoformat)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Oblicz i zweryfikuj wszystkie próby, bez zapisu profilu")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise FileExistsError(f"Odmowa nadpisania profilu: {args.output}")
        settings = load_synthetic_settings(args.config, generator_version="v2", diagnostic=True,
                                           v2_variant=args.variant)
        profile = refine_v2_volatility(args.input, args.source_profile, symbol=args.symbol,
            variant=args.variant, start=args.start, end=args.end,
            split=load_chronological_split(args.config), settings=settings,
            search=load_refinement_settings(args.config), expected_source_sha256=args.source_sha256)
        if not args.dry_run:
            save_profile(args.output, profile)
        audit = profile["calibration"]
        print(f"{args.symbol}/{args.variant}: status=unapproved; parametry={profile['v2_parameters']}")
        print(f"Błąd: baseline={audit['baseline_loss']:.7g}, wybrany={audit['selected_loss']:.7g}")
        print(f"Profil SHA-256: {profile_hash(profile)}")
        print(f"{'Dry-run, bez zapisu' if args.dry_run else 'Zapisano'}: {args.output}")
    except (ValueError, TypeError, OSError) as exc:
        parser.exit(1, f"BŁĄD: {exc}\n")


if __name__ == "__main__":
    main()
