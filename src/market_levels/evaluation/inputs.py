"""Read-only binding to one split; reject incomplete or mixed prediction sets."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import hashlib
from pathlib import Path

from ..charts.diversity import SourceLedger
from ..data_processing.storage import read_candles_csv
from ..data_processing.synthetic.quality import canonical_hash
from ..datasets.packaging import verify_files, INSTRUCTION, INSTRUCTION_VERSION
from ..labeling.pilot import child, sha256
from .protocol import VERSION, dumps, loads
from .scoring import Reference, parse_response, final_atr


class InputError(ValueError):
    def __init__(self, problems: dict):
        self.problems = problems
        super().__init__(dumps(problems))


def read_references(dataset: Path, split: str = 'validation') -> tuple[list[Reference], dict, SourceLedger]:
    if split not in ('validation', 'test'):
        raise ValueError('Ewaluacja obsługuje wyłącznie validation lub jawnie wskazany test')
    dataset = dataset.resolve()
    ledger = SourceLedger()
    ledger.track(dataset/'manifest.json')
    manifest = verify_files(dataset)  # Hash bytes only; no generation or test-label analysis.
    fixture = manifest['kind'] == 'evaluation_fixture_dataset'
    if manifest['kind'] not in ('production_dataset', 'evaluation_fixture_dataset'):
        raise ValueError('Wymagany zbiór produkcyjny lub jawny ręczny fixture ewaluacji')
    if manifest.get('status') != ('manual_fixture' if fixture else 'complete'):
        raise ValueError('Niekompletny zbiór wejściowy')
    entries = manifest['entries']
    all_ids = {r['id']: r['split'] for r in entries}
    if len(all_ids) != len(entries) or manifest['count'] != len(entries):
        raise ValueError('Niezgodne ID/liczebności manifestu zbioru')
    selected = [r for r in entries if r['split'] == split]
    path = ledger.track(dataset/f'splits/{split}.jsonl')
    rows = [loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    if not selected or len({r['id'] for r in rows}) != len(rows) or {r['id'] for r in rows} != {r['id'] for r in selected}:
        raise ValueError('JSONL nie odpowiada kompletnemu oczekiwanemu splitowi')
    by_id = {r['id']: r for r in rows}
    references, bindings = [], []
    for entry in selected:
        row = by_id[entry['id']]
        if set(row) != {'id','split','image','instruction','answer'} or row['split'] != split or row['instruction'] != INSTRUCTION or row['image'] != entry['image']:
            raise ValueError('Niezgodny schemat, split lub instrukcja referencji')
        if entry['symbol'] not in ('BTCUSDT','ETHUSDT') or (not fixture and entry['source'] != 'real'):
            raise ValueError('Validation/test wymagają właściwego symbolu i realnego źródła')
        label_path = ledger.track(child(dataset, entry['label']))
        label = parse_response(label_path.read_text(encoding='utf-8'))
        answer = parse_response(dumps(row['answer']))
        if label.levels is None or answer.levels != label.levels:
            raise ValueError('Niepoprawna lub niezgodna etykieta referencyjna')
        csv = ledger.track(child(dataset, entry['ohlc']))
        candles = read_candles_csv(csv, source='evaluation-reference')
        atr = final_atr(candles)
        meta_path = ledger.track(child(dataset, entry['metadata']))
        meta = loads(meta_path.read_text(encoding='utf-8'))
        if (any(meta[k] != entry[k] for k in ('id','symbol','split','source')) or meta['ohlc_sha256'] != canonical_hash(candles)
                or meta['csv_sha256'] != sha256(csv) or meta['label_sha256'] != sha256(label_path)):
            raise ValueError('Niespójne metadane, CSV lub etykieta')
        image_hash = None
        if not fixture:
            image = ledger.track(child(dataset, entry['image']))
            image_hash = sha256(image)
            if meta['rendering']['png_sha256'] != image_hash or meta['rendering']['visualization']['target_lines'] is not False:
                raise ValueError('Niepoprawny obraz wejściowy lub overlay')
            if meta['label_audit']['atr'] != str(atr):
                raise ValueError('ATR nie odpowiada produkcyjnej referencji')
        references.append(Reference(row['id'], entry['symbol'], split, label.levels, atr))
        bindings.append({'id': row['id'], 'symbol': entry['symbol'], 'image_sha256': image_hash,
                         'instruction': row['instruction'], 'ohlc_sha256': canonical_hash(candles),
                         'label_sha256': sha256(label_path), 'reference': asdict(references[-1])})
    binding = {'dataset_manifest_sha256': sha256(dataset/'manifest.json'), 'split': split,
               'kind': 'technical_fixture' if fixture else 'production', 'all_ids': all_ids,
               'instruction_version': INSTRUCTION_VERSION, 'selected': bindings}
    binding['fingerprint'] = hashlib.sha256(dumps(binding).encode()).hexdigest()
    ledger.verify()
    return references, binding, ledger


def read_predictions(path: Path, references: list[Reference], binding: dict) -> dict[str, str]:
    expected = {r.id for r in references}
    records, malformed = [], []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        try:
            row = loads(line)
            if (not isinstance(row, dict) or set(row) != {'id','response'} or not isinstance(row['id'], str)
                    or not row['id'] or not isinstance(row['response'], str)):
                raise ValueError('Wiersz wymaga dokładnie tekstowych id i response')
            records.append(row)
        except (ValueError, RecursionError) as error:
            malformed.append({'line': number, 'reason': str(error)})
    counts = Counter(r['id'] for r in records)
    wrong_split = {identity: binding['all_ids'][identity] for identity in sorted(set(counts)-expected)
                   if identity in binding['all_ids']}
    problems = {'missing_ids': sorted(expected-set(counts)), 'unknown_ids': sorted(set(counts)-set(binding['all_ids'])),
                'wrong_split_ids': wrong_split, 'duplicate_ids': sorted(k for k, v in counts.items() if v > 1),
                'malformed_lines': malformed}
    if any(problems.values()):
        raise InputError(problems)
    return {r['id']: r['response'] for r in records}


def read_run_manifest(path: Path, binding: dict) -> dict:
    doc = loads(path.read_text(encoding='utf-8'))
    required = {'run_id','model_id','checkpoint_id','variant','protocol_version','instruction_version',
                'inference','prediction_kind','dataset_manifest_sha256','split'}
    if not isinstance(doc, dict) or not required <= set(doc):
        raise ValueError('Manifest predykcji nie zawiera wymaganych metadanych modelu i przebiegu')
    if any(not isinstance(doc[k], str) or not doc[k].strip() for k in required-{'inference'}):
        raise ValueError('Identyfikatory i wersje manifestu muszą być niepustym tekstem')
    if not isinstance(doc['inference'], dict) or doc['protocol_version'] != VERSION:
        raise ValueError('Niepoprawne ustawienia inferencji lub wersja protokołu')
    if any(doc[k] != binding[k] for k in ('dataset_manifest_sha256','split','instruction_version')):
        raise ValueError('Manifest predykcji dotyczy innego zbioru, splitu lub instrukcji')
    if doc['prediction_kind'] not in ('model', 'technical_fixture') or doc['variant'] not in ('base','finetuned','technical_fixture'):
        raise ValueError('Niepoprawny rodzaj predykcji lub wariant')
    if (binding['kind'] == 'technical_fixture') != (doc['prediction_kind'] == 'technical_fixture'):
        raise ValueError('Nie wolno przedstawiać fixture jako wyników rzeczywistego modelu')
    if (doc['prediction_kind'] == 'technical_fixture') != (doc['variant'] == 'technical_fixture'):
        raise ValueError('Niepoprawne oznaczenie wariantu technicznego')
    return doc
