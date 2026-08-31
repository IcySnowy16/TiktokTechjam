"""Stage E: safe personalization from the anonymized aggregate user_profile."""

from __future__ import annotations

import math

from .text_utils import token_set
from .vocab import TAG_SYNONYMS


def preference_boost(doc_tokens: set[str], doc_text_lower: str, preference_tags: list[str]) -> float:
    """0..1-ish score for how well a product's own text matches the profile's tags."""
    if not preference_tags:
        return 0.0
    hits = 0
    total = 0
    for tag in preference_tags:
        synonyms = TAG_SYNONYMS.get(str(tag).lower(), [str(tag).lower()])
        total += 1
        for synonym in synonyms:
            if (" " in synonym and synonym in doc_text_lower) or (synonym in doc_tokens):
                hits += 1
                break
    return hits / total if total else 0.0


def rating_prior(product: dict, rating_style: str) -> float:
    """Small popularity prior; halved for critical raters whose taste correlates
    less with generic high ratings. Never a primary ranking driver."""
    try:
        average = float(product.get("average_rating") or 0.0)
        count = float(product.get("rating_number") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    score = (average / 5.0) * min(1.0, math.log1p(count) / math.log1p(10000))
    if "critical" in (rating_style or "").lower():
        score *= 0.5
    return score


__all__ = ["preference_boost", "rating_prior", "token_set"]
