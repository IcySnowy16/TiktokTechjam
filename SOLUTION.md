# Solution Report — Stateful Conversational Shopping Agent

Team submission for the TechJam Conversational E-Commerce Search Challenge (Track 4).

## Method Overview

The provided BM25 starter is stateless and never asks a question, which makes it structurally
unable to receive most of what the simulated customer is willing to disclose. Our agent replaces
it with a stateful pipeline, run on every turn:

1. **Query processing** (`starter/dialog_state.py`) — each customer message updates per-session
   state: constraint phrases are filed into typed slots; "no preference" replies (fuzzy-matched,
   never exact-string-matched) permanently retire an attribute; override cues ("actually, ignore
   that…") trigger targeted single-slot erasure with a recency boost for the new value.
2. **Intent routing** — a lightweight buying-vs-browsing signal selects retrieval weighting,
   never a branch that skips retrieval.
3. **Hybrid retrieval** (`starter/retriever.py`) — always runs, on cumulative state:
   BM25 (SQLite FTS5) recall → soft attribute match/contradiction scoring (never a hard filter)
   → **idf-weighted phrase-coverage boost** of each disclosed constraint against each candidate's
   own text (the highest-value signal: disclosed constraints are near-literal fragments of the
   target's catalog entry) → TF-IDF tie-breaking → personalization from the anonymized profile's
   `preference_tags` and rating style.
4. **Question policy** (`starter/question_policy.py`) — asks the attribute maximizing
   reveal-prior × pool-splitting entropy, computed over the current candidate pool; stops asking
   once the pool is small, a clear leader exists, or turn ≥ 8. Recommendations are attached on
   every turn regardless — asking and recommending are never either/or.
5. **Safety choke point** (`starter/safety.py`) — every return path funnels through
   `build_safe_response()`; two fallback tiers (BM25-only, then a static valid response)
   guarantee `respond()` never raises and never returns a malformed payload.

## Results (public 200-session set, deterministic local evaluator)

| Stage | TechnicalScore | HR@10 | MRR | MTTC |
|---|---|---|---|---|
| Organizer BM25 baseline | 0.107 | 0.125 | 0.068 | 9.81 |
| + statefulness & fixed-order questions (M1) | 0.749 | 0.900 | 0.530 | 4.02 |
| + reveal-prior × entropy question policy (M2) | 0.770 | 0.915 | 0.561 | 3.80 |
| + phrase-coverage & attribute stages (M3) | 0.817 | 0.965 | 0.588 | 3.08 |
| + TF-IDF & personalization (M4, shipped) | **0.835** | **0.975** | **0.609** | **2.77** |

Per-scenario at M4 (HR@10 / MTTC): Buying 0.975 / 2.20, Browsing 0.988 / 2.64,
Intent Override 0.933 / 4.37, Boundary 1.000 / 3.60.

A negative result worth recording: pure pool-splitting entropy for question selection
*regressed* the score (0.749 → 0.714) until blended with a prior on which attribute types the
customer's hidden intent can actually answer — question value is reveal-likelihood × splitting
power, not splitting power alone.

## Model Choice, Cost, Latency

- **Core agent: no LLM.** The full technical score above is achieved with zero model calls —
  0 prompt tokens, 0 completion tokens, no network access. Stdlib-only (Python 3.10+, sqlite3
  FTS5); no vector database, no third-party dependencies required.
- **Optional LLM layer** (`starter/llm_adapter.py`): if `ANTHROPIC_API_KEY` is set and the
  `anthropic` SDK is installed, question phrasing is varied by `claude-haiku-4-5-20251001`
  (≤60 output tokens per asked question). A circuit breaker disables the layer permanently on
  the first failure or timeout, degrading to templates. Token usage is reported from the real
  API response, never estimated; it is honestly 0/0 whenever the offline path runs.
- **Offline statement (per submission rules): this submission does not require network access.**
  The LLM layer is presentation polish only.
- Latency: sub-second per turn after a one-time index build (~1–2 minutes for the 50k catalog)
  in `Agent.__init__`, which the evaluator amortizes across all sessions.

## Reproduction

```bash
# from the repo root, with data/catalog.jsonl in place (see README)
python -m evaluator.local_evaluator     # writes results.json
python -m unittest discover -s tests    # 24 tests: state machine, policy, retriever, contract
```

No environment variables are required. `ANTHROPIC_API_KEY` optionally enables the phrasing layer.

## Limitations

- Constraint classification is vocabulary-driven (`starter/vocab.py`); an exotic paraphrase
  outside the vocab falls back to the generic "feature" slot (still retrievable via the phrase
  stage, but unavailable to attribute filtering).
- The reveal priors in the question policy are derived from the public set's intent-card
  structure; a private set with a very different constraint mix would dilute (not break) the
  question ordering.
- The per-turn decision trace (`starter/explain.py`) is session-local and in-memory; export is
  manual (`TraceLog.export()`).

## Team Contributions

To be completed by the team before submission.
