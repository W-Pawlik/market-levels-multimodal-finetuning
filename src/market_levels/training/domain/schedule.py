"""Deterministic epoch permutations and exact optimizer-boundary cursors."""
from __future__ import annotations

import math
import random


def epoch_order(ids: list[str], seed: int, epoch: int) -> list[str]:
    if not ids or len(set(ids)) != len(ids):
        raise ValueError('Nonempty unique train IDs required')
    order = sorted(ids)
    random.Random(seed + epoch).shuffle(order)
    return order


def total_steps(count: int, settings: dict) -> int:
    steps = math.ceil(count / settings['gradient_accumulation']) * settings['epochs']
    return min(steps, settings['max_steps']) if settings['max_steps'] is not None else steps


def initial_state(ids, settings):
    return {'epoch': 0, 'position': 0, 'order': epoch_order(ids, settings['seed'], 0),
            'global_step': 0, 'processed_examples': 0, 'input_tokens': 0, 'supervised_tokens': 0,
            'elapsed_seconds': 0.0}


def next_group(state, settings):
    return state['order'][state['position']:state['position'] + settings['gradient_accumulation']]


def advance(state, ids, settings, count):
    state['position'] += count
    state['processed_examples'] += count
    state['global_step'] += 1
    if state['position'] == len(state['order']):
        state['epoch'] += 1
        state['position'] = 0
        state['order'] = epoch_order(ids, settings['seed'], state['epoch'])


def validate_state(state, ids, settings):
    size, accumulation = len(ids), settings['gradient_accumulation']
    epoch, position, step = (state[k] for k in ('epoch', 'position', 'global_step'))
    if (not 0 <= epoch <= settings['epochs'] or not 0 <= position < size
            or position % accumulation or (epoch == settings['epochs'] and position)
            or step != epoch * math.ceil(size / accumulation) + position // accumulation
            or state['processed_examples'] != epoch * size + position
            or state['order'] != epoch_order(ids, settings['seed'], epoch)
            or step > total_steps(size, settings)):
        raise ValueError('Invalid sampler state or optimizer boundary')


def lr_multiplier(step, total, warmup, kind):
    if warmup and step < warmup:
        return step / warmup
    fraction = min(1.0, max(0.0, (step - warmup) / max(1, total - warmup)))
    if kind == 'constant':
        return 1.0
    return 1.0 - fraction if kind == 'linear' else 0.5 * (1.0 + math.cos(math.pi * fraction))
