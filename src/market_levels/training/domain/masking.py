"""Mask user/image/padding tokens, supervise only the assistant completion."""
from __future__ import annotations


def assistant_labels(input_ids, prompt_ids):
    prefix = prompt_ids.shape[-1]
    if input_ids.shape[-1] <= prefix or not input_ids[:, :prefix].equal(prompt_ids):
        raise ValueError('Pełna rozmowa nie zachowuje prefiksu instrukcji i obrazu')
    labels = input_ids.clone()
    labels[:, :prefix] = -100
    return labels
