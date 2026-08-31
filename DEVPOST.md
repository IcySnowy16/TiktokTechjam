# Devpost Project Description

Source text for Team KE$HA's Devpost submission (Track 4).

---

## Inspiration & problem

Traditional e-commerce search does keyword matching and hopes for the best; real shoppers
arrive vague ("something for winter, still exploring"), change their minds mid-conversation,
and expect an assistant that *remembers*. Track 4 makes this concrete: find the customer's
hidden target product in a 50,000-item catalog within 10 conversational turns, scored on
HitRate@10, MRR, and mean turns to conversion.

## What it does — how our solution addresses the problem statement

Our agent is a **stateful conversational search pipeline** that runs five steps every turn,
mapping directly onto the problem statement's pillars:

1. **Dialog state tracking (Pillar II).** Every customer message is split into clauses and
   classified independently: constraints file into typed slots (material, color, budget,
   size, style, use-case) **with polarity** — "I don't want leather; cotton is fine"
   excludes leather and keeps cotton. "No preference" replies retire an attribute
   permanently. Intent overrides are **scoped**: "actually, I need a hiking backpack"
   rewrites the shopping category and retires the old intent's constraints, while
   "actually, what I need is: X" replaces exactly one slot and leaves everything else the
   customer said intact.
2. **Hybrid retrieval (Pillar I).** Cumulative BM25 recall (SQLite FTS5, in-memory) feeds
   four re-ranking signals: polarity-aware attribute matching with **typed budget
   operators** (under/over/between/around), an **idf-weighted phrase-coverage boost** —
   our key insight: disclosed constraints are near-literal fragments of the target's own
   listing, so coverage of a distinctive phrase is the strongest possible signal — TF-IDF
   tie-breaking, and profile personalization from the anonymized `preference_tags`.
3. **Adaptive clarification (Pillars II & III).** The next question maximizes
   reveal-likelihood × pool-splitting entropy over the live candidate pool, stops asking
   once the pool is small or a clear leader emerges, and never re-asks what the customer
   already answered. A signature-based stall detector notices when the same candidates keep
   recurring with no new evidence and relaxes filters — runtime strategy re-orchestration,
   not a static pipeline.
4. **Evaluation discipline (Pillar IV).** Every change was gated against the official
   deterministic evaluator, logged in `REGRESSION_LOG.md`, and checked on a grouped
   holdout split that was never used for tuning.

**Results** (official local evaluator, 200 public sessions): TechnicalScore **0.8264** vs
the organizer baseline's 0.107 — HitRate@10 0.975, MRR 0.593, mean conversion in 2.95
turns — achieved with **zero LLM tokens and no network access**, and bit-identical across
Python hash seeds. Grouped holdout check: dev 0.8158 vs holdout 0.8458 — no overfitting
gap. Two findings we're proud of: textbook information-gain question selection made the
agent *worse* until blended with a reveal prior; and negation parsing must never apply to
quoted catalog fragments ("do not bleach" describes the product, not the customer's
wishes) — both measured, both documented.

## Development tools used

- VS Code with the Claude Code extension (Anthropic Claude Opus 5) for AI-pair-programmed
  development, code review against the organizer's evaluator source, and test authoring
- Python 3.10–3.12, Git/GitHub, PowerShell & Bash
- The organizer's deterministic local evaluator as the measurement harness

## APIs used

- **None required at runtime.** The scored agent is fully offline (0 prompt / 0 completion
  tokens reported).
- Optional, explicit opt-in only (`TECHJAM_ENABLE_LLM=1` + key): Anthropic Claude Haiku
  (`claude-haiku-4-5-20251001`) for varying clarifying-question phrasing — presentation
  polish with a circuit-breaker fallback to templates; it never affects retrieval or
  ranking correctness, and an ambient API key alone can never trigger a call.

## Libraries and frameworks used

- **Python standard library only** for the scored path: `sqlite3` (FTS5 full-text index,
  BM25), `difflib` (fuzzy cue matching), `dataclasses`, `re`, `math`, `unittest` (61 tests)
- Optional accelerators (off by default, declared in `starter/requirements.txt`):
  `rapidfuzz` (fuzzy matching speed-up), `anthropic` (the opt-in phrasing layer)
- Deliberately **no** PyTorch / Transformers / vector database — the rules require
  in-memory light execution, and our measured results show classic IR + careful dialog
  state semantics gets there without them

## Datasets and assets used

- The organizer's frozen competition kit, derived from **Amazon Reviews 2023 (McAuley Lab,
  UCSD)**, `Clothing_Shoes_and_Jewelry` category: 50,000-product catalog
  (SHA256-verified) + 200 labeled public development sessions
- **No external training data**, no scraped data, no manual labeling; hand-written
  adversarial paraphrase tests were authored by the team without copying evaluator
  templates (that's the overfitting trap)

## Challenges / what we learned

The public simulator is deterministic and visible — the discipline was refusing to
overfit it. We removed behaviors that scored points only through simulator structure
(re-asking answered attributes, leaning on the catch-all "other" question), costing a
measured −0.013 public score, and validated the trade with a grouped holdout split and
a battery of adversarial semantics tests (negation, mixed clauses, category switches,
typed budgets) that the public set never exercises. Demo rehearsal then exposed further
free-form ranking bugs the evaluator never triggers; fixing them (category anchoring,
unknown-price credit) recovered the score to 0.8264 without re-introducing the
overfitting behaviors.

## What's next

Multi-route recall with reciprocal-rank fusion (our single BM25 gate is the known recall
ceiling), a conversation-replay visualization built on the agent's per-turn decision
trace, and a learned reranker gated on holdout — not public — gains.

## Team

Team **KE$HA** — Wang Zilu, Lim Wei Feng Leo, Guan Chen Di, Dylan Yap, Damien Tan.
All members contributed across design, implementation, review, and submission preparation,
with Claude Code (Anthropic) used as an AI pair-programming tool throughout.

## Links

- Public repository: https://github.com/IcySnowy16/TiktokTechjam
- Demo video: [[FILL: public YouTube URL]]
