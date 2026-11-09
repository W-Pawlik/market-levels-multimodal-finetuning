"""evaluation / workflows / evaluate."""
from __future__ import annotations

import platform
from pathlib import Path

from ...shared.publication import publication_workspace, publish_directory
from ...shared.manifests import seal
from ..io.inputs import read_references, read_predictions, read_run_manifest
from ..domain.metrics import aggregate
from ..protocol import VERSION, PROTOCOL_SHA256, RULES, dumps
from ..domain.responses import parse_response
from ..domain.scoring import score_example
from ..io.reports import _output, _write
from ..reporting.markdown import _markdown
from .verification import read_evaluation


def evaluate(dataset: Path, predictions: Path, run_manifest: Path, output: Path,
             *, split: str = 'validation') -> Path:
    output = _output(output)
    refs, binding, ledger = read_references(dataset, split)
    ledger.track(predictions)
    ledger.track(run_manifest)
    responses = read_predictions(predictions, refs, binding)
    run = read_run_manifest(run_manifest, binding)
    rows = [score_example(ref, parse_response(responses[ref.id])) for ref in refs]
    summary = aggregate(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    with publication_workspace(output.parent, prefix='.eval-') as tmp:
        stage = tmp/'batch'
        stage.mkdir()
        (stage/'predictions.jsonl').write_bytes(predictions.read_bytes())
        (stage/'run-input.json').write_bytes(run_manifest.read_bytes())
        _write(stage/'dataset_binding.json', binding)
        _write(stage/'protocol.json', {'version': VERSION, 'sha256': PROTOCOL_SHA256, 'rules': RULES})
        (stage/'per_example.jsonl').write_text(''.join(dumps(row)+'\n' for row in rows), encoding='utf-8')
        _write(stage/'summary.json', summary)
        _write(stage/'run.json', run)
        _write(stage/'SOURCE_INTEGRITY.json', ledger.verify())
        (stage/'RAPORT.md').write_text(_markdown(summary, run), encoding='utf-8')
        seal(stage, {'kind': 'evaluation_result', 'schema_version': 1, 'status': 'complete',
                     'protocol_version': VERSION, 'protocol_sha256': PROTOCOL_SHA256,
                     'prediction_kind': run['prediction_kind'], 'count': len(refs),
                     'runtime': {'python': platform.python_version(), 'platform': platform.platform()}})
        read_evaluation(stage)
        publish_directory(stage, output)
    return output
