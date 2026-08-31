# Regression Log — Hardening Branch

Gate: public score within 0.015 of the 0.834805 baseline; all tests green.
Fixes here are private-set insurance — the public simulator never emits
negation, mixed clauses, or budget operators, so score-neutrality is success.

| Change | Tests | Score | HR@10 | MRR | MTTC | Notes |
|---|---|---|---|---|---|---|
| M4 baseline (frozen) | 24 pass | 0.834805 | 0.975 | 0.609016 | 2.77 | commit a20f58a |
| P0 guards + LLM opt-in | 28 pass | — | — | — | — | no scoring-path change |
| P1.1 negation/polarity (v1) | 31 pass | 0.830105 | 0.970 | 0.604016 | 2.805 | IO HR 0.933→0.90: FLAGGED |
| P1.2 clauses + fragment-whole fix | 35 pass | 0.830105 | 0.970 | 0.604016 | 2.805 | identical ⇒ splitting wasn't the cause |
| P1.3 scoped overrides | 39 pass | 0.829155 | 0.970 | 0.601516 | 2.815 | IO still 0.90 |
| quoted-message negation scope | 45 pass | 0.834205 | 0.975 | 0.609016 | 2.800 | IO recovered: 0.9333 / MRR 0.7616. Root cause was negation false-positives on quoted catalog fragments ("do not bleach") |
| P1.5–1.8 + P2 (final Phase-1 state) | 57 pass | 0.821611 | 0.965 | 0.600038 | 3.045 | SEED-IDENTICAL across PYTHONHASHSEED 0/42. Inside gate (−0.0132). Skip-known + other-cap cost reveals: boundary HR 1.0→0.9, buying MTTC 2.2→2.76 — deliberate de-exploitation of simulator-specific behavior; ablation recorded in SOLUTION.md |

Lessons recorded:
- Negation parsing must never apply to quoted constraint payloads (colon
  messages): catalog fragments legitimately contain negation-shaped text.
- The audit's recency-cancellation and set-iteration findings reproduced
  exactly as described and are covered by tests/test_semantics.py.
- IO MTTC drifted 4.37→4.57: the retracted turn-1 soft preference is now
  deactivated per spec semantics. On the public simulator that value still
  described the target (intent cards are self-consistent), so this is a
  deliberate robustness-over-public-score trade inside the gate.

Holdout (grouped by target ASIN, never tuned on): dev n=161 -> 0.815754, holdout n=39 -> 0.845791. No gap; no overfitting signal.
