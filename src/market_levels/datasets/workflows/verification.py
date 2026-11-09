"""Independent dataset readback, re-labeling, rendering and regeneration."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from dataclasses import replace
from collections import Counter

from ...charts.io.rendering import render_window
from ...charts.config import VISUALIZATION, RENDERER_VERSION
from ...data_processing.io.candles import read_candles_csv
from ...core.ohlc.identity import canonical_hash
from ...labeling.domain.algorithm import label_window
from ...labeling.domain.models import VERSION
from ...shared.paths import child
from ...shared.integrity import sha256_file as sha256
from ...shared.configuration import configuration_snapshot
from ..config import SYMBOLS, synthetic_settings, SPLITS, load_plan_config
from ...data_processing.synthetic.domain.profiles.v1 import profile_hash
from ...data_processing.synthetic.domain.generation.dispatch import generate_example
from ...data_processing.synthetic.domain.generation.seeds import example_seed
from ...data_processing.synthetic.domain.quality import validate_synthetic
from ...data_processing.io.chronology import load_chronological_split
from ...core.time.periods import split_from_document
from ...data_processing.synthetic.io.profiles import prepare_profiles
from ...data_processing.windows.domain.models import Window
from ...data_processing.windows.domain.candidates import validate_selection
from ..domain.audit import audit_dataset, summarize
from ...shared.manifests import verify_files
from ..domain.examples import (
    INSTRUCTION_VERSION,
    _example_line,
    _metadata,
    json_line,
    names_for,
    synthetic_id,
    source_metadata,
)


def verify_smoke(output: Path, *, re_render: bool = True) -> dict:
    """Replay from copied OHLC without original large files; verify every binding."""
    manifest = verify_files(output)
    if (manifest["kind"] != "diagnostic_smoke" or manifest["status"] != "diagnostic_only_not_final_splits"
            or manifest["algorithm_version"] != VERSION or manifest["instruction_version"] != INSTRUCTION_VERSION):
        raise ValueError("Niezgodny schemat/status/wersja próby")
    rows = [json.loads(line) for line in (output/"examples.jsonl").read_text(encoding="utf-8").splitlines()]
    entries = manifest["entries"]
    if manifest["count"] != len(rows) or len(rows) != len(entries) or not 4 <= len(rows) <= 8:
        raise ValueError("Niepoprawna liczba przykładów")
    integrity = json.loads((output/"SOURCE_INTEGRITY.json").read_text(encoding="utf-8"))
    if integrity["unchanged"] is not True or not integrity["files"]:
        raise ValueError("Brak kontroli integralności źródła")
    source_hashes = set(integrity["files"].values())
    seen, ids, metadata, lines = set(), set(), [], []
    expected_files = {"examples.jsonl", "summary.json", "SOURCE_INTEGRITY.json"}
    with tempfile.TemporaryDirectory(prefix="ds-verify-") as temporary:
        for i, (row, entry) in enumerate(zip(rows, entries)):
            names = {"image": f"images/{i:03d}.png", "ohlc": f"ohlc/{i:03d}.csv",
                     "label": f"labels/{i:03d}.json", "metadata": f"metadata/{i:03d}.json"}
            if set(entry) != {"id", *names} or any(entry[k] != v for k, v in names.items()):
                raise ValueError("Niezgodne ścieżki przykładów")
            expected_files.update(names.values())
            meta = json.loads(child(output, entry["metadata"]).read_text(encoding="utf-8"))
            record = meta["source_metadata"]
            candles = read_candles_csv(child(output, entry["ohlc"]), source="dataset-replay")
            result = label_window(candles)
            digest = canonical_hash(candles)
            identity = hashlib.sha256((record["symbol"]+":"+record["source"]+":"+record["id"]+":"+digest).encode()).hexdigest()[:24]
            if digest in seen or identity in ids:
                raise ValueError("Duplikat przykładu")
            seen.add(digest)
            ids.add(identity)
            if record["symbol"] not in SYMBOLS or record["source"] not in ("real", "synthetic") or not record["id"].startswith(record["symbol"]+"_"):
                raise ValueError("Niezgodny symbol/źródło")
            if (record["source"] == "real" and (record["start_utc"] != candles[0].timestamp.isoformat()
                    or record["end_utc"] != candles[-1].timestamp.isoformat())):
                raise ValueError("Niezgodny zakres czasowy źródła")
            if record["source"] == "synthetic" and (record.get("variant") != "V2-full-refined" or type(record.get("seed")) is not int or not record.get("profile_sha256")):
                raise ValueError("Brak pochodzenia syntetyka")
            if record["visualization"] != VISUALIZATION or record["renderer_version"] != RENDERER_VERSION:
                raise ValueError("Niedozwolony obraz wejściowy")
            if digest != record["ohlc_sha256"] or sha256(child(output, entry["image"])) != record["png_sha256"]:
                raise ValueError("Niezgodne wiązanie obrazu/OHLC ze źródłem")
            if record["png_sha256"] not in source_hashes or record["window_csv_sha256"] not in source_hashes or sha256(child(output, entry["ohlc"])) != record["window_csv_sha256"]:
                raise ValueError("Brak wiązania z inwentarzem źródłowym")
            rendering = meta["rendering"]
            if re_render:
                rendering = render_window(candles, Path(temporary)/f"{i:03d}.png")
                if rendering != meta["rendering"]:
                    raise ValueError("Niezgodny odtworzony PNG; kontrola braku linii")
            expected = _metadata(record, candles, result, rendering, identity)
            expected.update(csv_sha256=sha256(child(output, entry["ohlc"])), label_sha256=sha256(child(output, entry["label"])))
            if expected != meta or entry["id"] != identity:
                raise ValueError("Niezgodne metadane")
            if child(output, entry["label"]).read_text(encoding="utf-8") != result.target_json():
                raise ValueError("Niezgodna etykieta")
            line = _example_line(identity, entry["image"], result.target_json())
            if row != json.loads(line):
                raise ValueError("Niezgodny przykład modelu")
            lines.append(line)
            metadata.append(meta)
    if set(manifest["files"]) != expected_files:
        raise ValueError("Niekompletny manifest")
    if (output/"examples.jsonl").read_text(encoding="utf-8") != "".join(lines):
        raise ValueError("Niezgodna serializacja JSONL")
    summary = summarize(metadata)
    if json.loads((output/"summary.json").read_text(encoding="utf-8")) != summary:
        raise ValueError("Niezgodny audyt struktury")
    if set(summary["by_symbol_source"]) != {s+"/"+source for s in SYMBOLS for source in ("real", "synthetic")}:
        raise ValueError("Niekompletne grupy instrument/źródło")
    return {"verified": True, "count": len(rows), "re_rendered": re_render, "final_dataset": False}


def _settings(config: Path, profile_root: Path, symbol: str):
    return replace(synthetic_settings(config, symbol, output=Path('data/synthetic/dataset35')),
                   profiles={symbol: str(profile_root/f'{symbol}.json')})


def _check_sources(plan: dict, *, saved_config: Path | None = None) -> None:
    snapshot = saved_config.read_bytes() if saved_config is not None else None
    config_digest = hashlib.sha256(snapshot).hexdigest() if snapshot is not None else None
    for name, digest in plan['source_integrity']['sha256'].items():
        if sha256(Path(name)) != digest:
            # Only an old complete config may be represented by split files now.
            # Match its pinned bytes exactly; every other source stays byte-strict.
            if digest == config_digest:
                try:
                    if configuration_snapshot(Path(name)) == snapshot:
                        continue
                except (OSError, UnicodeError, ValueError):
                    pass
            raise ValueError(f'Źródło planu zmieniło się: {name}')


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
        _check_sources(plan, saved_config=config)
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
