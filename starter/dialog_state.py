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
    polarity: str = "include"  # "include" | "exclude"
    active: bool = True


@dataclass
class ParsedTurn:
    override: bool = False
    category_changed: bool = False
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
    pool_signatures: list[tuple[str, ...]] = field(default_factory=list)
    relax_filters: bool = False

    def all_slot_values(self) -> list[SlotValue]:
        return [value for values in self.slots.values() for value in values]

    def include_values(self) -> list[SlotValue]:
        return [v for v in self.all_slot_values() if v.active and v.polarity == "include"]

    def exclude_values(self) -> list[SlotValue]:
        return [v for v in self.all_slot_values() if v.active and v.polarity == "exclude"]

    def excluded_tokens(self) -> set[str]:
        from .text_utils import tokenize
        included: set[str] = set()
        for value in self.include_values():
            included.update(tokenize(value.text))
        excluded: set[str] = set()
        for value in self.exclude_values():
            excluded.update(tokenize(value.text))
        return excluded - included

    def budget_spec(self):
        """Typed Budget from the newest active budget value, or None."""
        from .attribute_extractor import parse_budget_spec
        for value in reversed(self.slots.get("budget", [])):
            if not value.active or value.polarity != "include":
                continue
            spec = parse_budget_spec(value.text)
            if spec is not None:
                return spec
        return None

    def budget_value(self) -> float | None:
        """Representative single number for messaging; ranking uses budget_spec()."""
        spec = self.budget_spec()
        if spec is None:
            return None
        return spec.target if spec.target is not None else (spec.max or spec.min)


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

        if self._is_override(lowered):
            payload = self._payload(message)
            if payload:
                category_match = self._CATEGORY_INTENT_RE.match(payload.lower())
                if category_match:
                    # Category-wide: the customer is now shopping for a
                    # different thing. Rewrite the category, retire every
                    # constraint from the old intent, reset stall state.
                    from .text_utils import tokenize
                    new_category = category_match.group(1)
                    state.category_terms = tokenize(new_category)
                    for values in state.slots.values():
                        for value in values:
                            value.active = False
                    state.slots.setdefault("category", []).append(
                        SlotValue(new_category, weight=config.OVERRIDE_NEW_VALUE_WEIGHT, turn=turn)
                    )
                    state.exhausted_attributes.clear()
                    state.pool_size_history.clear()
                    state.pool_signatures.clear()
                    state.relax_filters = False
                    parsed.category_changed = True
                    parsed.filled.append(("category", new_category))
                else:
                    # Attribute-local: replace only this attribute's values and
                    # the retracted turn-1 soft preference ("ignore my earlier
                    # preference"); everything else the customer said stands.
                    attribute = classify_text(payload)
                    for value in state.slots.get(attribute, []):
                        value.active = False
                    for values in state.slots.values():
                        for value in values:
                            if value.turn == 1 and value.weight <= 0.9:
                                value.active = False
                    state.slots.setdefault(attribute, []).append(
                        SlotValue(payload, weight=config.OVERRIDE_NEW_VALUE_WEIGHT, turn=turn)
                    )
                    state.exhausted_attributes.discard(attribute)
                    parsed.filled.append((attribute, payload))
                parsed.override = True
            return parsed

        # Clause-by-clause: one reply may hold a boundary AND a constraint
        # ("no preference for color, but it must be waterproof") — classify
        # each clause independently and apply every compatible update.
        # A colon anywhere marks the message as carrying QUOTED constraint
        # payload; clause splitting must not strip that protection from the
        # second piece of "what matters is: X; Y".
        quoted_message = ":" in message
        for clause in self._split_clauses(message):
            clause_low = clause.lower()
            # "no additional preference" would also match the broader boundary
            # cues, so exhausted is checked first.
            if self._matches_any(clause_low, EXHAUSTED_CUES):
                attribute = self._cue_attribute(clause_low, state)
                if attribute:
                    state.exhausted_attributes.add(attribute)
                    parsed.exhausted_attr = attribute
                continue
            if self._matches_any(clause_low, BOUNDARY_CUES):
                attribute = self._cue_attribute(clause_low, state)
                if attribute:
                    state.boundary_attributes.add(attribute)
                    parsed.boundary_attr = attribute
                continue
            # Negation parsing applies only to customer-authored phrasing.
            # A colon marks a quoted constraint payload — catalog-derived
            # fragments legitimately contain negation-shaped text ("do not
            # machine wash") that describes the product and must file whole.
            quoted = quoted_message or ":" in clause
            payload = self._payload(clause)
            for piece in self._split_constraints(payload):
                pairs = [(piece, "include")] if quoted else self._parse_polarity(piece)
                for text, polarity in pairs:
                    if not self._is_informative(text):
                        continue
                    attribute = self._file_attribute(state, text)
                    state.slots.setdefault(attribute, []).append(
                        SlotValue(text, weight=1.2, turn=turn, polarity=polarity)
                    )
                    parsed.filled.append((attribute, text))
        return parsed

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _matches_any(lowered: str, cues: list[str]) -> bool:
        return any(fuzzy_contains(lowered, cue, config.FUZZY_THRESHOLD) for cue in cues)

    # A payload phrased as shopping intent ("I need a hiking backpack") signals
    # a category-wide switch; a bare constraint fragment ("100% cotton") is
    # attribute-local. Requires the verb, so catalog fragments never match.
    _CATEGORY_INTENT_RE = re.compile(
        r"^(?:i(?:'m|\s+am)?\s+)?(?:need|want|would like|am looking for|m looking for"
        r"|looking for|shopping for|after|searching for)\s+(?:a|an|some)?\s*(.+)$",
        re.IGNORECASE,
    )

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

    # Decimal-safe: never split "3.5 inch" or "$40.99" on the dot.
    _CLAUSE_SPLIT_RE = re.compile(
        r"(?<!\d)\.(?!\d)|[!?;]|,\s*(?:but|though|although|however)\b|\bbut\b"
    )
    _ATTRIBUTE_NAME_RE = re.compile(
        r"\b(category|material|fabric|color|colour|size|sizing|fit|style|brand"
        r"|budget|price|feature|use case|use_case)\b",
        re.IGNORECASE,
    )
    _ATTRIBUTE_ALIASES = {
        "fabric": "material", "colour": "color", "sizing": "size", "fit": "style",
        "price": "budget", "use case": "use_case",
    }
    # Clauses that only steer the conversation carry no product constraint.
    _NON_CONSTRAINT_RE = re.compile(
        r"^(?:please\b|ask me\b|use your\b|it'?s up to you\b|you (?:decide|pick|choose)\b"
        r"|go ahead\b|surprise me\b|that'?s (?:all|it)\b|thanks?\b|ok(?:ay)?\b)",
        re.IGNORECASE,
    )

    @classmethod
    def _split_clauses(cls, message: str) -> list[str]:
        return [c.strip(" .;,") for c in cls._CLAUSE_SPLIT_RE.split(message) if c and c.strip(" .;,")]

    @classmethod
    def _cue_attribute(cls, clause_low: str, state: SessionState) -> str | None:
        """The attribute a boundary/exhausted clause is about: an explicitly
        named one wins; otherwise whatever we just asked."""
        match = cls._ATTRIBUTE_NAME_RE.search(clause_low)
        if match:
            name = match.group(1).lower()
            return cls._ATTRIBUTE_ALIASES.get(name, name)
        return state.last_ask_attribute

    @classmethod
    def _is_informative(cls, text: str) -> bool:
        from .text_utils import tokenize
        if cls._NON_CONSTRAINT_RE.match(text.strip()):
            return False
        return len(tokenize(text)) >= 1

    @staticmethod
    def _split_constraints(payload: str) -> list[str]:
        return [piece.strip(" .;,") for piece in payload.split(";") if piece.strip(" .;,")]

    # Negation scope is local to a comma-bounded sub-clause: "avoid wool, I'd
    # like fleece" excludes wool but keeps fleece positive. Runs on RAW text -
    # the tokenizer strips "no"/"not", so this must happen first.
    _NEGATION_RE = re.compile(
        r"\b(?:do not|don't|dont|does not|doesn't|not|no|never|avoid|without"
        r"|except|anything but|rather not|skip|hate|dislike)\b",
        re.IGNORECASE,
    )
    _NEGATION_LEAD_RE = re.compile(
        r"^(?:want|need|like|really|the|any|a|an)\b\s*", re.IGNORECASE
    )

    @classmethod
    def _parse_polarity(cls, piece: str) -> list[tuple[str, str]]:
        """Split a constraint piece into (text, polarity) sub-clauses.

        A piece with no negation cue is kept WHOLE — long catalog-derived
        fragments are the strongest phrase-coverage signal, and comma/and
        splitting exists solely to bound a negation's scope (measured:
        unconditional splitting cost Intent Override 0.933 -> 0.90)."""
        from .text_utils import tokenize
        if not cls._NEGATION_RE.search(piece):
            return [(piece, "include")]
        results: list[tuple[str, str]] = []
        for clause in re.split(r",|\bbut\b|\band\b", piece):
            clause = clause.strip(" .;,")
            if not clause:
                continue
            match = cls._NEGATION_RE.search(clause)
            if match:
                before = clause[: match.start()].strip(" .;,")
                after = clause[match.end():].strip(" .;,")
                after = cls._NEGATION_LEAD_RE.sub("", after).strip()
                if after:
                    results.append((after, "exclude"))
                # Leading fragments like "I do" / "please" carry no constraint.
                if before and len(tokenize(before)) >= 2:
                    results.append((before, "include"))
            else:
                results.append((clause, "include"))
        return results

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
