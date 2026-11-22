"""Generate thesis figures 5.1 and 5.2 exclusively from saved test results."""
from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from market_levels.evaluation.domain.models import Levels
from market_levels.evaluation.protocol import dumps
from market_levels.evaluation.reporting.figures import comparison_figure, save_figure
from market_levels.evaluation.workflows.visualization import load_visualization_examples


# These assertions describe the author's selected cases; drawing uses source values.
CASES = (
    ("9f49cdba6e4d2d0cff453353", "ETHUSDT", "rysunek_5_1_ethusdt_porownanie",
     (("3217.56", "3150.39"), ("3473.75", "3549.07", "3611.85")),
     (("3250.00", "3280.00", "3150.00"), ("3450.00", "3550.00")), (4, 1, 1, "0.8")),
    ("9ae321c8cccbc677d118c424", "BTCUSDT", "rysunek_5_2_btcusdt_blad_skali",
     (("86510.95", "85230.32"), ("89477.61", "90530.32", "88274.17")),
     (("8650.00", "8750.00", "8550.00"), ("8950.00", "9050.00", "9100.00")), (0, 6, 5, "0")),
)


def validate_case(example: dict, case: tuple) -> None:
    identity, symbol, _, reference, predicted, metrics = case
    ref = example["reference"]
    def levels(values):
        return Levels(*(tuple(Decimal(v) for v in side) for side in values))
    score = example["score"]["scores"]["0.5"]
    if (ref.id != identity or ref.symbol != symbol or ref.split != "test"
            or ref.levels != levels(reference) or example["predicted"] != levels(predicted)
            or tuple(score[k] for k in ("tp", "fp", "fn", "example_f1"))
            != (*metrics[:3], Decimal(metrics[3]))):
        raise ValueError(f"Przykład nie odpowiada zleceniu autora: {identity}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/datasets/ds35-800-20261107-a"))
    parser.add_argument("--predictions", type=Path,
                        default=Path("results/vlm46-final-test/finetuned-nf4/predictions.jsonl"))
    parser.add_argument("--evaluation", type=Path,
                        default=Path("results/evaluation/vlm46-final-test-finetuned-nf4"))
    parser.add_argument("--output", type=Path, default=Path("docs/thesis/figures"))
    parser.add_argument("--verification", type=Path, default=Path("docs/thesis/verification/generation"))
    args = parser.parse_args()
    # Preflight every destination before writing even the verification previews.
    for stem in (c[2] for c in CASES):
        for suffix in (".png", ".svg"):
            if (args.output/(stem+suffix)).exists():
                raise FileExistsError(f"Odmowa nadpisania: {args.output/(stem+suffix)}")
    if args.verification.exists():
        raise FileExistsError(f"Wybierz nowy katalog weryfikacji: {args.verification}")
    for source in (args.dataset, args.predictions.parent, args.evaluation):
        for target in (args.output, args.verification):
            if target.resolve().is_relative_to(source.resolve()):
                raise ValueError("Wyjście musi być poza chronionymi źródłami")
    examples, report = load_visualization_examples(args.dataset, args.predictions, args.evaluation,
                                                  [c[0] for c in CASES], args.verification)
    for example, case in zip(examples, CASES):
        validate_case(example, case)
    outputs = []
    for example, case in zip(examples, CASES):
        fig = comparison_figure(example["candles"], example["reference"].levels,
                                example["predicted"], scale_error=case[1] == "BTCUSDT")
        paths = save_figure(fig, args.output/case[2])
        outputs.extend(str(p.resolve()) for p in paths)
    report["outputs"] = outputs
    report["png_dpi"] = 300
    (args.verification/"verification.json").write_text(dumps(report)+"\n", encoding="utf-8")
    for path in outputs:
        print(path)
    print("Zgodność poziomów, metryk i odtworzonych PNG: OK")


if __name__ == "__main__":
    main()
