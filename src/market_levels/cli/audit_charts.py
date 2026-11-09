"""Audit existing V2-full-refined and render a small train-only pilot."""
from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from ..charts.workflows.audit import run_audit


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/experiment.json"))
    parser.add_argument("--synthetic-root", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--btc-csv", type=Path, required=True)
    parser.add_argument("--eth-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selection-seed", type=int, default=20261106)
    parser.add_argument("--per-group", type=int, choices=(6,7,8), default=8)
    args = parser.parse_args(argv)
    try:
        output = args.output or Path("results/diagnostics")/("dc-"+uuid.uuid4().hex[:12])
        result = run_audit(synthetic_root=args.synthetic_root,
                           real_csv={"BTCUSDT": args.btc_csv, "ETHUSDT": args.eth_csv},
                           config=args.config, output=output, selection_seed=args.selection_seed,
                           per_group=args.per_group)
    except (ValueError, OSError, ImportError) as error:
        parser.exit(1, f"Błąd audytu/renderera: {error}\n")
    print(f"Diagnostyczny audyt i pilotaż (unapproved): {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
