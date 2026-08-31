# Solution Report — Stateful Conversational Shopping Agent

Team submission for the TechJam Conversational E-Commerce Search Challenge (Track 4).

## Method Overview

The provided BM25 starter is stateless and never asks a question, which makes it structurally
unable to receive most of what the simulated customer is willing to disclose. Our agent replaces
it with a stateful pipeline, run on every turn:

1. **Query processing** (`starter/dialog_state.py`) — each customer message is split into clauses
   and each clause classified independently, so one reply can carry a boundary AND a constraint
   ("no preference for color, but it must be waterproof") and both land. Constraints carry
   **polarity**: negated values ("I don't want leather") are excluded from all positive query
   construction and penalized at ranking time. Overrides are **scoped**: "actually, I need a
   hiking backpack" rewrites the category and retires the old intent's constraints; "actually,
   what I need is: X" replaces one attribute's values (old ones deactivated, kept for
   traceability) plus the retracted turn-1 preference, and leaves everything else untouched.
   Cue detection uses lexicons + fuzzy similarity; exact substring match is tried first as a
   fast path, with `difflib` similarity as the fallback for reworded cues (stdlib `difflib` is
   canonical — `rapidfuzz` accelerates only behind `TECHJAM_ENABLE_RAPIDFUZZ=1`, so parsing
   never varies with the environment).
2. **Cumulative hybrid retrieval** (`starter/retriever.py`) — always runs, on all state so far:
   BM25 (SQLite FTS5) recall → polarity-aware soft attribute scoring with a **typed budget**
   (min / max / range / target operators, "size 12" guarded) → **idf-weighted phrase-coverage
   boost** of each disclosed constraint against each candidate's own text → TF-IDF tie-breaking
   → personalization from the sanitized profile's `preference_tags` and rating style. There is
   no separate buying/browsing router module: scenario adaptivity comes from the state itself
   (which constraints exist and their weights), not from an explicit route decision.
3. **Question policy** (`starter/question_policy.py`) — deterministic by construction: askable
   attributes keep `FIXED_QUESTION_ORDER`, score ties break to the earlier attribute, results
   are bit-identical across `PYTHONHASHSEED` values (verified). Attributes the customer already
   answered are never re-asked; `other` is capped at one ask per session. Selection maximizes
   reveal-prior × pool-splitting entropy; stops asking when the pool is small, a clear leader
   exists, or turn ≥ 8. Recommendations attach on every turn regardless.
4. **Stall detection** (`starter/agent.py`) — a top-8 ASIN signature per turn; a stall is the
   same candidates recurring with no new evidence (never just an unchanged list length), and any
   new constraint, override, or category change resets it. On stall, contradiction penalties
   relax and the pool diversifies.
5. **Safety** (`starter/safety.py`) — every return path funnels through `build_safe_response()`;
   turns are **transactional** (state mutates on a copy, committed only after the full pipeline
   succeeds, so a mid-turn failure never leaves partial conversation state). After successful
   construction, `respond()` does not raise: it degrades to a BM25-only fallback, then to a
   static valid response. Constructor failures are deliberate and actionable (missing/empty
   catalog, missing FTS5) rather than silent.

## Results (public 200-session set, deterministic local evaluator)

| Stage | TechnicalScore | HR@10 | MRR | MTTC |
|---|---|---|---|---|
| Organizer BM25 baseline | 0.107 | 0.125 | 0.068 | 9.81 |
| + statefulness & fixed-order questions (M1) | 0.749 | 0.900 | 0.530 | 4.02 |
| + reveal-prior × entropy question policy (M2) | 0.770 | 0.915 | 0.561 | 3.80 |
| + phrase-coverage & attribute stages (M3) | 0.817 | 0.965 | 0.588 | 3.08 |
| + TF-IDF & personalization (M4) | 0.835 | 0.975 | 0.609 | 2.77 |
| + semantics hardening | 0.822 | 0.965 | 0.600 | 3.05 |
| + demo-driven ranking fixes (shipped) | **0.826** | **0.975** | **0.593** | **2.95** |

Per-scenario at shipped state (HR@10 / MTTC): Buying 0.975 / 2.64, Browsing 1.000 / 2.51,
Intent Override 0.933 / 4.60, Boundary 0.900 / 3.90. Identical results measured under
different `PYTHONHASHSEED` values.

A third measurement source beyond the evaluator and the holdout: rehearsing the demo
(`tools/demo_session.py`, a scripted free-form conversation) exposed ranking failures the
templated evaluator never triggers — a flat budget bonus let cheap off-category items with
known prices outrank correct matches whose price field was missing. Fixes (category-coverage
anchor, exclusion substance filter, full credit for unverifiable prices — only violations
move ranking) raised the public score from 0.8216 to 0.8264 and are individually logged,
including the two experiments that measured worse and were reverted.

