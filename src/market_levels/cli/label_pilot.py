"""Etykietowanie i weryfikacja 32 istniejących okien pilotażowych."""
import argparse
from pathlib import Path
import uuid

from ..labeling.pilot import run_labeling, verify_labeling


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--re-render", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.verify:
            if args.output is None:
                raise ValueError("--verify wymaga --output")
            verify_labeling(args.output, args.pilot, re_render=args.re_render)
            print("OK: 32 etykiety, diagnostyka, SHA-256" + (", identyczne PNG" if args.re_render else ""))
        else:
            if args.re_render:
                raise ValueError("--re-render wymaga --verify")
            output = args.output or Path("results/diagnostics")/("sr-"+uuid.uuid4().hex[:12])
            print(run_labeling(pilot=args.pilot, output=output))
    except (ValueError, OSError, ImportError, KeyError, TypeError) as error:
        parser.exit(1, f"Błąd etykietowania: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
