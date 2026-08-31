"""Grouped holdout evaluation — DEV HARNESS ONLY, never part of the submission agent.

Splits the 200 public sessions into dev/holdout groups by a deterministic hash
of the target parent_asin (so no target appears on both sides), then scores the
agent on each split separately. Tune on dev; treat a gain that appears only on
dev as suspected overfitting.

Usage:  python -m tools.holdout_eval
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
from starter.agent import Agent

HOLDOUT_FRACTION = 4  # asin-hash % 4 == 0 -> holdout (~25%, ~50 sessions)


def split(samples: list[dict]) -> tuple[list[dict], list[dict]]:
    dev, holdout = [], []
    for sample in samples:
        asin = str(sample["ground_truth"]["parent_asin"])
        digest = int(hashlib.md5(asin.encode()).hexdigest(), 16)
        (holdout if digest % HOLDOUT_FRACTION == 0 else dev).append(sample)
    return dev, holdout


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    samples = load_jsonl(root / "data" / "public_set.jsonl")
    dev, holdout = split(samples)
    identifiers, categories, products = catalog_index(root / "data" / "catalog.jsonl")
    agent = Agent(root / "data" / "catalog.jsonl")
    for name, subset in (("dev", dev), ("holdout", holdout)):
        result = evaluate(agent, subset, identifiers, categories, products)
        keep = ("hit_rate_at_10", "mrr", "mttc", "efficiency", "recommended_technical_score")
        print(f"[{name}] n={len(subset)} " + json.dumps({k: result[k] for k in keep}))


if __name__ == "__main__":
    main()
