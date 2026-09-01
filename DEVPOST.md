# Devpost Project Description

Source text for Team KE$HA's Devpost submission (Track 4). Sections match Devpost's
"About the project" template exactly — paste from **Inspiration** through **What's next**.

---

## Inspiration

Traditional e-commerce search does keyword matching and hopes for the best; real shoppers
arrive vague ("something for winter, still exploring"), change their minds mid-conversation,
and expect an assistant that *remembers*. Track 4 makes this concrete: find the customer's
hidden target product in a 50,000-item catalog within 10 conversational turns, scored on
HitRate@10, MRR, and mean turns to conversion. The organizer's baseline agent — stateless,
never asking a single question — scores 0.107. We wanted to see how far disciplined
engineering could go without a single LLM token in the scored loop.

## What it does

A **stateful conversational search pipeline** that runs five steps every turn, mapping
directly onto the problem statement's pillars:

1. **Dialog state tracking.** Every customer message is split into clauses and classified
   independently: constraints file into typed slots (material, color, budget, size, style,
   use-case) **with polarity** — "I don't want leather; cotton is fine" excludes leather
   and keeps cotton. "No preference" replies retire an attribute permanently. Intent
   overrides are **scoped**: "actually, I need a hiking backpack" rewrites the shopping
   category and retires the old intent's constraints, while "actually, what I need is: X"
   replaces exactly one slot and leaves everything else the customer said intact.
2. **Hybrid retrieval.** Cumulative BM25 recall (SQLite FTS5, in-memory) feeds re-ranking
   signals: polarity-aware attribute matching with **typed budget operators**
   (under/over/between/around), a category-coverage anchor, an **idf-weighted
   phrase-coverage boost** — our key insight: disclosed constraints are near-literal
   fragments of the target's own listing, so coverage of a distinctive phrase is the
   strongest possible signal — TF-IDF tie-breaking, and profile personalization from the
   anonymized `preference_tags`.
3. **Adaptive clarification.** The next question maximizes reveal-likelihood ×
   pool-splitting entropy over the live candidate pool, stops asking once the pool is
   small or a clear leader emerges, and never re-asks what the customer already answered.
   A signature-based stall detector notices when the same candidates keep recurring with
   no new evidence and relaxes filters — runtime strategy re-orchestration, not a static
   pipeline.
4. **Recommendations every turn.** Asking and recommending are never either/or — misses
   cost nothing and a hit ends the session, so the agent always attaches its best top-10.
5. **A safety choke point.** Every response exits through one schema validator with
   transactional per-turn state and two fallback tiers, so the agent never crashes a
   session.

## How we built it

Measured milestones, each gated against the official deterministic evaluator and logged in
`REGRESSION_LOG.md`: statefulness first (0.107 → 0.749 — the single biggest jump came from
simply *remembering the conversation*), then adaptive questioning (0.770), phrase-coverage
and attribute ranking (0.817), TF-IDF + personalization (0.835), then a hardening pass
against an independent teammate audit (negation, mixed clauses, scoped overrides, typed
budgets, determinism, transactional state) and demo-exposed ranking fixes — finishing at
**0.8264** with every change's score impact recorded, including the experiments that
measured worse and were reverted.

- **Development tools:** VS Code with the Claude Code extension (Anthropic Claude Opus 5)
  for AI-pair-programmed development, code review against the organizer's evaluator
  source, and test authoring; Python 3.10–3.12; Git/GitHub; PowerShell & Bash; the
  organizer's deterministic local evaluator as the measurement harness.
- **APIs:** none required at runtime — the scored agent is fully offline (0 prompt /
  0 completion tokens reported). Optional, explicit opt-in only (`TECHJAM_ENABLE_LLM=1`
  + key): Anthropic Claude Haiku (`claude-haiku-4-5-20251001`) for varying
  clarifying-question phrasing — presentation polish with a circuit-breaker fallback to
  templates; it never affects retrieval or ranking correctness, and an ambient API key
  alone can never trigger a call.
