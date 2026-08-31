# Stateful Conversational Shopping Agent — TechJam 2026 Track 4

A multi-turn shopping copilot for the TechJam Conversational E-Commerce Search Challenge:
given an anonymized shopper profile and a conversation of up to 10 turns, find the hidden
target product in a frozen 50,000-item catalog by asking the right clarifying questions
and ranking with hybrid retrieval.

**Result:** TechnicalScore **0.8216** on the official 200-session public evaluator
(organizer baseline: 0.107) — HitRate@10 0.965, MRR 0.600, mean conversion in 3.05 turns —
with **zero LLM tokens, no network access**, and bit-identical results across Python hash
seeds. Grouped holdout check shows no overfitting gap (dev 0.8158 / holdout 0.8458).

> The organizer's original challenge README is preserved unchanged as
> [`ORGANIZER_README.md`](ORGANIZER_README.md). Competition rules and data documentation
> live in [`docs/`](docs/) and are untouched.

## Project overview

The provided starter agent was stateless and never asked questions. This agent replaces it
with a five-step pipeline, run every turn (all code in [`starter/`](starter/)):

| Step | Module | What it does |
|---|---|---|
| 1. Parse | `dialog_state.py` | Clause-by-clause classification into typed slots with **polarity** (negations exclude), boundary handling ("no preference" retires an attribute), and **scoped intent overrides** (category-wide vs attribute-local) |
| 2. Retrieve | `retriever.py`, `catalog_store.py` | Cumulative BM25 (SQLite FTS5) recall → polarity-aware attribute scoring with **typed budgets** (under/over/between/around) → idf-weighted **phrase-coverage boost** → TF-IDF → profile personalization |
| 3. Ask | `question_policy.py` | Deterministic question selection maximizing reveal-prior × pool-splitting entropy; never re-asks answered attributes; stops when confident |
| 4. Adapt | `agent.py` | Signature-based stall detection → filter relaxation (runtime strategy re-orchestration) |
| 5. Guard | `safety.py` | Single schema-validating choke point; transactional per-turn state; two fallback tiers so `respond()` never raises after construction |

Supporting: `explain.py` (per-turn decision trace), `llm_adapter.py` (optional,
opt-in-only phrasing layer with circuit breaker), `config.py` (every tunable in one place).

## Setup and installation

Requirements: **Python 3.10+** with sqlite3 FTS5 (standard on python.org builds). The
scored agent has **no required third-party dependencies** (`starter/requirements.txt`
lists optional extras only).

```bash
git clone <this-repo>
cd <this-repo>

# Get the catalog (58 MB, not in the repo):
#   download catalog.jsonl.gz from the organizer's participant-kit release:
#   https://github.com/TechJam2026/techjam-conversational-search/releases/tag/participant-kit
gzip -dk catalog.jsonl.gz
mv catalog.jsonl data/catalog.jsonl
# verify: SHA256 of the .gz must match the release's SHA256SUMS
```

## Steps to reproduce our results

```bash
python -m evaluator.local_evaluator      # official scorer -> results.json  (expect ~0.8216)
python -m unittest discover -s tests     # 57 tests: semantics, policy, retriever, contract, leakage guards
python -m tools.holdout_eval             # grouped dev/holdout split (dev harness only)
python -m tools.build_submission         # minimal leak-checked submission bundle
```

Determinism: results are identical under different `PYTHONHASHSEED` values. Optional env
flags (both off by default): `TECHJAM_ENABLE_LLM=1` (+ `ANTHROPIC_API_KEY` + `anthropic`
package) enables the phrasing layer; `TECHJAM_ENABLE_RAPIDFUZZ=1` enables the fuzzy-match
accelerator. Never commit keys.

Full method, measured milestone-by-milestone results, cost/latency disclosure, and the
change-by-change regression history: [`SOLUTION.md`](SOLUTION.md) and
[`REGRESSION_LOG.md`](REGRESSION_LOG.md).

## Limitations, and what we would improve given more time

- **Simulator coupling.** The public simulator derives constraints near-verbatim from the
  target's own catalog fields and our phrase-coverage stage exploits that structure —
  legal use of visible mechanics, but public scores likely overstate robustness to free
  human phrasing. We narrowed the gap with 31 hand-written adversarial tests (negation,
  mixed clauses, category switches, typed budgets) and a grouped holdout split; we did not
  close it.
- **Single recall gate.** Everything downstream re-ranks BM25's top 300; a target missed
  there is unrecoverable. Given more time: multi-route recall (category, latest-clause,
  synonym routes) fused with reciprocal-rank fusion, measured on recall separately.
- **Vocabulary-driven classification.** Paraphrases outside `vocab.py` fall back to the
  generic "feature" slot — retrievable via phrase coverage but invisible to attribute
  filtering. Double negation and colon-quoted negated constraints are not understood.
- **Memory (~890 MiB peak measured pre-bounding; caches now LRU-capped)** is acceptable,
  not lean — field pruning and token-ID compaction were deliberately deferred.
- Given more time we would also ship the conversation-replay visualization (the per-turn
  decision trace in `explain.py` already records pool sizes and question rationale) and a
  learned reranker gated on holdout — not public — improvement.

## Team member contributions

[[FILL BEFORE MAKING THE REPO PUBLIC: one line per member — who built/tuned what
(state machine, retrieval, tests, docs, demo video, Devpost) — or state that this is a
solo submission. Do not ship this placeholder.]]

## Data attribution

Derived from Amazon Reviews 2023 (McAuley Lab, UCSD) via the organizer's frozen
competition kit — see [`DATA_ATTRIBUTION.md`](DATA_ATTRIBUTION.md). No external training
data was used.
