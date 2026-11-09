"""Only image pixels and the production instruction enter a conversation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImageInput:
    id: str
    image: Path
    instruction: str


def conversation(example: ImageInput, image) -> list[dict]:
    return [{'role': 'user', 'content': [{'type': 'image', 'image': image},
                                      {'type': 'text', 'text': example.instruction}]}]


def spread_indices(count: int, selected: int) -> list[int]:
    """Equally spaced chronological ranks, including both endpoints."""
    if selected < 2 or count < selected:
        raise ValueError('Za mało przykładów do selekcji chronologicznej')
    return [(i * (count - 1) + (selected - 1) // 2) // (selected - 1) for i in range(selected)]
