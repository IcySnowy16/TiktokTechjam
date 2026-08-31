"""Per-turn decision trace for the demo and conversation-quality metrics.

Internal only — the scored turn_response schema forbids extra fields, so this
never touches the API payload. Feeds the conversation-replay demo and the
honest per-session quality score (no repeated questions, boundaries respected,
turns-to-conversion).
"""

from __future__ import annotations

import json
from pathlib import Path


class SessionTrace:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.turns: list[dict] = []

    def record(
        self,
        turn: int,
        pool_size: int,
        ask_attribute: str | None,
        why: str,
        top_asins: list[str],
        parsed_summary: dict,
    ) -> None:
        self.turns.append(
            {
                "turn": turn,
                "pool_size": pool_size,
                "ask_attribute": ask_attribute,
                "why": why,
                "top_asins": top_asins[:5],
                "parsed": parsed_summary,
            }
        )

    def quality_metrics(self) -> dict:
        asked = [t["ask_attribute"] for t in self.turns if t["ask_attribute"]]
        return {
            "questions_asked": len(asked),
            "repeated_questions": len(asked) - len(set(asked)),
            "turns": len(self.turns),
        }


class TraceLog:
    """Collects session traces; export() writes one JSON file for the replay demo."""

    def __init__(self) -> None:
        self.sessions: dict[str, SessionTrace] = {}

    def session(self, session_id: str) -> SessionTrace:
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionTrace(session_id)
        return self.sessions[session_id]

    def export(self, path: str | Path = "trace_log.json") -> None:
        payload = {
            session_id: {
                "turns": trace.turns,
                "quality": trace.quality_metrics(),
            }
            for session_id, trace in self.sessions.items()
        }
        Path(path).write_text(json.dumps(payload, indent=1), encoding="utf-8")
