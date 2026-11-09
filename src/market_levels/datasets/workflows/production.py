"""datasets / workflows / production."""
from __future__ import annotations

import json
import platform
import uuid
from pathlib import Path

from ...shared.integrity import SourceLedger, sha256_file as sha256
from ...charts.io.rendering import render_window
from ...charts.config import RENDERER_VERSION
from ...shared.publication import publication_workspace, publish_directory
from ...data_processing.io.candles import read_candles_csv, write_candles_csv
from ...shared.json_io import write_json
from ...data_processing.synthetic.domain.profiles.v1 import profile_hash
from ...data_processing.synthetic.domain.generation.dispatch import generate_example
from ...core.ohlc.identity import canonical_hash
from ...data_processing.synthetic.io.profiles import prepare_profiles
from ...labeling.domain.algorithm import label_window
from ...labeling.domain.models import VERSION
from ..domain.audit import audit_dataset
from ..config import SYMBOLS, SPLITS
from .planning import build_plan, require_production_ready
from ..domain.examples import (
    INSTRUCTION_VERSION,
    json_line,
    names_for,
    synthetic_id,
    source_metadata,
)
from ...shared.manifests import seal, verify_files
from ..io.outputs import production_output
from .verification import _settings, _check_sources, verify_dataset


def build_dataset(config: Path, preflight: Path, output: Path, *, progress=print) -> Path:
    output = production_output(output)
    if verify_files(preflight)['kind'] != 'preflight_plan':
        raise ValueError('Wymagany opublikowany preflight')
    plan = json.loads((preflight/'plan.json').read_text(encoding='utf-8'))
    _check_sources(plan)
    require_production_ready(config)
    progress('Kontrola aktualności zatwierdzonego planu', flush=True)
    fresh = build_plan(config, {s: Path(r['path']) for s, r in plan['real_sources'].items()})
    if json.loads(json.dumps(fresh)) != plan or not plan['real_feasible'] or not plan['synthetic']['production_ready']:
        raise ValueError('Plan jest nieaktualny lub niegotowy do produkcji')
    ledger = SourceLedger()
    ledger.track(config)
    ledger.track(preflight/'manifest.json')
    sources = {s: read_candles_csv(ledger.track(Path(r['path'])), source=r['path']) for s, r in plan['real_sources'].items()}
    historical_hashes = set()
    for name in plan['source_integrity']['sha256']:
        if Path(name).name == 'manifest.json':
            doc = json.loads(Path(name).read_text(encoding='utf-8'))
            historical_hashes.update(r['ohlc_sha256'] for r in doc.get('examples', []))
    output.parent.mkdir(parents=True, exist_ok=True)
    with publication_workspace(output.parent, prefix='.dataset-') as tmp:
        stage = tmp/'batch'
        for folder in ('images', 'ohlc', 'labels', 'metadata', 'splits', 'profiles'):
            (stage/folder).mkdir(parents=True)
        (stage/'config.json').write_bytes(config.read_bytes())
        write_json(stage/'plan.json', plan)
        profiles, settings = {}, {}
        for symbol in SYMBOLS:
            path = ledger.track(Path(plan['synthetic']['profiles'][symbol]['path']))
            (stage/f'profiles/{symbol}.json').write_bytes(path.read_bytes())
            settings[symbol] = _settings(stage/'config.json', stage/'profiles', symbol)
            profiles[symbol] = prepare_profiles(settings[symbol])[symbol]
        records = []
        for r in plan['selected_real']:
            cs = [sources[r['symbol']][i] for i in r['csv_record_indices']]
            record = dict(r, source_csv=plan['real_sources'][r['symbol']]['path'],
                          source_csv_sha256=plan['real_sources'][r['symbol']]['sha256'])
            records.append((record, cs))
        progress(f'Wybrano {len(records)} rzeczywistych okien; generacja syntetyków', flush=True)
        for item in plan['synthetic']['planned_examples']:
            symbol, seed = item['symbol'], item['seed']
            example = generate_example(symbol, seed, profiles[symbol], settings[symbol])
            if canonical_hash(example.candles) in historical_hashes:
                raise ValueError('Nowy syntetyk jest duplikatem historycznego OHLC')
            generator_meta = {k: v for k, v in example.metadata.items() if k not in ('calibration_profile', 'configuration')}
            record = dict(item, source='synthetic', profile_id=profile_hash(profiles[symbol]),
                          generator_metadata=generator_meta, start_utc=None, end_utc=None)
            record['id'] = synthetic_id(symbol, seed, canonical_hash(example.candles), record['profile_id'])
            records.append((record, example.candles))
        entries, metas, seen, png_seen = [], [], set(), set()
        lines = {s: [] for s in SPLITS}
        for i, (record, candles) in enumerate(records):
            digest = canonical_hash(candles)
            if digest in seen:
                raise ValueError('Duplikat OHLC w zbiorze')
            seen.add(digest)
            names = names_for(record['id'])
            result = label_window(candles)
            rendering = render_window(candles, stage/names['image'])
            if rendering['png_sha256'] in png_seen:
                raise ValueError('Duplikat PNG w zbiorze')
            png_seen.add(rendering['png_sha256'])
            write_candles_csv(stage/names['ohlc'], candles)
            (stage/names['label']).write_text(result.target_json(), encoding='utf-8')
            meta = source_metadata(record, candles, result, rendering)
            meta.update(csv_sha256=sha256(stage/names['ohlc']), label_sha256=sha256(stage/names['label']))
            write_json(stage/names['metadata'], meta)
            entries.append(dict(id=record['id'], split=record['split'], symbol=record['symbol'], source=record['source'], **names))
            metas.append(meta)
            lines[record['split']].append(json_line(record['id'], record['split'], names['image'], result.target_json()))
            if (i+1) % 50 == 0 or i+1 == len(records):
                progress(f'Renderowanie i etykietowanie: {i+1}/{len(records)}', flush=True)
        for split in SPLITS:
            (stage/f'splits/{split}.jsonl').write_text(''.join(lines[split]), encoding='utf-8')
        write_json(stage/'audit.json', audit_dataset(metas))
        _check_sources(plan)
        write_json(stage/'SOURCE_INTEGRITY.json', ledger.verify())
        import matplotlib
        write_json(stage/'run.json', {'run_id': str(uuid.uuid4()), 'status': 'production',
            'python': platform.python_version(), 'implementation': platform.python_implementation(),
            'platform': platform.platform(), 'matplotlib': matplotlib.__version__,
            'renderer_version': RENDERER_VERSION, 'algorithm_version': VERSION,
            'instruction_version': INSTRUCTION_VERSION, 'preflight_manifest_sha256': sha256(preflight/'manifest.json')})
        seal(stage, {'kind': 'production_dataset', 'schema_version': 1, 'status': 'complete',
                     'count': len(entries), 'entries': entries,
                     'split_counts': {s: len(lines[s]) for s in SPLITS}})
        progress('Pełna kontrola odczytu z dysku i ponownego odtworzenia wszystkich przykładów', flush=True)
        verify_dataset(stage, check_sources=True, progress=progress)
        publish_directory(stage, output)
    return output
