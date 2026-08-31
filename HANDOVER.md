# HANDOVER — Track 4 Shopping Copilot

Last updated: 2026-08-31 · branch `hardening` (4 commits ahead of `main`) · 57 tests green

The one-paragraph version: the agent is **built, hardened, measured, and documented**.
Public score 0.8216 (organizer baseline 0.107), bit-identical across hash seeds, no
dev/holdout overfitting gap, zero LLM tokens, no network needed. What remains is
**submission logistics** (names, Devpost, video, one smoke test) and optional polish.

---

## 1. What has been done

### The agent (score: 0.107 → 0.835 → 0.8216 hardened)

Built in measured milestones, each verified against the official local evaluator:

| Stage | Score | What it added |
|---|---|---|
| Organizer baseline | 0.107 | stateless BM25, never asks questions |
| M1 statefulness | 0.749 | conversation memory + slot filling + questions — the big jump |
| M2 question policy | 0.770 | reveal-prior × entropy question selection |
| M3 phrase matching | 0.817 | idf-weighted phrase coverage (constraints ≈ fragments of the target's own listing) |
| M4 TF-IDF + personalization | 0.835 | tie-breaking + `preference_tags` boost |
| Hardening (shipped) | **0.8216** | audit fixes below; −0.013 is a *deliberate* de-exploitation trade |

All code lives in `starter/` (entry point `starter/agent.py`, which the evaluator imports;
13 focused modules behind it). Tuning knobs are all in `starter/config.py`.

### The hardening pass (Leo's audit, implemented and verified)

Every P0/P1/P2 finding closed, each with failing-test-first discipline:

- **Negation & polarity** — "I don't want leather" excludes leather everywhere (query,
  phrase scoring, attribute scoring). Crucial subtlety we learned the hard way: negation
  parsing must SKIP quoted constraint payloads (text after a colon) — catalog fragments
  like "do not bleach" describe the product, and excluding them penalized the target
  itself (cost Intent Override 0.933→0.90 until scoped; see `REGRESSION_LOG.md`).
- **Clause-by-clause parsing** — "no preference for color, but it must be waterproof"
  records the boundary AND keeps the constraint.
- **Scoped overrides** — "I need a hiking backpack" = category switch (old constraints
  retired, stall reset); "what I need is: X" = one slot replaced, everything else intact.
- **Typed budgets** — under/over/between/around parse to min/max/range/target operators;
  "size 12" is never a price.
- **Deterministic questions** — fixed-order tie-breaks, never re-asks answered attributes,
  `other` capped at 1/session. Verified bit-identical under `PYTHONHASHSEED=0` and `=42`.
- **Signature stall detection** — same top-8 candidates recurring with no new evidence
  (never just list length); resets on any new constraint/override/category change.
- **Transactional turns** — a mid-turn crash commits no partial state (tested).
- **LLM & fuzzy opt-ins** — an ambient `ANTHROPIC_API_KEY` alone can NEVER trigger a
  network call (`TECHJAM_ENABLE_LLM=1` required); stdlib `difflib` is the canonical fuzzy
  matcher (`TECHJAM_ENABLE_RAPIDFUZZ=1` to accelerate).
- **Leakage guards** — `tests/test_no_leakage.py` proves `starter/` never imports the
  evaluator or reads public labels; the bundle builder hard-fails on any label leak.

### Evidence & documentation

- `SOLUTION.md` — the submission report, truth-passed (every audit-flagged overclaim
  corrected; simulator-coupling limitation stated plainly).
- `REGRESSION_LOG.md` — every gate run, including the failed intermediate states.
- Holdout check: dev n=161 → 0.8158, holdout n=39 → **0.8458**. No gap = no
  development-set overfitting.
- Team pages (private links, share from the page menu):
  - The Ten-Turn Playbook (plan + strategy): https://claude.ai/code/artifact/88276342-695e-4656-a48b-0d5878b0a61f
  - Inside the Ten-Turn Agent (concept explainer): https://claude.ai/code/artifact/c62a1605-2740-4343-a631-a5b7a9874ef0

---

## 2. What YOU need to do (blockers, in order)

### 2.1 Fill in Team Contributions — 10 minutes
`SOLUTION.md`, last section, is a marked placeholder. Replace it with real names + roles,
or state explicitly that this is a solo submission. **The bundle must not ship with the
placeholder.**

### 2.2 Leo: remove the exposed answer from HIS copy — 5 minutes
`tiktokfiles/SOLUTION.md` (on Leo's Mac) reveals the target product for `public_0001`.
Delete that line/transcript there. Our repo's copy is verified clean, and the bundle
builder now blocks any such leak from merging back in — but his file must be fixed at
the source before anything is copied from it.

### 2.3 Build + smoke-test the submission bundle — 20 minutes
```bash
cd techjam-cs
python -m tools.build_submission          # -> build/submission.zip (18 files)
```
The builder fails loudly if any public target ASIN / sample id is in the bundle.
Then smoke-test from a CLEAN directory (this is the audit's "clean package" gate):
```bash
mkdir /tmp/smoke && cd /tmp/smoke
unzip <path>/submission.zip
# copy the ORGANIZER's evaluator/ and data/public_set.jsonl here,
# download + verify a FRESH catalog.jsonl into data/ (SHA256SUMS)
python -m evaluator.local_evaluator       # expect score ≈ 0.8216
python -m unittest discover -s tests      # if you also copy tests/: 57 green
```

### 2.4 Devpost writeup — 30 minutes
`DEVPOST.md` is a ready-to-paste draft covering every required section (problem fit,
tools, APIs, libraries, datasets). Fill its two [[FILL]] blocks (team + links), paste
into the Devpost form. The public-repo `README.md` is likewise ready — fill its Team
Contributions block, push to the TEAM FORK (never the organizer repo), make it public.

### 2.5 Demo video — half a day
Public YouTube, linked in Devpost. Suggested 3-minute storyline, all of it real:
1. One live multi-turn session (run the evaluator on a single session or drive the
   agent from a small REPL script) — show the clarifying question and the hit.
2. The score story: 0.107 baseline → 0.8216, per-scenario table from `results.json`.
3. The robustness moment: show `TECHJAM_ENABLE_LLM` unset, no API key, score unchanged —
   "no network, zero tokens."
4. One hardening highlight: the negation demo ("I don't want leather; cotton is fine")
   showing leather excluded from results.
The decision trace for a session is available via `agent.trace_log.session(id).export()`
(`starter/explain.py`) if you build the pool-narrowing visualization.

---

## 3. Optional (only if time remains)

- **Weight tuning** — knobs in `starter/config.py`. Discipline: change one value →
  `python -m evaluator.local_evaluator` → also `python -m tools.holdout_eval` → keep only
  if BOTH dev and holdout improve (log it in `REGRESSION_LOG.md`). Intent Override
  (0.933 HR, 4.6 MTTC) is the weakest scenario.
- **Multi-route recall + RRF fusion** — the audit's Phase 3, deliberately deferred. The
  single BM25 gate (top 300) is the known recall ceiling; see `SOLUTION.md` Limitations.
- **Conversation-replay visualization** — trace data already exists in `explain.py`;
  highest payoff for the final-round pitch.
- **Paraphrase battery growth** — add hand-written rewordings to `tests/test_semantics.py`
  (never copy evaluator template strings — that's the overfitting trap).

---

## 4. House rules (do not break these)

1. **Never edit** `evaluator/`, `data/public_set.jsonl`, `docs/`, or scoring config.
2. **Never commit** API keys, `results.json`, archives, or anything from `data/`.
3. Entry point stays `starter/agent.py` exporting `Agent` — the evaluator hardcodes
   that import. Helper modules under `starter/` are fine (submission rules allow them).
4. Organizer's reserved test filenames stay untouched: `tests/test_evaluator.py`,
   `test_5core_builder.py`, `test_organizer_pipeline.py`.
5. Every change: run `python -m unittest discover -s tests` (fast) before the full
   evaluator (slow). Gate: public score within 0.015 of the logged value, or investigate.
6. Two different zips: `techjam-track4-handover.zip` (teammate onboarding — contains
   evaluator/public set, fine to share within the team) vs `build/submission.zip`
   (what gets submitted — minimal 18 files, no data, no evaluator).
7. Git: this repo's `origin` is the ORGANIZER's repo — do not push. Add the team fork
   as a new remote and push branches there.

## 5. Quick reference

```bash
python -m evaluator.local_evaluator      # full 200-session score -> results.json
python -m unittest discover -s tests     # 57 tests, ~0.3 s
python -m tools.holdout_eval             # grouped dev/holdout split
python -m tools.build_submission         # leak-checked minimal bundle
git log --oneline                        # the story: checkpoint -> guards -> semantics -> truth pass
```

Key files: `starter/config.py` (all knobs) · `starter/dialog_state.py` (state machine) ·
`starter/retriever.py` (ranking fusion) · `starter/question_policy.py` (what to ask) ·
`SOLUTION.md` (submission report) · `REGRESSION_LOG.md` (measurement history).
