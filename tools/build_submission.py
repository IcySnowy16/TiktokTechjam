"""Build the FINAL submission bundle — minimal, clean, and label-leak-checked.

Bundle contents (per submission_rules.md's recommended layout):
    starter/ (code + requirements.txt), README.md (generated), SOLUTION.md

Excluded on purpose: data/, evaluator/, docs/, results.json, tests/, tools/,
caches, git metadata, archives. The organizer supplies their own harness.

The build FAILS if any public-session target ASIN or sample id appears anywhere
in the bundle (guards against a bad merge re-introducing a label leak).

Usage:  python -m tools.build_submission [out_dir]
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def public_labels() -> tuple[set[str], set[str]]:
    asins: set[str] = set()
    sample_ids: set[str] = set()
    with (ROOT / "data" / "public_set.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            sample = json.loads(line)
            asins.add(str(sample["ground_truth"]["parent_asin"]))
            sample_ids.add(str(sample["sample_id"]))
    return asins, sample_ids


def build(out_dir: Path) -> Path:
    stage = out_dir / "submission"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    shutil.copytree(
        ROOT / "starter", stage / "starter",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copy2(ROOT / "SOLUTION.md", stage / "SOLUTION.md")
    (stage / "README.md").write_text(README, encoding="utf-8")

    asins, sample_ids = public_labels()
    pattern = re.compile("|".join(map(re.escape, sorted(asins | sample_ids))))
    leaks: list[str] = []
    for path in stage.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            match = pattern.search(text)
            if match:
                leaks.append(f"{path.relative_to(stage)}: contains {match.group(0)!r}")
    if leaks:
        raise SystemExit("LABEL LEAK — bundle rejected:\n" + "\n".join(leaks))

    archive = out_dir / "submission.zip"
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(stage))
    return archive


README = """\
# TechJam Track 4 Submission — Stateful Conversational Shopping Agent

## Setup

- Python 3.10+ with sqlite3 FTS5 (standard on python.org builds). No required
  third-party packages; `starter/requirements.txt` lists optional extras only.
- Place the organizer catalog at `data/catalog.jsonl` relative to the working
  directory (download `catalog.jsonl.gz` from the participant-kit release,
  verify against the published SHA256SUMS, decompress).

## Run in the official harness

The evaluator imports `starter.agent.Agent` and constructs it once with the
catalog path. From a directory containing both this bundle's `starter/` and
the organizer's `evaluator/` + `data/`:

    python -m evaluator.local_evaluator

## Offline / model policy

No network access required: the agent is stdlib-only and reports 0/0 token
usage. An optional LLM phrasing layer exists but activates ONLY with explicit
opt-in (`TECHJAM_ENABLE_LLM=1` plus `ANTHROPIC_API_KEY` plus the `anthropic`
package); an ambient API key alone never triggers a call.

## Documentation

`SOLUTION.md` — method, measured results, cost/latency disclosure, limitations,
and team contributions.
"""


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build"
    archive = build(out)
    print(f"bundle: {archive}")
    print("smoke test: extract next to the organizer's evaluator/ and data/, then run it clean.")
