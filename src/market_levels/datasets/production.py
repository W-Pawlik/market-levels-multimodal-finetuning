"""Atomic production dataset assembled from a pinned, approved preflight."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import platform
import tempfile
import uuid

from ..charts.diversity import SourceLedger, window_metrics
from ..charts.renderer import render_window, require_short_path, VISUALIZATION, RENDERER_VERSION
from ..data_processing.staging import publication_workspace, publish_directory
from ..data_processing.storage import read_candles_csv, write_candles_csv, write_json
from ..data_processing.synthetic.calibration import load_profile, profile_hash
from ..data_processing.synthetic.dispatch import generate_example
from ..data_processing.synthetic.generator import example_seed
from ..data_processing.synthetic.quality import canonical_hash, validate_synthetic
from ..data_processing.synthetic.training_period import load_chronological_split, split_from_document
from ..data_processing.pipelines.synthetic import prepare_profiles
from ..data_processing.windows import Window, validate_selection
from ..labeling.algorithm import label_window, VERSION
from ..labeling.pilot import child, sha256
from .audit import audit_dataset
from .planning import SYMBOLS, SPLITS, build_plan, synthetic_settings, require_production_ready, load_plan_config
from .packaging import INSTRUCTION, INSTRUCTION_VERSION, seal, verify_files


def json_line(identity: str, split: str, image: str, answer: str) -> str:
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


def production_output(output: Path) -> Path:
    output = output.resolve()
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'Odmowa nadpisania: {output}')
    if Path('data/datasets').resolve() not in output.parents:
        raise ValueError('Produkcja wymaga nowego katalogu pod data/datasets')
    for base in (output, output.parent/('.dataset-'+'x'*8)/'batch'):
        for name in ('metadata/'+'x'*24+'.json', 'profiles/BTCUSDT.json', 'SOURCE_INTEGRITY.json'):
            require_short_path(base/name)
    return output


def _settings(config: Path, profile_root: Path, symbol: str):
    return replace(synthetic_settings(config, symbol, output=Path('data/synthetic/dataset35')),
                   profiles={symbol: str(profile_root/f'{symbol}.json')})


def _check_sources(plan: dict) -> None:
    for name, digest in plan['source_integrity']['sha256'].items():
        if sha256(Path(name)) != digest:
            raise ValueError(f'Źródło planu zmieniło się: {name}')


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


def verify_dataset(output: Path, *, check_sources: bool = False, allow_renderer_difference: bool = False,
                   progress=print) -> dict:
    """Independent readback, re-label, re-render and re-generate every example."""
    manifest = verify_files(output)
    if (manifest['kind'] != 'production_dataset' or manifest['schema_version'] != 1 or manifest['status'] != 'complete'):
        raise ValueError('Niekompletny produkcyjny zbiór')
    config, plan = output/'config.json', json.loads((output/'plan.json').read_text(encoding='utf-8'))
    doc = load_plan_config(config)
    if doc['dataset_build']['targets'] != plan['targets'] or not plan['real_feasible'] or not plan['synthetic']['production_ready']:
        raise ValueError('Niezgodny plan i konfiguracja')
    split = split_from_document(plan['chronological_split'])
    if split.document() != load_chronological_split(config).document():
        raise ValueError('Niezgodna chronologia')
    real_plan = {r['id']: r for r in plan['selected_real']}
    synthetic_plan = {(r['symbol'], r['seed']): r for r in plan['synthetic']['planned_examples']}
    if len(real_plan) != len(plan['selected_real']) or len(synthetic_plan) != len(plan['synthetic']['planned_examples']):
        raise ValueError('Duplikaty planu')
    profiles, settings = {}, {}
    for symbol in SYMBOLS:
        settings[symbol] = _settings(config, output/'profiles', symbol)
        profiles[symbol] = prepare_profiles(settings[symbol])[symbol]
        pinned = plan['synthetic']['profiles'][symbol]
        if profile_hash(profiles[symbol]) != pinned['profile_id'] or sha256(output/f'profiles/{symbol}.json') != pinned['file_sha256']:
            raise ValueError('Niezgodny profil produkcyjny')
    expected_files = {'config.json', 'plan.json', 'audit.json', 'run.json', 'SOURCE_INTEGRITY.json'}
    expected_files.update(f'profiles/{s}.json' for s in SYMBOLS)
    expected_files.update(f'splits/{s}.jsonl' for s in SPLITS)
    metas, windows, seen, ids, pngs, seeds, real_seen = [], [], set(), set(), set(), set(), set()
    lines = {s: [] for s in SPLITS}
    counts, renderer_differences = Counter(), []
    original_sources = {}
    if check_sources:
        _check_sources(plan)
        original_sources = {s: read_candles_csv(Path(r['path']), source=r['path']) for s, r in plan['real_sources'].items()}
    with tempfile.TemporaryDirectory(prefix='ds-full-') as tmp:
        for i, entry in enumerate(manifest['entries']):
            identity = entry['id']
            if not isinstance(identity, str) or len(identity) != 24 or any(c not in '0123456789abcdef' for c in identity) or identity in ids:
                raise ValueError('Niepoprawny/duplikat ID')
            ids.add(identity)
            names = names_for(identity)
            if set(entry) != {'id', 'symbol', 'source', 'split', *names} or any(entry[k] != v for k, v in names.items()):
                raise ValueError('Niezgodne ścieżki przykładów')
            expected_files.update(names.values())
            meta = json.loads(child(output, names['metadata']).read_text(encoding='utf-8'))
            symbol, source, part = entry['symbol'], entry['source'], entry['split']
            if symbol not in SYMBOLS or source not in ('real', 'synthetic') or part not in SPLITS or (source == 'synthetic' and part != 'train'):
                raise ValueError('Niedozwolony symbol, źródło lub split')
            cs = read_candles_csv(child(output, names['ohlc']), source='dataset-readback')
            result = label_window(cs)
            digest = canonical_hash(cs)
            if digest in seen:
                raise ValueError('Duplikat OHLC')
            seen.add(digest)
            png_hash = sha256(child(output, names['image']))
            if png_hash in pngs:
                raise ValueError('Duplikat PNG')
            pngs.add(png_hash)
            if source == 'real':
                r = real_plan.get(identity)
                if r is None:
                    raise ValueError('Okno nie należy do zatwierdzonego planu')
                real_seen.add(identity)
                expected_record = dict(r, source_csv=plan['real_sources'][symbol]['path'], source_csv_sha256=plan['real_sources'][symbol]['sha256'])
                window = Window(symbol, part, tuple(r['csv_record_indices']), tuple(cs))
                windows.append(window)
                if window.document() != r or (check_sources and canonical_hash([original_sources[symbol][j] for j in r['csv_record_indices']]) != digest):
                    raise ValueError('Okno nie odpowiada źródłu lub planowi')
            else:
                seed = meta['seed']
                item = synthetic_plan.get((symbol, seed))
                if item is None or seed in seeds or seed != example_seed(doc['dataset_build']['synthetic_master_seed'], symbol, item['index']):
                    raise ValueError('Kolizja lub niezgodny seed')
                seeds.add(seed)
                generated = generate_example(symbol, seed, profiles[symbol], settings[symbol])
                if canonical_hash(generated.candles) != digest or [c.timestamp for c in generated.candles] != [c.timestamp for c in cs]:
                    raise ValueError('Syntetyk nie odtwarza się z zatwierdzonego profilu/seeda')
                gm = {k: v for k, v in generated.metadata.items() if k not in ('calibration_profile', 'configuration')}
                expected_record = dict(item, source='synthetic', profile_id=profile_hash(profiles[symbol]),
                    generator_metadata=gm, start_utc=None, end_utc=None,
                    id=synthetic_id(symbol, seed, digest, profile_hash(profiles[symbol])))
                validate_synthetic(generated.candles, gm['regimes'], seed)
            # PNG dimensions and format independently checked before exact renderer replay.
            import struct
            with child(output, names['image']).open('rb') as png:
                header = png.read(24)
            if header[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', header[16:24]) != (1024, 768):
                raise ValueError('Niepoprawny PNG 1024x768')
            target = Path(tmp)/f'{i:04d}.png'
            rendered = render_window(cs, target)
            if rendered['png_sha256'] != png_hash:
                if not allow_renderer_difference:
                    raise ValueError('Niezgodny odtworzony PNG; sprawdź środowisko renderera')
                renderer_differences.append(identity)
            target.unlink()
            rendering = meta['rendering']
            if (rendering['png_sha256'] != png_hash or rendering['ohlc_sha256'] != digest or
                    rendering['visualization'] != VISUALIZATION or rendering['renderer_version'] != RENDERER_VERSION or rendering['candle_count'] != 120):
                raise ValueError('Niedozwolone renderowanie; obrazy z liniami nie mogą być wejściem')
            expected = source_metadata(expected_record, cs, result, rendering)
            expected.update(csv_sha256=sha256(child(output, names['ohlc'])), label_sha256=sha256(child(output, names['label'])))
            if expected != meta or expected_record['id'] != identity or any(meta[k] != entry[k] for k in ('symbol', 'split', 'source')):
                raise ValueError('Niezgodne metadane i pochodzenie')
            if child(output, names['label']).read_text(encoding='utf-8') != result.target_json():
                raise ValueError('Niezgodna etykieta')
            lines[part].append(json_line(identity, part, names['image'], result.target_json()))
            counts[(part, source, symbol)] += 1
            metas.append(meta)
            if (i+1) % 100 == 0:
                progress(f'Zweryfikowano {i+1}/{manifest["count"]}', flush=True)
    validate_selection(windows, split)
    if real_seen != set(real_plan) or len(seeds) != len(synthetic_plan):
        raise ValueError('Niekompletny plan przykładów')
    for part in SPLITS:
        if (output/f'splits/{part}.jsonl').read_text(encoding='utf-8') != ''.join(lines[part]):
            raise ValueError('Niezgodny JSONL splitu')
        for source in ('real', 'synthetic'):
            for symbol in SYMBOLS:
                if counts[(part, source, symbol)] != doc['dataset_build']['targets'][part][source][symbol]:
                    raise ValueError('Niezgodne dokładne liczebności')
    actual_counts = {s: len(lines[s]) for s in SPLITS}
    if manifest['count'] != len(metas) or manifest['split_counts'] != actual_counts or set(manifest['files']) != expected_files:
        raise ValueError('Niekompletny manifest produkcyjny')
    if json.loads((output/'audit.json').read_text(encoding='utf-8')) != json.loads(json.dumps(audit_dataset(metas))):
        raise ValueError('Niezgodny audyt')
    return {'verified': True, 'count': len(metas), 'split_counts': actual_counts,
            'synthetic_regenerated': len(seeds), 'png_replayed': len(metas),
            'renderer_differences': renderer_differences, 'source_csv_checked': check_sources,
            'manifest_sha256': sha256(output/'manifest.json')}