**Why shipped < M4, on purpose.** The hardening pass (negation, mixed clauses, scoped overrides,
typed budgets, deterministic questions) deliberately removed two behaviors that scored points
only because of visible simulator structure: re-asking attributes the customer had already
answered, and leaning on the catch-all `other` question (now capped at 1/session). Together
these were worth about +0.013 public score (0.8342 → 0.8216 measured; demo-driven ranking
fixes later recovered to 0.8264 without re-introducing either behavior). The public simulator never emits negation, mixed
clauses, or budget operators, so these fixes cannot raise the public score — they exist to
protect behavior on the 800 private sessions, which may paraphrase more freely.

Two findings worth recording:
- Pure pool-splitting entropy for question selection *regressed* the score (0.749 → 0.714)
  until blended with a reveal prior — question value is reveal-likelihood × splitting power.
- Negation parsing must never apply to quoted constraint payloads: catalog-derived fragments
  legitimately contain negation-shaped text ("do not bleach"), and treating it as customer
  negation penalized the target itself (measured: Intent Override 0.933 → 0.900 until scoped).

**Grouped holdout check** (`tools/holdout_eval.py`: sessions split by target ASIN hash, holdout
never used for tuning): dev n=161 scores 0.8158, holdout n=39 scores **0.8458** — no dev/holdout
gap, i.e. no measurable development-set overfitting in the shipped configuration.

Full change-by-change metrics: `REGRESSION_LOG.md`.

## Model Choice, Cost, Latency

- **Core agent: no LLM.** All scores above are achieved with zero model calls — 0 prompt
  tokens, 0 completion tokens, no network access. Stdlib-only (Python 3.10+, sqlite3 with
  FTS5); no vector database; no required third-party packages.
- **Optional LLM layer** (`starter/llm_adapter.py`): requires **explicit opt-in** —
  `TECHJAM_ENABLE_LLM=1` *and* `ANTHROPIC_API_KEY` *and* an importable `anthropic` SDK. An
  ambient API key alone never triggers a network call (tested), so official scoring stays
  deterministic and cost-free by default. When enabled, question phrasing is varied by
  `claude-haiku-4-5-20251001`; a circuit breaker disables the layer permanently on first
  failure. Token usage is reported from the real API response, never estimated, and is honestly
  0/0 on the offline path.
- **Offline statement (per submission rules): this submission does not require network access.**
- Latency: sub-second per turn after a one-time index build in `Agent.__init__` (~4 s measured
  on an M-series MacBook; tens of seconds to minutes on cloud-synced/network folders — the
  build is I/O-bound on the 58 MB catalog). The evaluator constructs the Agent once, so the
  cost amortizes across all sessions.
- Memory: ~340 MiB after init, ~890 MiB peak over a full evaluator run (audit measurement,
  before the LRU cache bounds); token/attribute caches are now capped at 20k entries each.

## Reproduction

```bash
# from the repo root, with data/catalog.jsonl in place (see README)
python -m evaluator.local_evaluator     # scores the agent -> results.json
python -m unittest discover -s tests    # 57 tests: semantics, policy, retriever, contract, leakage guards
python -m tools.holdout_eval            # grouped dev/holdout split (dev harness, not shipped logic)
```

No environment variables are required. Optional: `TECHJAM_ENABLE_LLM=1` (with an API key)
enables the phrasing layer; `TECHJAM_ENABLE_RAPIDFUZZ=1` enables the fuzzy-matching accelerator.

## Limitations

- **Simulator coupling.** The public simulator derives constraints near-verbatim from the
  target's own catalog fields, and our phrase-coverage stage exploits that structure. It is
  legal use of visible mechanics, but public-set scores likely overstate robustness to free
  human phrasing; the hardening pass and adversarial tests (`tests/test_semantics.py`) narrow,
  not close, that gap.
- Constraint classification is vocabulary-driven (`starter/vocab.py`); an exotic paraphrase
  outside the vocab falls back to the generic "feature" slot (still retrievable via the phrase
  stage, but invisible to attribute filtering).
- Negation handling covers customer-authored clauses with local scope; double negation and
  colon-quoted negated constraints ("what matters is: nothing in wool") are not understood.
- Retrieval has a single BM25 recall gate (top 300): a target outside that shortlist cannot be
  recovered by later stages. Multi-route recall + rank fusion is the known next step.
- Reveal priors in the question policy are derived from the public set's intent-card structure;
  a private set with a very different constraint mix dilutes (not breaks) question ordering.
- Peak memory (~890 MiB measured pre-bounding) is acceptable but not lean; field-pruning and
  token-ID compaction were deliberately deferred.
- The per-turn decision trace (`starter/explain.py`) is in-memory and session-local; export is
  manual (`TraceLog.export()`).

## Team Contributions

Team: KE$HA
1. Wang Zilu
2. Lim Wei Feng Leo
3. Guan Chen Di
4. Dylan Yap
5. Damien Tan
