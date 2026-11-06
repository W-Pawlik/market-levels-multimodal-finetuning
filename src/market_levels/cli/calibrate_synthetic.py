"""Kalibracja empiryczna z jawnym okresem ograniczonym do treningu."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from ..data_processing.synthetic.calibration import calibrate_csv, profile_hash, save_profile
from ..data_processing.synthetic.settings import SYMBOLS
from ..data_processing.synthetic.settings import load_synthetic_settings
from ..data_processing.synthetic.calibration_v2 import calibrate_v2_csv, load_calibration_v2_settings
from ..data_processing.synthetic.training_period import load_chronological_split


def main() -> None:
    parser = argparse.ArgumentParser(description="Kalibracja OHLC tylko na zatwierdzonym treningu; profil unapproved")
    parser.add_argument("--config", type=Path, default=Path("configs/experiment.json"))
    parser.add_argument("--symbol", required=True, choices=SYMBOLS)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--start", required=True, type=datetime.fromisoformat)
    parser.add_argument("--end", required=True, type=datetime.fromisoformat)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Oblicz i sprawdź profil, bez zapisu")
    parser.add_argument("--generator-version", choices=("v1", "v2"), default="v1")
    args = parser.parse_args()
    try:
        split = load_chronological_split(args.config)
        split.require_training(args.start, args.end)
        if args.output.exists():
            raise FileExistsError(f"Profil już istnieje (odmowa nadpisania): {args.output}")
        if args.generator_version == "v2":
            settings = load_synthetic_settings(args.config, generator_version="v2", diagnostic=True)
            profile = calibrate_v2_csv(args.input, args.symbol, start=args.start, end=args.end, split=split,
                                      settings=settings, search=load_calibration_v2_settings(args.config))
        else:
            profile = calibrate_csv(args.input, args.symbol, allowed_start=args.start, allowed_end=args.end)
        # Dodatkowa metadana w źródle zachowuje istniejący schemat profilu v1.
        profile["source"]["chronological_split"] = split.document()
        if not args.dry_run:
            save_profile(args.output, profile)
        print(f"{args.symbol}: status={profile['status']}, obserwacje={profile['observations']}, "
              f"pominięte przejścia={profile['skipped_noncontiguous_transitions']}, "
              f"sigma_4h={profile['generator_parameters']['sigma_4h']:.8g}")
        print(f"Podział: {split.split_id}; okres otwarcia UTC włącznie: "
              f"{profile['period']['allowed_start']} – {profile['period']['allowed_end']}")
        print(f"Profil SHA-256: {profile_hash(profile)}")
        if args.generator_version == "v2":
            print(f"V2: parametry={profile['v2_parameters']}, błąd kalibracyjny={profile['calibration']['selected_loss']:.6g}")
        print(f"{'Dry-run, bez zapisu' if args.dry_run else 'Zapisano'}: {args.output}")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"BŁĄD: {exc}\n")


if __name__ == "__main__":
    main()
