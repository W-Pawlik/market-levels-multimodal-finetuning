"""Read full train JSONL, verify sealed input bytes, load pixels on demand."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from ...datasets.domain.examples import INSTRUCTION
from ...evaluation.domain.responses import parse_response
from ...evaluation.protocol import loads, dumps
from ...inference.domain.inputs import ImageInput, conversation
from ...modeling.io.runtime import prepare_input
from ...shared.integrity import sha256_file
from ...shared.manifests import verify_files
from ...shared.paths import child
from ..domain.masking import assistant_labels


def read_train(dataset: Path, split='train'):
    if split != 'train':
        raise ValueError('Training only; validation/test forbidden')
    manifest = verify_files(dataset)
    if manifest['kind'] != 'production_dataset' or manifest['status'] != 'complete' or manifest['count'] != 800:
        raise ValueError('Complete approved 800-example dataset required')
    entries = [e for e in manifest['entries'] if e['split'] == 'train']
    if len({e['id'] for e in manifest['entries']}) != 800:
        raise ValueError('Duplicate dataset IDs')
    if len(entries) != 698 or Counter(e['source'] for e in entries) != {'real': 258, 'synthetic': 440}:
        raise ValueError('Expected 698 train (258 real, 440 synthetic)')
    rows = [loads(s) for s in (dataset / 'splits/train.jsonl').read_text(encoding='utf-8').splitlines()]
    by_id = {r['id']: r for r in rows}
    if len(by_id) != len(rows) or set(by_id) != {e['id'] for e in entries}:
        raise ValueError('Train count/IDs differ')
    for e in entries:
        row = by_id[e['id']]
        if (set(row) != {'id', 'split', 'image', 'instruction', 'answer'} or row['split'] != 'train'
                or row['instruction'] != INSTRUCTION or row['image'] != e['image']
                or parse_response(dumps(row['answer'])).levels is None):
            raise ValueError('Invalid training row')
        meta = loads(child(dataset, e['metadata']).read_text(encoding='utf-8'))
        if meta['rendering']['visualization']['target_lines'] is not False:
            raise ValueError('Overlay forbidden')
        child(dataset, row['image'])
    # Full sealed manifest binds all PNG/config/JSONL bytes; no test OHLC/label parsing.
    return by_id, {'manifest_sha256': sha256_file(dataset / 'manifest.json'),
                   'train_sha256': sha256_file(dataset / 'splits/train.jsonl'), 'ids': sorted(by_id)}


def make_batch(row, dataset, processor, runtime, maximum):
    from PIL import Image
    with Image.open(child(dataset, row['image'])) as original:
        if original.size != (1024, 768):
            raise ValueError('Original 1024x768 PNG required')
        image = original.convert('RGB')
    try:
        item = ImageInput(row['id'], child(dataset, row['image']), row['instruction'])
        messages = conversation(item, image)
        prompt, _ = prepare_input(processor, messages, runtime['models']['qwen3-vl'])
        messages.append({'role': 'assistant', 'content': [{'type': 'text', 'text': dumps(row['answer'])}]})
        batch, info = prepare_input(processor, messages, runtime['models']['qwen3-vl'], generation=False)
        batch['labels'] = assistant_labels(batch['input_ids'], prompt['input_ids'])
        supervised = batch['input_ids'][0, prompt['input_ids'].shape[-1]:].tolist()
        end = processor.tokenizer.convert_tokens_to_ids('<|im_end|>')
        if end not in supervised or info['input_tokens'] > maximum:
            raise ValueError('Missing assistant end marker or sequence too long; no truncation')
        info.update(id=row['id'], supervised_tokens=int((batch['labels'] != -100).sum()))
        return batch, info
    finally:
        image.close()
