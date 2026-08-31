"""Next-question selection: fixed priority order (M1) or entropy/coverage (M2+), plus stop rules."""

from __future__ import annotations

import math

from . import config
from .dialog_state import SessionState

_ENTROPY_ATTRIBUTES = ("material", "color", "size", "style", "use_case")
# Prior probability that the customer's hidden intent actually holds an
# undisclosed constraint of this type. Derived from the card structure
# (material/color are extracted first and most reliably, features/details fill
# the rest, budget is appended when a price exists) — a pool-splitting question
# about an attribute the card can't answer just wastes a turn.
_REVEAL_PRIOR = {
    "material": 1.0, "color": 0.95, "feature": 0.9, "budget": 0.6,
    "style": 0.45, "use_case": 0.35, "size": 0.35, "other": 0.55,
}
# Attributes without enumerable catalog values get a fixed splitting utility.
_FIXED_UTILITY = {"feature": 0.8, "budget": 0.75, "other": 0.7}
_ENTROPY_POOL_CAP = 80


def _max_asks(attribute: str) -> int:
    return config.MAX_ASKS_PER_ATTRIBUTE.get(attribute, config.DEFAULT_MAX_ASKS)


def _askable(state: SessionState) -> list[str]:
    candidates = set(config.FIXED_QUESTION_ORDER)
    candidates -= state.boundary_attributes
    candidates -= state.exhausted_attributes
    return [
        attribute for attribute in candidates
        if state.asked_attributes.get(attribute, 0) < _max_asks(attribute)
    ]


def _should_stop(state: SessionState, ranked_pool: list[tuple[str, float]]) -> bool:
    if state.turn >= config.MAX_QUESTION_TURN:
        return True
    if 0 < len(ranked_pool) <= config.CONFIDENT_POOL_SIZE:
        return True
    if len(ranked_pool) >= 2:
        top1, top2 = ranked_pool[0][1], ranked_pool[1][1]
        if top1 > 0 and (top1 - top2) / top1 >= config.CONFIDENT_MARGIN:
            return True
    return False


def select_ask_attribute(
    ranked_pool: list[tuple[str, float]],
    state: SessionState,
    catalog,
) -> str | None:
    if _should_stop(state, ranked_pool):
        return None
    askable = _askable(state)
    if not askable:
        return None

    if not config.ADAPTIVE_QUESTIONS:
        for attribute in config.FIXED_QUESTION_ORDER:
            if attribute in askable:
                return attribute
        return None

    pool = [asin for asin, _ in ranked_pool[:_ENTROPY_POOL_CAP]]
    if not pool:
        return max(askable, key=lambda a: _REVEAL_PRIOR.get(a, 0.0))

    best_attribute: str | None = None
    best_score = 0.0
    for attribute in askable:
        if attribute in _ENTROPY_ATTRIBUTES:
            # Blend so splitting power refines, but never overrides, the reveal
            # prior — a question the card can't answer scores low regardless.
            splitting = 0.5 + 0.5 * _coverage_balance(attribute, pool, catalog)
        else:
            splitting = _FIXED_UTILITY.get(attribute, 0.0)
        score = _REVEAL_PRIOR.get(attribute, 0.0) * splitting
        if score > best_score:
            best_score = score
            best_attribute = attribute
    return best_attribute


def _coverage_balance(attribute: str, pool: list[str], catalog) -> float:
    """coverage(a) x balance(a): how many pool items have the attribute, and how
    evenly its values split the pool. High = asking this question cuts hardest."""
    value_counts: dict[str, int] = {}
    covered = 0
    for asin in pool:
        values = catalog.get_attributes(asin).values_for(attribute)
        if values:
            covered += 1
            for value in values:
                value_counts[value] = value_counts.get(value, 0) + 1
    if covered == 0 or len(value_counts) < 2:
        return 0.0
    coverage = covered / len(pool)
    total = sum(value_counts.values())
    entropy = -sum((n / total) * math.log2(n / total) for n in value_counts.values())
    balance = entropy / math.log2(len(value_counts))
    return coverage * balance
