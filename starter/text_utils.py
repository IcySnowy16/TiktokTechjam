"""Tokenization and fuzzy text matching. Stdlib only; rapidfuzz is an optional accelerator."""

from __future__ import annotations

import os
import re
from difflib import SequenceMatcher

# difflib is the CANONICAL matcher: rapidfuzz scores borderline pairs slightly
# differently, so an ambient install must not silently change parsing between
# environments. Accelerate only on explicit opt-in.
_rf_fuzz = None
if os.environ.get("TECHJAM_ENABLE_RAPIDFUZZ") == "1":
    try:
        from rapidfuzz import fuzz as _rf_fuzz  # type: ignore[no-redef]
    except ImportError:
        _rf_fuzz = None

TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "i", "in", "is", "it", "me", "my", "of", "on", "or", "please", "some",
    "that", "the", "this", "to", "want", "with", "would", "you", "looking",
    "im", "am", "was", "were", "have", "has", "had", "do", "does", "did",
    "no", "not", "so", "if", "we", "our", "us", "they", "them",
}


def tokenize(text: str) -> list[str]:
    return [
        token.lower()
        for token in TOKEN_RE.findall(text or "")
        if len(token) > 1 and token.lower() not in STOPWORDS
    ]


def token_set(text: str) -> set[str]:
    return set(tokenize(text))


def _ratio(a: str, b: str) -> float:
    if _rf_fuzz is not None:
        return _rf_fuzz.ratio(a, b) / 100.0
    return SequenceMatcher(None, a, b).ratio()


def fuzzy_contains(text: str, phrase: str, threshold: float = 0.82) -> bool:
    """True if `phrase` appears in `text`, exactly or approximately.

    Exact substring check first; otherwise a sliding token-window comparison so
    a lightly reworded cue still triggers.
    """
    text_low = (text or "").lower()
    phrase_low = (phrase or "").lower()
    if not phrase_low:
        return False
    if phrase_low in text_low:
        return True
    phrase_tokens = phrase_low.split()
    words = text_low.split()
    width = len(phrase_tokens)
    if width == 0 or len(words) < max(2, width - 1):
        return False
    for start in range(0, len(words) - width + 2):
        window = " ".join(words[start:start + width + 1])
        if _ratio(phrase_low, window) >= threshold:
            return True
    return False


def idf_coverage(phrase_tokens: list[str], doc_tokens: set[str], idf) -> float:
    """Fraction of a phrase's idf mass present in a document's token set.

    Near-1.0 means the document contains (nearly) the whole phrase regardless of
    word order — robust to the light paraphrasing the private set may add.
    """
    if not phrase_tokens:
        return 0.0
    total = 0.0
    matched = 0.0
    for token in phrase_tokens:
        weight = idf(token)
        total += weight
        if token in doc_tokens:
            matched += weight
    return matched / total if total > 0 else 0.0
