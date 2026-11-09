"""evaluation / workflows / compare."""
from __future__ import annotations

from pathlib import Path

from ...shared.publication import publication_workspace, publish_directory
from ...shared.manifests import seal
from ..protocol import VERSION, PROTOCOL_SHA256, RULES, MAIN_TOLERANCE, dumps
from ..io.reports import _output, _write
from .verification import read_evaluation, read_comparison
from ..domain.comparison import _comparison_content


def compare(baseline: Path, candidate: Path, output: Path) -> Path:
    output = _output(output)
    before, after = read_evaluation(baseline), read_evaluation(candidate)
    report = _comparison_content(before, after)
    a = before['run']
    output.parent.mkdir(parents=True, exist_ok=True)
    with publication_workspace(output.parent, prefix='.eval-') as tmp:
        stage = tmp/'batch'
        stage.mkdir()
        _write(stage/'comparison.json', report)
        _write(stage/'protocol.json', {'version': VERSION, 'sha256': PROTOCOL_SHA256, 'rules': RULES})
        heading = '**Test techniczny na sztucznych predykcjach, nie porównanie rzeczywistych VLM.**' if a['prediction_kind'] == 'technical_fixture' else 'Sparowane porównanie modelu bazowego i dostrojonego.'
        delta = report['delta_candidate_minus_baseline']['tolerances'][MAIN_TOLERANCE]['overall']
        (stage/'RAPORT.md').write_text('# Porównanie S/R\n\n'+heading+'\n\nRóżnice candidate − baseline przy k=0.5:\n\n'+dumps(delta)+'\n', encoding='utf-8')
        for folder, label in ((baseline,'baseline'),(candidate,'candidate')):
            # Copy complete small evaluation artifacts, not mutable external pointers.
            destination = stage/label
            destination.mkdir()
            for path in folder.iterdir():
                if path.is_file():
                    (destination/path.name).write_bytes(path.read_bytes())
        seal(stage, {'kind': 'evaluation_comparison', 'schema_version': 1, 'status': 'complete',
                     'protocol_version': VERSION, 'protocol_sha256': PROTOCOL_SHA256,
                     'prediction_kind': a['prediction_kind'], 'paired_count': len(before['rows'])})
        read_comparison(stage)
        publish_directory(stage, output)
    return output
