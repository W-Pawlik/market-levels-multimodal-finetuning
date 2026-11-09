"""Strict, pinned configuration for the bounded VLM pilot."""
from __future__ import annotations

import re
from pathlib import Path

from ..shared.configuration import read_configuration


def load_config(path: Path) -> dict:
    doc = read_configuration(path)
    expected = {'dataset', 'cache', 'models', 'generation', 'image_budgets', 'min_pixels', 'seed', 'training'}
    if not isinstance(doc, dict) or set(doc) != expected:
        raise ValueError('Nieznane lub brakujące pola konfiguracji VLM')
    identities = {'qwen3-vl': ('Qwen/Qwen3-VL-2B-Instruct', 'Qwen3VLForConditionalGeneration', None),
                  'qwen3.5': ('Qwen/Qwen3.5-2B', 'Qwen3_5ForConditionalGeneration', False)}
    if set(doc['models']) != set(identities):
        raise ValueError('Pilot obsługuje wyłącznie dwóch wskazanych kandydatów')
    for key, (identity, architecture, thinking) in identities.items():
        spec = doc['models'][key]
        if (set(spec) != {'id', 'revision', 'architecture', 'enable_thinking'} or spec['id'] != identity
                or spec['architecture'] != architecture or spec['enable_thinking'] is not thinking
                or not re.fullmatch('[0-9a-f]{40}', spec['revision'])):
            raise ValueError('Wymagany oficjalny model, pełna rewizja i właściwa architektura')
    gen = doc['generation']
    if (set(gen) != {'do_sample', 'num_beams', 'max_new_tokens', 'use_cache'} or gen['do_sample'] is not False
            or gen['num_beams'] != 1 or gen['use_cache'] is not True
            or type(gen['max_new_tokens']) is not int or not 32 <= gen['max_new_tokens'] <= 512):
        raise ValueError('Pilot wymaga deterministycznego, ograniczonego generowania')
    budgets = doc['image_budgets']
    if (not isinstance(budgets, dict) or not budgets or any(type(v) is not int or not 65536 <= v <= 786432 for v in budgets.values())
            or type(doc['min_pixels']) is not int or not 1024 <= doc['min_pixels'] <= min(budgets.values())):
        raise ValueError('Niepoprawny budżet rozdzielczości')
    train = doc['training']
    if (set(train) != {'rank', 'alpha', 'learning_rate', 'gradient_checkpointing'}
            or type(train['rank']) is not int or not 1 <= train['rank'] <= 16
            or type(train['alpha']) is not int or train['alpha'] <= 0
            or not 0 < train['learning_rate'] <= 0.001 or type(train['gradient_checkpointing']) is not bool):
        raise ValueError('Niepoprawna konfiguracja małej próby adaptera')
    if type(doc['seed']) is not int or not all(isinstance(doc[k], str) and doc[k] for k in ('dataset', 'cache')):
        raise ValueError('Niepoprawny seed lub ścieżki')
    return doc
