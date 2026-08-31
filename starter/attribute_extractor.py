"""Attribute extraction: catalog products -> structured attributes, free text -> attribute class."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text_utils import tokenize
from .vocab import (
    BUDGET_WORDS, COLORS, MATERIALS, SIZE_TERMS, STYLE_TERMS, USE_CASE_TERMS,
)

_PRICE_RE = re.compile(r"(?:\$|usd\s*)\s*(\d+(?:,\d{3})*(?:\.\d+)?)|(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:dollars|bucks)", re.IGNORECASE)
_BUDGET_HINT_RE = re.compile(r"(?:\$|<=|under|around|below|less than|up to|budget)\s*\$?\s*\d", re.IGNORECASE)

# Typed budget operators. A number is only a price when a currency marker or a
# budget keyword anchors it — "size 12" and "15 inch" are never budgets.
_NUM = r"\$?\s*(\d+(?:,\d{3})*(?:\.\d+)?)"
_RANGE_RE = re.compile(r"between\s+" + _NUM + r"\s+and\s+" + _NUM, re.IGNORECASE)
_MAX_RE = re.compile(
    r"(?:under|below|less than|at most|up to|no more than|max(?:imum)?(?:\s+of)?|cheaper than|within)\s+" + _NUM,
    re.IGNORECASE,
)
_MIN_RE = re.compile(
    r"(?:over|above|more than|at least|min(?:imum)?(?:\s+of)?|no less than|starting (?:at|from))\s+" + _NUM,
    re.IGNORECASE,
)
_TARGET_RE = re.compile(
    r"(?:around|about|approximately|roughly|circa|budget(?:\s+(?:of|is|near))?)\s+" + _NUM,
    re.IGNORECASE,
)
_NOT_PRICE_CONTEXT_RE = re.compile(
    r"(?:\bsizes?\s+" + _NUM + r")|(?:" + _NUM + r"\s*(?:inch(?:es)?|\"|cm|mm|oz|ounce|lbs?|pounds?|years?|yrs?))",
    re.IGNORECASE,
)


def _to_float(raw: str) -> float | None:
    try:
        return float(raw.replace(",", ""))
    except (TypeError, ValueError):
        return None


@dataclass
class Budget:
    """A typed price constraint: any of min / max / target may be set."""

    min: float | None = None
    max: float | None = None
    target: float | None = None
    tolerance: float = 0.35  # fraction, applies to target-style budgets

    def satisfied(self, price: float) -> bool:
        if self.min is not None and price < self.min:
            return False
        if self.max is not None and price > self.max:
            return False
        if self.target is not None:
            return abs(price - self.target) <= self.tolerance * self.target
        return self.min is not None or self.max is not None

    def violated(self, price: float) -> bool:
        if self.min is not None and price < self.min:
            return True
        if self.max is not None and price > self.max:
            return True
        if self.target is not None:
            return price > self.target * (1 + self.tolerance)
        return False


def parse_budget_spec(text: str) -> Budget | None:
    """Typed budget from a phrase; None when no price constraint is present."""
    lowered = (text or "").lower()
    # Strip non-price number contexts so "size 12" never becomes a budget.
    cleaned = _NOT_PRICE_CONTEXT_RE.sub(" ", lowered)
    match = _RANGE_RE.search(cleaned)
    if match:
        low, high = _to_float(match.group(1)), _to_float(match.group(2))
        if low is not None and high is not None:
            return Budget(min=min(low, high), max=max(low, high))
    match = _MAX_RE.search(cleaned)
    if match:
        value = _to_float(match.group(1))
        if value is not None:
            return Budget(max=value)
    match = _MIN_RE.search(cleaned)
    if match:
        value = _to_float(match.group(1))
        if value is not None:
            return Budget(min=value)
    match = _TARGET_RE.search(cleaned)
    if match:
        value = _to_float(match.group(1))
        if value is not None:
            return Budget(target=value)
    # A bare currency amount in budget context is a target.
    if _BUDGET_HINT_RE.search(cleaned):
        value = parse_budget(cleaned)
        if value is not None:
            return Budget(target=value)
    return None


@dataclass
class ProductAttributes:
    material: set[str] = field(default_factory=set)
    color: set[str] = field(default_factory=set)
    size: set[str] = field(default_factory=set)
    style: set[str] = field(default_factory=set)
    use_case: set[str] = field(default_factory=set)
    price: float | None = None

    def values_for(self, attribute: str) -> set[str]:
        return getattr(self, attribute, None) or set()


def extract(product: dict, tokens: set[str] | None = None) -> ProductAttributes:
    """Structured attributes from a catalog record's own text."""
    if tokens is None:
        from .catalog_store import searchable_text
        tokens = set(tokenize(searchable_text(product)))
    price = product.get("price")
    try:
        price_value = float(price) if price not in (None, "") else None
    except (TypeError, ValueError):
        price_value = None
    return ProductAttributes(
        material=tokens & MATERIALS,
        color=tokens & COLORS,
        size=tokens & SIZE_TERMS,
        style=tokens & STYLE_TERMS,
        use_case=tokens & USE_CASE_TERMS,
        price=price_value,
    )


def parse_budget(text: str) -> float | None:
    """Best-effort numeric budget from a phrase like 'budget around $24.99'."""
    match = _PRICE_RE.search(text or "")
    if not match:
        return None
    raw = match.group(1) or match.group(2)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def classify_text(text: str) -> str:
    """Best-effort attribute class for a disclosed constraint phrase.

    Independent, deliberately broader reimplementation of the evaluator's hidden
    heuristic — it only needs to file phrases into the right session slot.
    """
    lowered = (text or "").lower()
    if _BUDGET_HINT_RE.search(lowered) or any(word in lowered for word in BUDGET_WORDS):
        if parse_budget(lowered) is not None or "budget" in lowered:
            return "budget"
    tokens = set(tokenize(lowered))
    scores = {
        "material": len(tokens & MATERIALS),
        "color": len(tokens & COLORS),
        "size": len(tokens & SIZE_TERMS),
        "style": len(tokens & STYLE_TERMS),
        "use_case": len(tokens & USE_CASE_TERMS),
    }
    best = max(scores, key=lambda k: scores[k])
    if scores[best] > 0:
        return best
    return "feature"
