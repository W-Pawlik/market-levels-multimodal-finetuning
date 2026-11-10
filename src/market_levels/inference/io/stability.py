"""Read only train or validation; deterministic length strata for 32 train IDs."""
import json
from collections import Counter
from pathlib import Path

from ...datasets.domain.examples import INSTRUCTION
from ...evaluation.protocol import loads, dumps
from ...shared.integrity import sha256_file
from ...shared.manifests import verify_files
from ...shared.paths import child
from ..domain.inputs import ImageInput, spread_indices


def select_training(entries: list[dict]) -> list[dict]:
    if any(e['split'] != 'train' for e in entries) or len({e['id'] for e in entries}) != len(entries):
        raise ValueError('Training requires unique train-only records')
    groups = []
    for symbol in ('BTCUSDT', 'ETHUSDT'):
        for source in ('real', 'synthetic'):
            group = sorted((e for e in entries if e['symbol'] == symbol and e['source'] == source),
                           key=lambda e: (e['answer_tokens'], e['level_count'], e['id']))
            groups.append([group[i] for i in spread_indices(len(group), 8)])
    # Each optimizer step contains all four symbol/source strata.
    return [group[i] for i in range(8) for group in groups]


def read_split(dataset: Path, split: str, tokenizer=None):
    if split not in ('train', 'validation'):
        raise ValueError('Test is forbidden in this experiment')
    manifest = verify_files(dataset)
    if manifest['kind'] != 'production_dataset' or manifest['status'] != 'complete':
        raise ValueError('Complete production dataset required')
    rows = [loads(line) for line in (dataset / f'splits/{split}.jsonl').read_text(encoding='utf-8').splitlines()]
    entries = [e for e in manifest['entries'] if e['split'] == split]
    by_id = {r['id']: r for r in rows}
    if len(by_id) != len(rows) or set(by_id) != {e['id'] for e in entries}:
        raise ValueError('Split IDs differ')
    selected = []
    for entry in entries:
        row = by_id[entry['id']]
        if (set(row) != {'id', 'split', 'image', 'instruction', 'answer'} or row['split'] != split
                or row['image'] != entry['image'] or row['instruction'] != INSTRUCTION):
            raise ValueError('Invalid production row')
        meta = json.loads(child(dataset, entry['metadata']).read_text(encoding='utf-8'))
        image = child(dataset, entry['image'])
        digest = sha256_file(image)
        if (meta['rendering']['visualization']['target_lines'] is not False
                or meta['rendering']['png_sha256'] != digest):
            raise ValueError('Invalid image or overlay')
        # Count records without exposing OHLC to the model.
        if len(child(dataset, entry['ohlc']).read_text(encoding='utf-8').splitlines()) != 121:
            raise ValueError('Expected exactly 120 candles')
        record = {**entry, 'image_sha256': digest}
        if split == 'train':
            if tokenizer is None:
                raise ValueError('Training selection requires the pinned tokenizer')
            record['answer_tokens'] = len(tokenizer.encode(dumps(row['answer']), add_special_tokens=False))
            record['level_count'] = sum(len(v) for v in row['answer'].values())
        selected.append(record)
    if split == 'train':
        selected = select_training(selected)
    else:
        if len(selected) != 36 or Counter(e['symbol'] for e in selected) != {'BTCUSDT': 18, 'ETHUSDT': 18}:
            raise ValueError('Expected full balanced 36-image validation')
        if any(e['source'] != 'real' for e in selected):
            raise ValueError('Validation must be real')
        selected.sort(key=lambda e: (e['symbol'], e['id']))
    inputs = [ImageInput(e['id'], child(dataset, e['image']), INSTRUCTION) for e in selected]
    targets = {e['id']: by_id[e['id']]['answer'] for e in selected} if split == 'train' else {}
    return inputs, selected, targets
