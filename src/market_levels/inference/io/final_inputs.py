"""Manifest-only final input loader; never parses test answers, metadata or OHLC."""
import hashlib
from collections import Counter
from pathlib import Path

from ...datasets.domain.examples import INSTRUCTION, INSTRUCTION_VERSION
from ...shared.integrity import sha256_file
from ...shared.manifests import verify_files
from ...shared.paths import child
from ...evaluation.protocol import dumps
from ..domain.inputs import ImageInput


def read_test_images(dataset: Path, expected_manifest: str):
    if sha256_file(dataset/'manifest.json') != expected_manifest:
        raise ValueError('Frozen dataset manifest SHA-256 mismatch')
    manifest = verify_files(dataset)  # Other splits and labels are hashed as opaque bytes only.
    if manifest.get('kind') != 'production_dataset' or manifest.get('status') != 'complete':
        raise ValueError('Complete frozen production dataset required')
    entries = manifest['entries']
    if len({e['id'] for e in entries}) != len(entries) or len(entries) != manifest['count']:
        raise ValueError('Duplicate or missing dataset IDs')
    if Counter(e['split'] for e in entries) != {'train': 698, 'validation': 36, 'test': 66}:
        raise ValueError('Frozen 698/36/66 split required')
    selected = sorted((e for e in entries if e['split'] == 'test'), key=lambda e: (e['symbol'], e['id']))
    if Counter(e['symbol'] for e in selected) != {'BTCUSDT': 33, 'ETHUSDT': 33} or any(e['source'] != 'real' for e in selected):
        raise ValueError('Expected 33 real test images per instrument')
    records, inputs = [], []
    from PIL import Image
    for e in selected:
        image = child(dataset, e['image'])
        with Image.open(image) as opened:
            if opened.format != 'PNG' or opened.size != (1024, 768):
                raise ValueError('Original PNG 1024x768 required')
            opened.verify()
        records.append({'id': e['id'], 'symbol': e['symbol'], 'image': e['image'],
                        'image_sha256': manifest['files'][e['image']]})
        inputs.append(ImageInput(e['id'], image, INSTRUCTION))
    binding = {'dataset_manifest_sha256': expected_manifest, 'split': 'test',
               'instruction_version': INSTRUCTION_VERSION,
               'instruction_sha256': hashlib.sha256(INSTRUCTION.encode('utf-8')).hexdigest(), 'images': records}
    # This is NOT the evaluator's reference-dependent fingerprint.
    binding['image_input_fingerprint'] = hashlib.sha256(dumps(binding).encode('utf-8')).hexdigest()
    return inputs, binding
