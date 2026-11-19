"""One frozen test pair: preparation, raw inference, resume and completeness only.

No evaluator/reference loader is imported here. Official scoring is a later action.
"""
import uuid
import warnings
from pathlib import Path

from ...shared.integrity import sha256_file
from ...shared.manifests import verify_files
from ...shared.paths import require_short_path
from ...shared.configuration import configuration_sources
from ...evaluation.protocol import VERSION, PROTOCOL_SHA256
from ...datasets.domain.examples import INSTRUCTION_VERSION
from ...modeling.io.checkpoints import local_checkpoint
from ..final_config import load_plan, require_approval, VARIANTS
from ..io.final_inputs import read_test_images
from ..io.final_state import read, encoded, digest, atomic, event, session_lock, read_records, commit_record, publish_predictions, check_predictions
from ..io.final_model import FinalModel


def audit_plan(config_path: Path, *, dataset=None, selection_path=None, split='test'):
    config, selection = load_plan(config_path)
    if (split != 'test' or dataset is not None and dataset.resolve() != Path(config['dataset']).resolve()
            or selection_path is not None and selection_path.resolve() != Path(config['selection']).resolve()):
        raise ValueError('Only the explicitly frozen test dataset/selection is accepted')
    adapter = Path(selection['selected_adapter'])
    verify_files(adapter)
    if (sha256_file(adapter/'manifest.json') != selection['adapter_manifest_sha256']
            or sha256_file(adapter/'adapter_model.safetensors') != selection['adapter_sha256']):
        raise ValueError('Frozen adapter hash mismatch')
    for name, checksum in selection['adapter_files'].items():
        if sha256_file(adapter/name) != checksum:
            raise ValueError(f'Frozen adapter component mismatch: {name}')
    if sha256_file(Path(selection['effective_config_path'])) != selection['effective_config_sha256']:
        raise ValueError('Effective training configuration changed')
    for field, filename in [('validation_summary_sha256','summary.json'), ('validation_manifest_sha256','manifest.json')]:
        if sha256_file(Path(selection['validation_path'])/filename) != selection[field]:
            raise ValueError('Historical validation changed')
    inputs, binding = read_test_images(Path(config['dataset']), selection['dataset_manifest_sha256'])
    if binding['image_input_fingerprint'] != config['image_input_fingerprint']:
        raise ValueError('Frozen image-input fingerprint mismatch')
    identity = read(adapter/'training-identity.json')
    base = local_checkpoint(config['runtime'], 'qwen3-vl')
    for entry in identity['base']['files']:
        path = base/entry['file']
        if path.stat().st_size != entry['bytes'] or sha256_file(path) != entry['sha256']:
            raise ValueError(f'Frozen base-model/processor bytes changed: {path.name}')
    sources = {p.as_posix(): sha256_file(p) for p in Path('src/market_levels').rglob('*.py')}
    for p in [*configuration_sources(config_path), Path(config['selection']),
              Path('configs/vlm/stability.json'), Path('results/vlm41-cz2-20261110-1840/base-nf4/config.json'),
              adapter/'training-identity.json', Path('scripts/run_vlm_final_test.ps1')]:
        sources[p.as_posix()] = sha256_file(p)
    plan = {'config': config, 'selection_sha256': sha256_file(Path(config['selection'])),
            'binding': binding, 'source_sha256': sources, 'protocol_sha256': PROTOCOL_SHA256,
            'base_files': identity['base']['files']}
    return config, selection, inputs, plan


def prepare(config_path: Path, output: Path, explicit: bool, **options):
    config, _ = load_plan(config_path)
    require_approval(config, explicit)
    if output.resolve() != Path(config['output']).resolve():
        raise ValueError('Use the single output directory pinned by the final plan')
    if output.exists():
        raise FileExistsError('Final pair already reserved; use its unfinished variant with --resume')
    config, selection, inputs, plan = audit_plan(config_path, **options)
    require_short_path(output/'finetuned-nf4/records'/f'065-{inputs[-1].id}.json.pending')
    output.mkdir(parents=True, exist_ok=False)
    identifier = str(uuid.uuid4())
    session = {'schema': 1, 'session_id': identifier, 'plan': plan,
               'run_ids': {variant: f'{identifier}-{variant}' for variant in VARIANTS}}
    atomic(output/'session.json', encoded(session))
    atomic(output/'session.sha256', (sha256_file(output/'session.json')+'\n').encode('ascii'))
    (output/'execution.lock').write_bytes(b'0')
    return {'session': str(output), 'session_id': identifier, 'examples': len(inputs), 'loads_model': False}


