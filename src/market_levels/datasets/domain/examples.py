"""Stable example identities, exact JSONL, instructions and metadata."""
from __future__ import annotations

import hashlib
import json

from ...charts.domain.metrics import window_metrics
from ...core.ohlc.identity import canonical_hash
from ...data_processing.synthetic.domain.parameters import V2_VERSION
from ...labeling.domain.models import VERSION


INSTRUCTION_VERSION = "pl-sr-v1"


INSTRUCTION = ("Przeanalizuj przedstawiony wykres świecowy. Wskaż maksymalnie trzy poziomy wsparcia "
               "i trzy poziomy oporu. Zwróć wyłącznie obiekt JSON z polami supports i resistances, "
               "zawierającymi listy wartości cenowych.")


def _metadata(record: dict, candles: list, result, rendering: dict, identity: str) -> dict:
    answer = json.loads(result.target_json())
    return {"id": identity, "symbol": record["symbol"], "source": record["source"],
            "split": None, "diagnostic_only": True, "source_metadata": record,
            "start_utc": candles[0].timestamp.isoformat() if record["source"] == "real" else None,
            "end_utc": candles[-1].timestamp.isoformat() if record["source"] == "real" else None,
            "generator_version": V2_VERSION if record["source"] == "synthetic" else None,
            "profile_id": record.get("profile_sha256"), "seed": record.get("seed"),
            "master_seed": record.get("master_seed"), "ohlc_sha256": canonical_hash(candles),
            "support_count": len(answer["supports"]), "resistance_count": len(answer["resistances"]),
            "metrics": window_metrics(candles), "rendering": rendering,
            "algorithm_version": VERSION, "instruction_version": INSTRUCTION_VERSION,
            "source_reproduction": "Pinned source pilot metadata, copied exact OHLC; same renderer and labeling versions. No overlays."}


def json_line(identity: str, split: str | None, image: str, answer: str) -> str:
    fields = {'id': identity, 'split': split, 'image': image, 'instruction': INSTRUCTION}
    return json.dumps(fields, ensure_ascii=False)[:-1]+', "answer": '+answer.strip()+'}\n'


def names_for(identity: str) -> dict:
    return {'image': f'images/{identity}.png', 'ohlc': f'ohlc/{identity}.csv',
            'label': f'labels/{identity}.json', 'metadata': f'metadata/{identity}.json'}


def synthetic_id(symbol: str, seed: int, digest: str, profile_id: str) -> str:
    return hashlib.sha256(f'{symbol}:train:synthetic:{seed}:{digest}:{profile_id}'.encode()).hexdigest()[:24]


def source_metadata(record: dict, candles: list, result, rendering: dict) -> dict:
    answer = json.loads(result.target_json())
    return dict(record, ohlc_sha256=canonical_hash(candles), answer=answer,
                support_count=len(answer['supports']), resistance_count=len(answer['resistances']),
                metrics=window_metrics(candles), rendering=rendering, algorithm_version=VERSION,
                instruction_version=INSTRUCTION_VERSION, diagnostic_only=False,
                label_audit={'atr': str(result.atr[-1]), 'delta': str(result.delta),
                    'rounding_collisions': len(result.collisions), 'extrema_count': len(result.extrema)})


def _example_line(identity: str, image: str, answer: str) -> str:
    """Serialize a diagnostic example with an explicit null split."""
    return json_line(identity, None, image, answer)
