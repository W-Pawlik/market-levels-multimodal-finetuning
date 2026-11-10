"""Bounded optimizer-boundary training using the verified PyTorch/PEFT path."""
from __future__ import annotations

import copy
import json
import random
import re
import time
from pathlib import Path

from ...inference.io.pilot import write_json
from ...modeling.io.runtime import load_model, set_resolution, setup, environment
from ...modeling.io.adapter_check import prepare_nf4
from ...modeling.io.checkpoints import local_checkpoint
from ...shared.integrity import sha256_file
from ..domain.schedule import initial_state, next_group, advance, total_steps, validate_state, lr_multiplier
from ..io.data import read_train, make_batch
from ..io.checkpoints import save_checkpoint, load_checkpoint, export_adapter, checkpoint_metadata
from ..io.resources import snapshot, pressure, guard, ResourceMonitor
from ..io.events import Events


def plan(config, mode):
    config = copy.deepcopy(config)
    rows, binding = read_train(Path(config['runtime']['dataset']))
    ids = sorted(rows)
    if mode == 'smoke-test':
        # Fixed train-only subset, independent of all validation outputs.
        random.Random(config['pipeline']['seed']).shuffle(ids)
        ids = sorted(ids[:config['pipeline']['smoke_examples']])
        config['pipeline']['max_steps'] = config['pipeline']['smoke_steps']
        config['pipeline']['warmup_steps'] = 0
    binding['selected_ids'] = ids
    return config, {identity: rows[identity] for identity in ids}, binding


def verify_base(runtime):
    path = local_checkpoint(runtime, 'qwen3-vl')
    source = Path('results/vlm-feasibility-20261109-210209/downloaded-models.json')
    known = next(r for r in json.loads(source.read_text(encoding='utf-8'))
                 if r['id'] == runtime['models']['qwen3-vl']['id'])
    if known['revision'] != runtime['models']['qwen3-vl']['revision']:
        raise ValueError('Base revision mismatch')
    for entry in known['files']:
        file = path / entry['file']
        if file.stat().st_size != entry['bytes'] or sha256_file(file) != entry['sha256']:
            raise ValueError(f'Base checkpoint checksum mismatch: {file.name}')
    return {'files': known['files'], 'source_sha256': sha256_file(source)}


def preflight(config, mode='full', resume=None):
    effective, rows, binding = plan(config, mode)
    before = guard(effective['pipeline'])  # Before creating a CUDA context/model.
    torch = setup(effective['pipeline']['seed'])
    if (torch.cuda.device_count() != 1 or torch.cuda.get_device_name(0) != effective['pipeline']['required_gpu']
            or not torch.cuda.is_bf16_supported(including_emulation=False)):
        raise RuntimeError('One verified RTX 3060 Ti with native BF16 required')
    versions = environment()
    expected = {'torch': '2.10.0+cu128', 'transformers': '5.3.0', 'peft': '0.18.1',
                'bitsandbytes': '0.49.2', 'accelerate': '1.12.0'}
    if any(versions['packages'][key] != value for key, value in expected.items()):
        raise RuntimeError('Unverified ML library versions')
    base = verify_base(effective['runtime'])
    if resume is not None:
        meta = checkpoint_metadata(resume)
        # Processor identity is checked again after loading the local processor.
        for key, value in {'config': effective, 'dataset': binding, 'environment': versions, 'base': base}.items():
            if meta['identity'][key] != value:
                raise ValueError(f'Resume identity mismatch: {key}')
        validate_state(meta['sampler'], list(rows), effective['pipeline'])
    return {'memory_before_cuda': before, 'memory_after_cuda': snapshot(torch), 'environment': versions,
            'base': base, 'dataset': binding, 'total_steps': total_steps(len(rows), effective['pipeline'])}


