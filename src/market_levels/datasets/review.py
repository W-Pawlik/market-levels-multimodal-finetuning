"""Small, separate review set; overlays can never enter production JSONL."""
import json
from pathlib import Path

from ..data_processing.staging import publication_workspace, publish_directory
from ..data_processing.storage import read_candles_csv, write_json
from ..labeling.algorithm import label_window
from ..labeling.pilot import render_levels, sha256
from .packaging import diagnostic_output, seal, verify_files


def create_review(dataset: Path, output: Path) -> Path:
    manifest = verify_files(dataset)
    if manifest['kind'] != 'production_dataset':
        raise ValueError('Przegląd wymaga kompletnego zbioru produkcyjnego')
    output = diagnostic_output(output)
    metadata = [(e, json.loads((dataset/e['metadata']).read_text(encoding='utf-8'))) for e in manifest['entries']]
    chosen = []
    for split, source in (('train','real'), ('train','synthetic'), ('validation','real'), ('test','real')):
        for symbol in ('BTCUSDT', 'ETHUSDT'):
            group = sorted([(e, m) for e, m in metadata if (e['split'], e['source'], e['symbol']) == (split, source, symbol)],
                           key=lambda pair: (pair[1]['metrics']['log_return_std'], pair[0]['id']))
            for index, reason in ((len(group)//2, 'mediana zmienności grupy'), (len(group)-1, 'maksymalna zmienność grupy')):
                entry, meta = group[index]
                if entry['id'] not in {e['id'] for e, _, _ in chosen}:
                    chosen.append((entry, meta, reason))
    output.parent.mkdir(parents=True, exist_ok=True)
    with publication_workspace(output.parent, prefix='.review-') as tmp:
        stage = tmp/'batch'
        for folder in ('images', 'overlays', 'ohlc', 'labels', 'metadata', 'diagnostics', 'splits'):
            (stage/folder).mkdir(parents=True)
        rows = []
        ids = {e['id'] for e, _, _ in chosen}
        for entry, meta, reason in chosen:
            for key in ('image', 'ohlc', 'label', 'metadata'):
                relative = entry[key]
                (stage/relative).write_bytes((dataset/relative).read_bytes())
            candles = read_candles_csv(stage/entry['ohlc'], source='production-review')
            result = label_window(candles)
            overlay = f'overlays/{entry["id"]}.png'
            render_levels(candles, result, stage/overlay)
            write_json(stage/f'diagnostics/{entry["id"]}.json', result.diagnostics())
            rows.append(dict(entry, reason=reason, overlay=overlay, overlay_is_vlm_input=False,
                             supports=meta['answer']['supports'], resistances=meta['answer']['resistances']))
        for split in ('train', 'validation', 'test'):
            text = ''.join(line+'\n' for line in (dataset/f'splits/{split}.jsonl').read_text(encoding='utf-8').splitlines()
                           if json.loads(line)['id'] in ids)
            (stage/f'splits/{split}.jsonl').write_text(text, encoding='utf-8')
        write_json(stage/'review.json', {'count': len(rows), 'purpose': 'diagnostic_only_not_training',
                    'source_manifest_sha256': sha256(dataset/'manifest.json'), 'samples': rows,
                    'selection': 'Osobno po splicie/źródle/instrumencie: mediana i max std log-zwrotów; wyłącznie przegląd po budowie.'})
        seal(stage, {'kind': 'production_review_samples', 'count': len(rows), 'schema_version': 1,
                     'overlay_is_vlm_input': False, 'full_dataset_manifest_sha256': sha256(dataset/'manifest.json')})
        verify_files(stage)
        publish_directory(stage, output)
    return output
