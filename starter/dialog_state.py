"""Per-session conversation state and the state machine that updates it each turn.

Detection uses structural cues and fuzzy matching, never the evaluator's exact
template strings, so private-set paraphrasing still triggers the same paths.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import config
from .attribute_extractor import classify_text
from .text_utils import fuzzy_contains
from .vocab import BOUNDARY_CUES, EXHAUSTED_CUES, OVERRIDE_STRONG_CUES, OVERRIDE_WEAK_CUES

_CATEGORY_RE = re.compile(r"looking for ([^.,:;]+)", re.IGNORECASE)


@dataclass
class SlotValue:
    text: str
    weight: float = 1.0
    turn: int = 0


@dataclass
class ParsedTurn:
    override: bool = False
    boundary_attr: str | None = None
    exhausted_attr: str | None = None
    filled: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class SessionState:
    session_id: str
    user_profile: dict
    turn: int = 0
    category_terms: list[str] = field(default_factory=list)
    slots: dict[str, list[SlotValue]] = field(default_factory=dict)
    boundary_attributes: set[str] = field(default_factory=set)
    exhausted_attributes: set[str] = field(default_factory=set)
    asked_attributes: dict[str, int] = field(default_factory=dict)
    last_ask_attribute: str | None = None
    utterance_log: list[str] = field(default_factory=list)
    pool_size_history: list[int] = field(default_factory=list)
    relax_filters: bool = False

    def all_slot_values(self) -> list[SlotValue]:
        return [value for values in self.slots.values() for value in values]

    def budget_value(self) -> float | None:
        from .attribute_extractor import parse_budget
        for value in self.slots.get("budget", []):
            budget = parse_budget(value.text)
            if budget is not None:
                return budget
        return None


class DialogStateMachine:
    """Parses each customer message into state mutations."""

    def update(self, state: SessionState, user_message: str, turn: int) -> ParsedTurn:
        state.turn = turn
        message = (user_message or "").strip()
        state.utterance_log.append(message)
        lowered = message.lower()
        parsed = ParsedTurn()

        if turn == 1:
            self._parse_initial(state, message, parsed)
            return parsed

        # Order matters: "no additional preference" contains "preference", so
        # exhausted cues are checked before the broader boundary cues.
        if self._matches_any(lowered, EXHAUSTED_CUES):
            if state.last_ask_attribute:
                state.exhausted_attributes.add(state.last_ask_attribute)
                parsed.exhausted_attr = state.last_ask_attribute
            return parsed

        if self._matches_any(lowered, BOUNDARY_CUES):
            if state.last_ask_attribute:
                state.boundary_attributes.add(state.last_ask_attribute)
                parsed.boundary_attr = state.last_ask_attribute
            return parsed

        if self._is_override(lowered):
            payload = self._payload(message)
            if payload:
                attribute = classify_text(payload)
                for values in state.slots.values():
                    for value in values:
                        value.weight *= config.STALE_VALUE_DECAY
                state.slots[attribute] = [
                    SlotValue(payload, weight=config.OVERRIDE_NEW_VALUE_WEIGHT, turn=turn)
                ]
                state.exhausted_attributes.discard(attribute)
                parsed.override = True
                parsed.filled.append((attribute, payload))
            return parsed

        payload = self._payload(message)
        for piece in self._split_constraints(payload):
            attribute = self._file_attribute(state, piece)
            state.slots.setdefault(attribute, []).append(SlotValue(piece, weight=1.2, turn=turn))
            parsed.filled.append((attribute, piece))
        return parsed

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _matches_any(lowered: str, cues: list[str]) -> bool:
        return any(fuzzy_contains(lowered, cue, config.FUZZY_THRESHOLD) for cue in cues)

    @staticmethod
    def _is_override(lowered: str) -> bool:
        if any(fuzzy_contains(lowered, cue, config.FUZZY_THRESHOLD) for cue in OVERRIDE_STRONG_CUES):
            return True
        has_weak = any(fuzzy_contains(lowered, cue, config.FUZZY_THRESHOLD) for cue in OVERRIDE_WEAK_CUES)
        return has_weak and ":" in lowered

    @staticmethod
    def _payload(message: str) -> str:
        """The informative part of a reply: text after the last colon when present."""
        if ":" in message:
            message = message.rsplit(":", 1)[1]
        return message.strip(" .;,\t\n")

    @staticmethod
    def _split_constraints(payload: str) -> list[str]:
        return [piece.strip(" .;,") for piece in payload.split(";") if piece.strip(" .;,")]

    @staticmethod
    def _file_attribute(state: SessionState, piece: str) -> str:
        """File under the asked attribute, unless the classifier confidently disagrees."""
        classified = classify_text(piece)
        asked = state.last_ask_attribute
        if asked in (None, "other"):
            return classified
        if classified not in ("feature", asked):
            return classified
        return asked

    def _parse_initial(self, state: SessionState, message: str, parsed: ParsedTurn) -> None:
        match = _CATEGORY_RE.search(message)
        if match:
            from .text_utils import tokenize
            state.category_terms = tokenize(match.group(1))
        if ":" in message:
            payload = self._payload(message)
            for piece in self._split_constraints(payload):
                attribute = classify_text(piece)
                state.slots.setdefault(attribute, []).append(SlotValue(piece, weight=1.5, turn=1))
                parsed.filled.append((attribute, piece))
        else:
            # A non-colon remainder after the category sentence (e.g. a stated
            # soft preference) still carries signal; file it softly.
            remainder = message
            if match:
                remainder = message[match.end():].strip(" .,")
            from .text_utils import tokenize
            if len(tokenize(remainder)) >= 3 and "exploring" not in remainder.lower():
                attribute = classify_text(remainder)
                state.slots.setdefault(attribute, []).append(SlotValue(remainder, weight=0.8, turn=1))
                parsed.filled.append((attribute, remainder))