def train_loop(settings, ids, state, backend, events, stop_requested, stop_after=None):
    """One group is a transaction: commit its cursor only after optimizer.step()."""
    validate_state(state, ids, settings)
    total = total_steps(len(ids), settings)
    session_steps = 0
    session_started, elapsed_before = time.perf_counter(), state['elapsed_seconds']
    while state['global_step'] < total:
        if stop_requested():
            return 'stopped'
        before_memory = backend.memory()
        before_reasons = pressure(before_memory, settings)
        if before_reasons:
            events.emit('memory_pressure', reasons=before_reasons, memory=before_memory)
            backend.save(state)
            return 'memory_stop'
        group = next_group(state, settings)
        started = time.perf_counter()
        epoch = state['epoch'] + 1
        stats = backend.step(group)
        advance(state, ids, settings, len(group))
        state['input_tokens'] += stats['input_tokens']
        state['supervised_tokens'] += stats['supervised_tokens']
        seconds = time.perf_counter() - started
        state['elapsed_seconds'] = elapsed_before + time.perf_counter() - session_started
        session_steps += 1
        memory = backend.memory()
        if state['global_step'] % settings['log_every_steps'] == 0:
            events.emit('step', epoch=epoch, step=state['global_step'], total_steps=total,
                        processed_examples=state['processed_examples'], seconds=seconds,
                        elapsed_seconds=state['elapsed_seconds'], memory=memory, **stats)
        reasons = pressure(memory, settings)
        status = None
        if reasons:
            events.emit('memory_pressure', reasons=reasons, memory=memory)
            status = 'memory_stop'
        elif stop_requested() or (stop_after is not None and session_steps >= stop_after):
            status = 'stopped'
        elif state['global_step'] == total:
            status = 'complete'
        elif state['global_step'] % settings['validate_every_steps'] == 0:
            status = 'validation_due'
        if (status or state['global_step'] % settings['save_every_steps'] == 0
                or state['position'] == 0):
            backend.save(state)
        if status:
            return status
    return 'complete'


class TorchBackend:
    def __init__(self, torch, model, processor, optimizer, scheduler, rows, config, identity, output, events):
        self.torch, self.model, self.processor = torch, model, processor
        self.optimizer, self.scheduler, self.rows = optimizer, scheduler, rows
        self.config, self.identity, self.output, self.events = config, identity, output, events
        self.latest = None

    def step(self, group):
        with ResourceMonitor() as monitor:
            result = self._step(group)
        self.samples = monitor.samples
        result['memory_samples'] = self.samples
        return result

    def _step(self, group):
        torch = self.torch
        self.optimizer.zero_grad(set_to_none=True)
        losses, batches = [], []
        for identity in group:
            batch, info = make_batch(self.rows[identity], Path(self.config['runtime']['dataset']),
                                    self.processor, self.config['runtime'], self.config['pipeline']['max_sequence_tokens'])
            batch = batch.to('cuda:0')
            with torch.autocast('cuda', dtype=torch.bfloat16):
                loss = self.model(**batch, use_cache=False).loss
            if not bool(torch.isfinite(loss)):
                raise ValueError('NaN/Inf loss; transaction aborted')
            losses.append(float(loss.detach()))
            (loss / len(group)).backward()
            batches.append(info)
            del batch, loss
        norm = float(torch.nn.utils.clip_grad_norm_([p for p in self.model.parameters() if p.requires_grad],
                                                   1.0, error_if_nonfinite=True))
        lr = self.optimizer.param_groups[0]['lr']
        self.optimizer.step()
        self.scheduler.step()
        self.optimizer.zero_grad(set_to_none=True)
        torch.cuda.synchronize()
        threshold = self.config['pipeline']['empty_cache_reserved_mib']
        if threshold and torch.cuda.memory_reserved() / 2**20 > threshold:
            # Only at an optimizer boundary; no active graph or gradient tensors.
            before = torch.cuda.memory_reserved() / 2**20
            torch.cuda.empty_cache()
            self.events.emit('cache_release', before_reserved_mib=before,
                             after_reserved_mib=torch.cuda.memory_reserved()/2**20)
        return {'ids': group, 'loss': sum(losses)/len(losses), 'losses': losses,
                'gradient_norm': norm, 'learning_rate': lr, 'batches': batches,
                'input_tokens': sum(b['input_tokens'] for b in batches),
                'supervised_tokens': sum(b['supervised_tokens'] for b in batches)}

    def memory(self):
        row = snapshot(self.torch)
        samples = getattr(self, 'samples', []) + [row]
        row['peak_global_vram_mib'] = max(s.get('used_vram_mib', 0) for s in samples)
        row['peak_rss_mib'] = max(s['rss_mib'] for s in samples)
        row['minimum_available_ram_mib'] = min(s['available_ram_mib'] for s in samples)
        commits = [s['commit_headroom_mib'] for s in samples if s['commit_headroom_mib'] is not None]
        row['minimum_commit_headroom_mib'] = min(commits) if commits else None
        return row

    def save(self, state):
        if self.latest is not None and self.latest.name == f"step-{state['global_step']:06d}":
            return
        self.latest = save_checkpoint(self.torch, self.model, self.optimizer, self.scheduler,
                                      state, self.identity, self.output / 'checkpoints')
        self.events.emit('checkpoint', step=state['global_step'], path=str(self.latest))


