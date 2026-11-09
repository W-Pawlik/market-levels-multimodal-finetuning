"""Bezpieczna koordynacja istniejących CLI; bez nowej matematyki OHLC."""
from __future__ import annotations

import argparse
from pathlib import Path

from ..experiments.refinement.workflows.runner import run_comparison


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', required=True, choices=('check', 'smoke', 'full'))
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--inputs', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', type=Path)
    parser.add_argument('--fresh-seeds', action='store_true', help='Oddzielna próba czterech grup: 20261201/20261211')
    run_comparison(parser.parse_args())


if __name__ == '__main__':
    main()