def read_session(session: Path, plan: dict):
    if (session/'session.sha256').read_text(encoding='ascii').strip() != sha256_file(session/'session.json'):
        raise ValueError('Session manifest checksum mismatch')
    saved = read(session/'session.json')
    if saved['schema'] != 1 or saved['plan'] != plan or set(saved['run_ids']) != set(VARIANTS):
        raise ValueError('Session configuration/dataset/code identity mismatch')
    expected = {v: saved['session_id']+'-'+v for v in VARIANTS}
    if saved['run_ids'] != expected:
        raise ValueError('Session run IDs changed')
    return saved


def run_metadata(config, selection, session, variant):
    return {'run_id': session['run_ids'][variant], 'model_id': selection['base_model'],
            'base_revision': selection['base_revision'],
            'checkpoint_id': selection['adapter_sha256'] if variant == 'finetuned-nf4' else selection['base_revision'],
            'adapter_sha256': selection['adapter_sha256'] if variant == 'finetuned-nf4' else None,
            'variant': 'finetuned' if variant == 'finetuned-nf4' else 'base', 'split': 'test',
            'protocol_version': VERSION, 'protocol_sha256': PROTOCOL_SHA256,
            'instruction_version': INSTRUCTION_VERSION, 'prediction_kind': 'model',
            'dataset_id': selection['dataset_id'], 'dataset_manifest_sha256': selection['dataset_manifest_sha256'],
            'image_input_fingerprint': session['plan']['binding']['image_input_fingerprint'],
            'inference': {'generation': config['runtime']['generation'], 'precision': 'nf4',
                          'image_budget': 786432, 'nf4_frozen_dtypes': 'PEFT preparation, vision BF16',
                          'base_revision': selection['base_revision'], 'seed': config['runtime']['seed']},
            'session_id': session['session_id'], 'no_optimizer_updates': True}


def verify_variant(folder: Path, expected_run: dict, ids: list[str]):
    manifest = verify_files(folder)
    if (manifest.get('kind') != 'final_test_raw_inference' or manifest.get('status') != 'complete'
            or manifest.get('run_id') != expected_run['run_id'] or manifest.get('count') != len(ids)
            or read(folder/'run.json') != expected_run):
        raise ValueError('Wrong/incomplete final raw result')
    records = read_records(folder, expected_run, ids)
    if len(records) != len(ids):
        raise ValueError('Missing prediction IDs')
    check_predictions(folder, records)
    result = read(folder/'result.json')
    if result != {'status': 'complete', 'count': len(ids), 'run_id': expected_run['run_id'], 'no_optimizer_updates': True}:
        raise ValueError('Wrong final completion marker')
    return {'run_id': expected_run['run_id'], 'count': len(records), 'manifest_sha256': sha256_file(folder/'manifest.json')}


def finish(folder, run, ids, records):
    if len(records) != len(ids):
        raise ValueError('Refusing to publish incomplete raw inference')
    publish_predictions(folder, records)
    atomic(folder/'result.json', encoded({'status': 'complete', 'count': len(ids), 'run_id': run['run_id'], 'no_optimizer_updates': True}))
    event(folder, 'finished', count=len(ids))
    # Replace a partially written seal safely after a crash; never include its own files.
    excluded = {'manifest.json','manifest.sha256','manifest.json.pending','manifest.sha256.pending'}
    files = {p.relative_to(folder).as_posix(): sha256_file(p) for p in sorted(folder.rglob('*'))
             if p.is_file() and p.relative_to(folder).as_posix() not in excluded}
    manifest = {'kind': 'final_test_raw_inference', 'schema': 1, 'status': 'complete',
                'count': len(ids), 'run_id': run['run_id'], 'files': files}
    atomic(folder/'manifest.json', encoded(manifest))
    atomic(folder/'manifest.sha256', (sha256_file(folder/'manifest.json')+'\n').encode('ascii'))
    return verify_variant(folder, run, ids)