def run_training(config, output: Path, mode, resume=None, stop_after=None):
    if mode not in ('smoke-test', 'full'):
        raise ValueError('Unsupported training mode')
    if mode == 'full' and not config['pipeline']['full_approved']:
        raise ValueError('Full training is not approved')
    workflow_started = time.perf_counter()
    output.mkdir(parents=True, exist_ok=False)
    events = Events(output / 'events.jsonl')
    backend = None
    try:
        checked = preflight(config, mode, resume)
        write_json(output / 'preflight.json', checked)
        config, rows, binding = plan(config, mode)
        settings, runtime = config['pipeline'], config['runtime']
        write_json(output / 'effective-config.json', config)
        import numpy as np
        random.seed(settings['seed'])
        np.random.seed(settings['seed'] % 2**32)
        torch, model, processor, details = load_model(runtime, 'qwen3-vl', local_checkpoint(runtime, 'qwen3-vl'), quantized=True)
        set_resolution(processor, runtime['min_pixels'], runtime['image_budgets']['native'])
        model = prepare_nf4(model, torch, checkpointing=True)
        from peft import LoraConfig, get_peft_model
        targets = [name for name, _ in model.named_modules()
                   if re.fullmatch(r'model\.language_model\.layers\.\d+\.self_attn\.(q_proj|v_proj)', name)]
        if len(targets) != 56:
            raise ValueError('Unexpected language LoRA projections')
        model = get_peft_model(model, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.0,
            target_modules=targets, bias='none', task_type='CAUSAL_LM'))
        model.config.use_cache = False
        model.train()
        visual = model.base_model.model.model.visual
        visual.eval()
        trainable = [p for name, p in model.named_parameters() if p.requires_grad]
        if (any(p.requires_grad for p in visual.parameters()) or any('lora_' not in name for name, p in model.named_parameters() if p.requires_grad)
                or sum(p.numel() for p in trainable) != 1605632):
            raise ValueError('Unexpected trainable parameters')
        optimizer = torch.optim.AdamW(trainable, lr=runtime['training']['learning_rate'],
                                      betas=(0.9, 0.999), eps=1e-8, weight_decay=0.01)
        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer,
            lambda step: lr_multiplier(step, total_steps(len(rows), settings), settings['warmup_steps'], settings['scheduler']))
        identity = {'config': config, 'dataset': binding, 'environment': checked['environment'], 'base': checked['base'],
                    'processor': processor.to_dict(), 'image_processor': processor.image_processor.to_dict(),
                    'tokenizer': processor.tokenizer.init_kwargs, 'lora_targets': targets}
        # Normalize tuples/enums to the same JSON representation used in metadata.
        identity = json.loads(json.dumps(identity, default=str))
        write_json(output / 'identity.json', identity)
        write_json(output / 'model.json', details)
        state = initial_state(list(rows), settings)
        if resume is not None:
            state = load_checkpoint(torch, resume, identity, model, optimizer, scheduler)
            validate_state(state, list(rows), settings)
            events.emit('resumed', source=str(resume), step=state['global_step'], position=state['position'])
        state['elapsed_seconds'] += time.perf_counter() - workflow_started
        backend = TorchBackend(torch, model, processor, optimizer, scheduler, rows, config, identity, output, events)
        backend.save(state)
        torch.cuda.reset_peak_memory_stats()
        # STOP is checked only between complete optimizer transactions.
        status = train_loop(settings, list(rows), state, backend, events,
                            lambda: (output / 'STOP').exists(), stop_after)
        if backend.latest is None or backend.latest.name != f"step-{state['global_step']:06d}":
            backend.save(state)
        export_adapter(model, output / 'adapter', identity)
        result = {'status': status, 'sampler': state, 'latest_checkpoint': str(backend.latest),
                  'adapter': str(output / 'adapter'), 'memory': snapshot(torch)}
        write_json(output / 'result.json', result)
        events.emit('finished', **result)
        return 0 if status != 'memory_stop' else 3
    except (Exception, KeyboardInterrupt) as error:
        # Never serialize partially accumulated/updated state after an exception.
        result = {'status': 'failed', 'type': type(error).__name__, 'message': str(error),
                  'latest_checkpoint': str(backend.latest) if backend and backend.latest else None,
                  'resume_requested': str(resume) if resume is not None else None,
                  'cuda_oom': type(error).__name__ == 'OutOfMemoryError' or 'CUDA out of memory' in str(error),
                  'no_automatic_retry': True}
        try:
            result['memory'] = snapshot(torch if 'torch' in locals() else None)
        except Exception as sampling_error:
            result['memory_sampling_error'] = str(sampling_error)
        write_json(output / 'result.json', result)
        events.emit('failed', **result)
        return 1
