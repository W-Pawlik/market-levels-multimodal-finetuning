"""experiments / refinement / domain / plan."""
from __future__ import annotations

from ..config import SEEDS, FRESH_SEEDS


def experiment_tasks(mode: str, *, fresh: bool = False) -> list[dict]:
    """Jawna lista partii: nowy eksperyment generuje również oba baseline."""
    seeds = FRESH_SEEDS if fresh else ((20261107,) if mode=='smoke' else SEEDS)
    count = 2 if mode=='smoke' else 60
    families = [('v1','v1','full'),('original','v2','full')] if fresh else []
    families += [('full','v2','full'),('bridge_volatility','v2','bridge_volatility')]
    return [dict(seed=seed, count=count, family=family, version=version, variant=variant)
            for seed in seeds for family,version,variant in families]
