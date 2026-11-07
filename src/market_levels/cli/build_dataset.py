"""Approval, pinned preflight, atomic production and readback verification."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from ..datasets.planning import SYMBOLS, build_plan
from ..datasets.packaging import publish_plan, run_smoke, verify_files, verify_smoke
from ..datasets.approval import approve_configured_profiles
from ..datasets.production import build_dataset, verify_dataset


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("approve", "preflight", "smoke", "build", "verify"))
    parser.add_argument("--config", type=Path, default=Path("configs/experiment.json"))
    parser.add_argument("--real-root", type=Path, default=Path("data/processed"))
    parser.add_argument("--btc-csv", type=Path)
    parser.add_argument("--eth-csv", type=Path)
    parser.add_argument("--pilot", type=Path, default=Path("results/diagnostics/dc-20261106-c/pilot"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--per-group", type=int, choices=(1, 2), default=2)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--audit", type=Path, default=Path("results/diagnostics/dc-20261106-c/AUDYT_ROZNORODNOSCI.json"))
    parser.add_argument("--decision-date")
    parser.add_argument("--check-sources", action="store_true")
    parser.add_argument("--allow-renderer-difference", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.mode in ("approve", "preflight"):
            paths = {s: override or args.real_root/f"{s}_4h_2020-01_2026-10.csv"
                     for s, override in zip(SYMBOLS, (args.btc_csv, args.eth_csv))}
            if args.mode == "approve":
                if not args.decision_date:
                    raise ValueError("approve wymaga jawnej daty decyzji --decision-date")
                approve_configured_profiles(args.config, paths, args.output, audit=args.audit, decision_date=args.decision_date)
                print(f"Zapisano nowe zatwierdzone profile: {args.output}. Zaktualizuj dataset_build.profiles w konfiguracji.")
                return 0
            plan = build_plan(args.config, paths)
            publish_plan(plan, args.output)
            print(json.dumps({"real_feasible": plan["real_feasible"], "groups": plan["groups"],
                              "synthetic_production_ready": plan["synthetic"]["production_ready"],
                              "problems": plan["problems"]}, ensure_ascii=False, indent=2))
            return 0 if plan["real_feasible"] else 2
        if args.mode == "build":
            if args.plan is None:
                raise ValueError("build wymaga --plan wskazującego aktualny preflight")
            build_dataset(args.config, args.plan, args.output)
            print(f"Opublikowano zweryfikowany zbiór: {args.output}")
        elif args.mode == "smoke":
            run_smoke(args.pilot, args.output, per_group=args.per_group)
            print(json.dumps(verify_smoke(args.output), ensure_ascii=False))
        else:
            manifest = verify_files(args.output)
            if manifest["kind"] == "production_dataset":
                report = verify_dataset(args.output, check_sources=args.check_sources,
                                        allow_renderer_difference=args.allow_renderer_difference)
            else:
                report = verify_smoke(args.output) if manifest["kind"] == "diagnostic_smoke" else {"verified": True, "kind": manifest["kind"]}
            print(json.dumps(report))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"Błąd budowy zbioru: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