def execute(config_path: Path, session_path: Path, variant: str, explicit: bool, *, adapter=None, resume=False, **options):
    # Authorization is checked before model import/setup, plan audit or output creation.
    config, selection = load_plan(config_path)
    require_approval(config, explicit)
    if variant not in VARIANTS or session_path.resolve() != Path(config['output']).resolve():
        raise ValueError('Wrong final variant/session')
    if ((variant == 'base-nf4' and adapter is not None) or (variant == 'finetuned-nf4' and
            (adapter is None or adapter.resolve() != Path(selection['selected_adapter']).resolve()))):
        raise ValueError('Use no adapter for base; use exactly the frozen adapter for finetuned')
    config, selection, inputs, plan = audit_plan(config_path, **options)
    with session_lock(session_path):
        session = read_session(session_path, plan)
        ids = [i.id for i in inputs]
        if variant == 'finetuned-nf4':
            verify_variant(session_path/'base-nf4', run_metadata(config, selection, session, 'base-nf4'), ids)
        run = run_metadata(config, selection, session, variant)
        folder = session_path/variant
        if (folder/'manifest.sha256').exists():
            raise ValueError('Variant already complete; rerun/resume is forbidden')
        if resume:
            if not folder.is_dir() or read(folder/'run.json') != run:
                raise ValueError('Resume requires the original unfinished run')
            records = read_records(folder, run, ids)
            # A crash may follow the atomic record commit but precede prefix publication.
            # Only a strict byte prefix is recoverable; any other edit is rejected.
            if (folder/'predictions.jsonl').exists():
                old = (folder/'predictions.jsonl').read_bytes()
                expected = b''.join(encoded({'id': r['id'], 'response': r['response']}) for r in records)
                if not expected.startswith(old) or old and not old.endswith(b'\n'):
                    raise ValueError('Existing predictions were changed')
            publish_predictions(folder, records)
            event(folder, 'resumed', committed_answers=len(records))
        else:
            folder.mkdir(exist_ok=False)
            (folder/'records').mkdir()
            atomic(folder/'run.json', encoded(run))
            records = []
            publish_predictions(folder, records)
            event(folder, 'started', count=len(ids))
        try:
            if len(records) < len(inputs):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter('always')
                    try:
                        with FinalModel(config, selection, variant) as backend:
                            event(folder, 'model_loaded', details=backend.details)
                            for item in inputs[len(records):]:
                                if (folder/'STOP').exists():
                                    raise InterruptedError('STOP requested at answer boundary; resume explicitly')
                                response, details = backend.generate(item)
                                commit_record(folder, run, ids, records, response, details)
                                print(f'{len(records)}/{len(ids)} saved {item.id}', flush=True)
                    finally:
                        for warning in caught:
                            event(folder, 'warning', category=warning.category.__name__, message=str(warning.message))
            # Re-audit immutable bytes before sealing; no quality scores are computed.
            _, _, _, after = audit_plan(config_path, **options)
            if after != plan:
                raise ValueError('Frozen sources changed during inference')
            return finish(folder, run, ids, records)
        except BaseException as error:
            event(folder, 'interrupted' if isinstance(error, (KeyboardInterrupt, InterruptedError)) else 'failed',
                  error_type=type(error).__name__, message=str(error), committed_answers=len(records))
            raise


def verify_pair(config_path: Path, session_path: Path, *, variant=None, **options):
    config, selection, inputs, plan = audit_plan(config_path, **options)
    if session_path.resolve() != Path(config['output']).resolve():
        raise ValueError('Wrong final session path')
    with session_lock(session_path):
        session = read_session(session_path, plan)
        variants = (variant,) if variant is not None else VARIANTS
        if any(v not in VARIANTS for v in variants):
            raise ValueError('Wrong variant')
        verified = {v: verify_variant(session_path/v, run_metadata(config, selection, session, v), [i.id for i in inputs]) for v in variants}
        return {'verified': True, 'quality_metrics_computed': False, 'variants': verified}