- **Libraries & frameworks:** Python standard library only for the scored path —
  `sqlite3` (FTS5 full-text index, BM25), `difflib` (fuzzy cue matching), `dataclasses`,
  `re`, `math`, `unittest` (61 tests). Optional accelerators, off by default:
  `rapidfuzz`, `anthropic`. Deliberately **no** PyTorch / Transformers / vector
  database — the rules require in-memory light execution, and our measured results show
  classic IR + careful dialog-state semantics gets there without them.
- **Datasets & assets:** the organizer's frozen competition kit, derived from **Amazon
  Reviews 2023 (McAuley Lab, UCSD)**, `Clothing_Shoes_and_Jewelry` category —
  50,000-product catalog (SHA256-verified) + 200 labeled public development sessions.
  **No external training data**, no scraped data, no manual labeling.

## Challenges we ran into

The public simulator is deterministic and visible — the discipline was refusing to overfit
it. We removed behaviors that scored points only through simulator structure (re-asking
answered attributes, leaning on the catch-all "other" question), costing a measured −0.013
public score, and validated the trade with a grouped holdout split plus a battery of
hand-written adversarial semantics tests (negation, mixed clauses, category switches,
typed budgets) that the public set never exercises. Then demo rehearsal exposed further
free-form ranking bugs the evaluator never triggers — a flat budget bonus let a $5.99
ear cuff outrank the correct shoes whose price field was missing — and fixing them
(category anchoring, unknown-price credit) recovered the score to 0.8264 without
re-introducing the overfitting behaviors.

## Accomplishments that we're proud of

- **7.7× the official baseline**: TechnicalScore 0.8264 vs 0.107 — HitRate@10 0.975,
  MRR 0.593, mean conversion in 2.95 turns; Browsing scenario HitRate 1.000.
- **Zero LLM tokens, no network access** for the full score — immune to the
  network-disabled final-scoring policy, with honest 0/0 token disclosure.
- **Bit-identical results across Python hash seeds** — determinism engineered and
  verified, not assumed; anyone who clones the repo reproduces our exact numbers and our
  demo video's exact transcript.
- **No overfitting gap**: a grouped holdout split (sessions never used for tuning) scores
  *higher* than the tuning split (0.8458 vs 0.8158).
- **A regression log with the failures left in** — every change's measured impact,
  including reverted experiments, is public in the repo.

## What we learned

- **Textbook information gain is wrong for this task**: entropy-maximizing questions made
  the agent *worse* (0.749 → 0.714) until blended with a reveal prior — question value is
  reveal-likelihood × splitting power, not splitting power alone.
- **Negation scope is subtler than it looks**: customer negation ("no suede") must become
  an exclusion, but negation inside quoted catalog fragments ("do not bleach") describes
  the product — treating it as customer intent penalized the correct target itself
  (measured: Intent Override 0.933 → 0.900 until scoped).
- **Your demo is a test harness**: rehearsing free-form conversation exposed real ranking
  bugs the official evaluator structurally cannot trigger. Fix the product, not the video.
- **Determinism is earned, not free**: Python's hash-randomized set ordering made question
  selection vary between runs until we rebuilt tie-breaking on a fixed order.

## What's next for Ten-Turn Shopping Copilot

Multi-route recall with reciprocal-rank fusion (our single BM25 gate is the known recall
ceiling), a conversation-replay visualization built on the agent's per-turn decision
trace, and a learned reranker gated on holdout — not public — gains.

---

## Team

Team **KE$HA** — Wang Zilu, Lim Wei Feng Leo, Guan Chen Di, Dylan Yap, Damien Tan.
All members contributed across design, implementation, review, and submission preparation,
with Claude Code (Anthropic) used as an AI pair-programming tool throughout.

## Links

- Public repository: https://github.com/IcySnowy16/TiktokTechjam
- Demo video: https://youtu.be/2UY8_PIC6Yw
