"""Gate official scoring behind two sealed runs; never performs inference."""
from pathlib import Path

from ...evaluation.workflows.evaluate import evaluate
from ...evaluation.workflows.compare import compare
from ...evaluation.workflows.verification import read_evaluation, read_comparison
from ...shared.integrity import sha256_file
from ..final_config import load_plan, require_approval, VARIANTS
from ..io.final_state import session_lock, read
from .final_test import verify_pair


def score_pair(config_path: Path, session: Path, explicit: bool, **options):
    config, _ = load_plan(config_path)
    require_approval(config, explicit)
    verify_pair(config_path, session, **options)  # No reference parsing until BOTH are complete.
    outputs = [Path('results/evaluation')/f'vlm46-final-test-{variant}' for variant in VARIANTS]
    with session_lock(session):
        for variant, output in zip(VARIANTS, outputs):
            raw = session/variant
            if output.exists():
                previous = read_evaluation(output)
                if (previous['run'] != read(raw/'run.json') or
                        sha256_file(output/'predictions.jsonl') != sha256_file(raw/'predictions.jsonl')):
                    raise ValueError('Existing official report belongs to other raw inputs')
            else:
                evaluate(Path(config['dataset']), raw/'predictions.jsonl', raw/'run.json', output, split='test')
            read_evaluation(output)
        paired = Path('results/evaluation/vlm46-final-test-comparison')
        if not paired.exists():
            compare(outputs[0], outputs[1], paired)
        report = read_comparison(paired)
        if (report['baseline_run'] != read(session/VARIANTS[0]/'run.json')
                or report['candidate_run'] != read(session/VARIANTS[1]/'run.json')):
            raise ValueError('Existing comparison belongs to another final pair')
    return {'evaluations': [str(p) for p in outputs], 'comparison': str(paired), 'verified': True}
