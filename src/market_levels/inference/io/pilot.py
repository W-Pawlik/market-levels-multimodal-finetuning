"""Bounded selection: validation for inference, train for the one-step check."""
from __future__ import annotations

import json
from pathlib import Path

from ...datasets.domain.examples import INSTRUCTION
from ...evaluation.protocol import loads
from ...shared.integrity import sha256_file
from ...shared.manifests import verify_files
from ...shared.paths import child
from ..domain.inputs import ImageInput, spread_indices


def select_examples(dataset: Path, *, split: str = 'validation') -> tuple[list[ImageInput], list[dict], dict]:
    # Reject before opening any test file, including a test manifest.
    if split not in ('validation', 'train'):
        raise ValueError('Diagnostyka VLM nie dopuszcza zbioru testowego')
    manifest = verify_files(dataset)
    if manifest.get('kind') != 'production_dataset' or manifest.get('status') != 'complete':
        raise ValueError('Wymagany kompletny produkcyjny zbiór')
    rows = [loads(line) for line in (dataset / f'splits/{split}.jsonl').read_text(encoding='utf-8').splitlines()]
    entries = [e for e in manifest['entries'] if e['split'] == split]
    by_id = {r['id']: r for r in rows}
    if len(by_id) != len(rows) or set(by_id) != {e['id'] for e in entries}:
        raise ValueError('Niezgodne ID splitu')
    for entry in entries:
        row = by_id[entry['id']]
        if (set(row) != {'id', 'split', 'image', 'instruction', 'answer'} or row['split'] != split
                or row['instruction'] != INSTRUCTION or row['image'] != entry['image']):
            raise ValueError('Niezgodny format produkcyjnego JSONL')
    picked = []
    for symbol in ('BTCUSDT', 'ETHUSDT'):
        group = []
        for entry in entries:
            if entry['symbol'] != symbol:
                continue
            if split == 'validation' and entry['source'] != 'real':
                raise ValueError('Walidacja musi być rzeczywista')
            meta = json.loads(child(dataset, entry['metadata']).read_text(encoding='utf-8'))
            if meta['rendering']['visualization']['target_lines'] is not False:
                raise ValueError('Overlay nie może być wejściem VLM')
            group.append((meta['start_utc'] or '', entry['id'], entry))
        group.sort(key=lambda item: (item[0], item[1]))
        indices = spread_indices(len(group), 4) if split == 'validation' else [0, len(group) - 1]
        for index in indices:
            start, identity, entry = group[index]
            picked.append({'id': identity, 'split': split, 'symbol': symbol, 'start_utc': start,
                           'chronological_rank': index, 'group_count': len(group), 'image': entry['image'],
                           'image_sha256': sha256_file(child(dataset, entry['image']))})
    inputs = [ImageInput(p['id'], child(dataset, p['image']), by_id[p['id']]['instruction']) for p in picked]
    # Return targets only to the training caller. Inference never receives them.
    targets = {p['id']: by_id[p['id']]['answer'] for p in picked} if split == 'train' else {}
    return inputs, picked, targets


def write_json(path: Path, payload) -> None:
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def append_response(path: Path, identity: str, response: str) -> None:
    if not isinstance(identity, str) or not identity or not isinstance(response, str):
        raise ValueError('Predykcja wymaga tekstowych id i response')
    with path.open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps({'id': identity, 'response': response}, ensure_ascii=False) + '\n')
