"""Tunable constants for the agent. Milestones flip these; code never hardcodes them."""

from __future__ import annotations

# --- Question policy ---
ADAPTIVE_QUESTIONS = True  # False = fixed priority order (M1); True = entropy/coverage (M2)
FIXED_QUESTION_ORDER = [
    "material", "color", "feature", "budget", "style", "size", "use_case", "other",
]
MAX_ASKS_PER_ATTRIBUTE = {"other": 1, "feature": 2}  # "other" is a last resort (ablation in SOLUTION.md)
DEFAULT_MAX_ASKS = 1
MAX_QUESTION_TURN = 8       # no new questions after this turn
CONFIDENT_POOL_SIZE = 3     # pool at or below this -> stop asking
CONFIDENT_MARGIN = 0.6      # (top1-top2)/top1 at or above this -> stop asking

# --- Retrieval fusion weights (0.0 disables a stage entirely) ---
W_BM25 = 1.0
W_ATTR = 1.0      # M3: attribute match/contradiction (Stage B)
W_PHRASE = 3.0    # M3: disclosed-phrase idf-coverage boost (Stage C) — the dominant signal
W_TFIDF = 0.5     # M4: idf-weighted query coverage (Stage D)
W_PERSONAL = 0.3  # M4: preference_tags boost (Stage E)
W_RATING = 0.15   # M4: rating prior tie-breaker (Stage E)

W_EXCLUDE = 1.5   # penalty weight for matching an excluded (negated) constraint
EXCLUDE_COVERAGE_MIN = 0.5  # coverage of an excluded phrase below this is ignored

SHORTLIST_SIZE = 300        # Stage-A BM25 recall depth
MAX_QUERY_TERMS = 60        # cap on FTS5 OR-query terms
ATTR_MATCH_BONUS = 1.0
ATTR_CONTRADICT_PENALTY = 0.5
BUDGET_TOLERANCE = 0.35     # price within +/-35% of stated budget counts as a match
OVERRIDE_NEW_VALUE_WEIGHT = 2.0
STALE_VALUE_DECAY = 0.5     # multiplier applied to pre-override slot values

# --- Text matching ---
FUZZY_THRESHOLD = 0.82      # difflib ratio for cue detection
PHRASE_MIN_COVERAGE = 0.35  # idf-coverage below this contributes nothing

# --- Strategy switch (stall detector, post-M3) ---
STALL_TURNS = 3             # unchanged pool signature for this many turns -> relax filters
