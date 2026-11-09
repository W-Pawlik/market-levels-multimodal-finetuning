"""Auxiliary per-example scoring for eight IDs; never a full-split report."""
from __future__ import annotations

import json
from pathlib import Path

from ...evaluation.io.inputs import read_references
from ...evaluation.domain.responses import parse_response
from ...evaluation.domain.scoring import score_example
from ...evaluation.domain.metrics import aggregate
from ...evaluation.protocol import dumps, PROTOCOL_SHA256, VERSION


def score_pilot(dataset: Path, model_output: Path) -> dict:
    selected = json.loads((model_output / 'selected-validation.json').read_text(encoding='utf-8'))
    expected = {r['id'] for r in selected}
    if len(selected) != 8 or len(expected) != 8 or any(r['split'] != 'validation' for r in selected):
        raise ValueError('Ocena pomocnicza wymaga dokładnie ośmiu ID validation')
    references, _, ledger = read_references(dataset, 'validation')
    by_id = {r.id: r for r in references}
    if not expected <= set(by_id):
        raise ValueError('Obce ID w pilotażu')
    results = {'kind': 'auxiliary_eight_images_not_full_validation', 'protocol': VERSION,
               'protocol_sha256': PROTOCOL_SHA256, 'selected_ids': sorted(expected), 'resolutions': {}}
    for folder in model_output.iterdir():
        predictions = folder / 'predictions.jsonl'
        if not folder.is_dir() or not predictions.is_file():
            continue
        rows = [json.loads(line) for line in predictions.read_text(encoding='utf-8').splitlines()]
        if len(rows) != 8 or {r['id'] for r in rows} != expected or any(set(r) != {'id', 'response'} for r in rows):
            raise ValueError('Niezgodne ID predykcji ośmiu obrazów')
        scored = [score_example(by_id[row['id']], parse_response(row['response'])) for row in rows]
        with (folder / 'auxiliary-per-example.jsonl').open('x', encoding='utf-8') as stream:
            stream.write(''.join(dumps(row) + '\n' for row in scored))
        results['resolutions'][folder.name] = aggregate(scored)
    ledger.verify()
    with (model_output / 'auxiliary-scores.json').open('x', encoding='utf-8') as stream:
        stream.write(dumps(results) + '\n')
    return results
