"""Stateful conversational shopping agent — thin composition root.

Pipeline per turn: dialog-state update -> hybrid retrieval (always runs) ->
pool-confidence question policy -> message composition, with every return path
funnelled through safety.build_safe_response(). Falls back to a stateless
BM25-only query, then to a static valid response, so respond() never raises.
"""

from __future__ import annotations

from pathlib import Path

from . import config
from .catalog_store import CatalogStore
from .dialog_state import DialogStateMachine, SessionState
from .explain import TraceLog
from .llm_adapter import LLMAdapter
from .messenger import compose
from .question_policy import select_ask_attribute
from .retriever import HybridRetriever
from .safety import build_safe_response
from .text_utils import tokenize


class Agent:
    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        self.catalog = CatalogStore(catalog_path)
        self.retriever = HybridRetriever(self.catalog)
        self.state_machine = DialogStateMachine()
        self.trace_log = TraceLog()
        self.llm = LLMAdapter()  # dormant unless ANTHROPIC_API_KEY + SDK are present
        self._sessions: dict[str, SessionState] = {}

    def reset(self, session_id: str, user_profile: dict) -> None:
        self._sessions[session_id] = SessionState(
            session_id=session_id,
            user_profile=user_profile if isinstance(user_profile, dict) else {},
        )

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        try:
            return self._respond_impl(session_id, user_message, turn, top_k)
        except Exception:
            try:
                return self._bm25_fallback(user_message, top_k)
            except Exception:
                return build_safe_response(
                    "Let me take another look at that.", None, [], {}, self.catalog.catalog_ids
                )

    # -- main pipeline -----------------------------------------------------

    def _respond_impl(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        state = self._sessions.get(session_id)
        if state is None:
            raise RuntimeError("reset must be called before respond")

        parsed = self.state_machine.update(state, user_message, turn)
        ranked = self.retriever.rank(state, top_k)
        self._update_stall_detector(state, ranked)

        ask_attribute = select_ask_attribute(ranked, state, self.catalog)
        if ask_attribute:
            state.asked_attributes[ask_attribute] = state.asked_attributes.get(ask_attribute, 0) + 1
        state.last_ask_attribute = ask_attribute

        top_product = self.catalog.get_product(ranked[0][0]) if ranked else None
        question_override = None
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        if ask_attribute and self.llm.enabled:
            question_override = self.llm.phrase_question(
                ask_attribute, " ".join(state.category_terms)
            )
            usage = self.llm.last_usage()
        message = compose(state, ask_attribute, top_product, question_override)
        recommendations = [{"parent_asin": asin} for asin, _ in ranked[:top_k]]

        self.trace_log.session(session_id).record(
            turn=turn,
            pool_size=len(ranked),
            ask_attribute=ask_attribute,
            why="stop-rule" if ask_attribute is None else "policy pick",
            top_asins=[asin for asin, _ in ranked[:5]],
            parsed_summary={
                "override": parsed.override,
                "boundary": parsed.boundary_attr,
                "exhausted": parsed.exhausted_attr,
                "filled": [attribute for attribute, _ in parsed.filled],
            },
        )

        return build_safe_response(
            message,
            ask_attribute,
            recommendations,
            usage,
            self.catalog.catalog_ids,
        )

    @staticmethod
    def _update_stall_detector(state: SessionState, ranked: list[tuple[str, float]]) -> None:
        state.pool_size_history.append(len(ranked))
        history = state.pool_size_history
        if len(history) >= config.STALL_TURNS and len(set(history[-config.STALL_TURNS:])) == 1:
            state.relax_filters = True

    # -- fallback tiers ----------------------------------------------------

    def _bm25_fallback(self, user_message: str, top_k: int) -> dict:
        ranked = self.catalog.bm25_search(tokenize(user_message), top_k)
        return build_safe_response(
            "Here are the closest matches I found.",
            None,
            [{"parent_asin": asin} for asin, _ in ranked],
            {"prompt_tokens": 0, "completion_tokens": 0},
            self.catalog.catalog_ids,
        )
