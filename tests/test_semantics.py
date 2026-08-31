"""Adversarial conversation semantics — hand-written paraphrases, none copied
from evaluator templates. Phase 1 hardening regression suite."""

from __future__ import annotations

import unittest

from starter.dialog_state import DialogStateMachine, SessionState


def make_state() -> SessionState:
    return SessionState(session_id="t", user_profile={})


def run_turns(machine, state, messages, start_turn=2):
    for offset, message in enumerate(messages):
        state.last_ask_attribute = state.last_ask_attribute  # explicitized per-test
        machine.update(state, message, start_turn + offset)


class NegationTest(unittest.TestCase):
    def setUp(self):
        self.machine = DialogStateMachine()
        self.state = make_state()

    def _values(self, attr):
        return [(v.text, v.polarity) for v in self.state.slots.get(attr, [])]

    def test_negated_material_excluded_positive_kept(self):
        self.state.last_ask_attribute = "material"
        self.machine.update(self.state, "I do not want leather; cotton is fine", 2)
        values = self.state.slots.get("material", [])
        polarities = {v.polarity for v in values}
        self.assertIn("exclude", polarities, "negated value must be polarity=exclude")
        excluded = [v.text for v in values if v.polarity == "exclude"]
        included = [v.text for v in values if v.polarity == "include"]
        self.assertTrue(any("leather" in t.lower() for t in excluded))
        self.assertTrue(any("cotton" in t.lower() for t in included))

    def test_excluded_terms_never_in_positive_query(self):
        from starter.retriever import HybridRetriever

        class StubCatalog:
            catalog_ids = frozenset()
            def idf(self, t): return 1.0

        self.state.last_ask_attribute = "material"
        self.machine.update(self.state, "please avoid wool, I'd like fleece", 2)
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.catalog = StubCatalog()
        terms = retriever._query_terms(self.state)
        self.assertNotIn("wool", terms, "excluded term leaked into positive query")
        self.assertIn("fleece", terms)

    def test_bare_negation_no_positive(self):
        self.state.last_ask_attribute = "color"
        self.machine.update(self.state, "no black please", 2)
        values = self.state.slots.get("color", [])
        self.assertTrue(values, "clause should still be filed")
        self.assertTrue(all(v.polarity == "exclude" for v in values))


if __name__ == "__main__":
    unittest.main()


class MixedClauseTest(unittest.TestCase):
    """A single reply can carry a boundary AND a constraint; both must land."""

    def setUp(self):
        self.machine = DialogStateMachine()
        self.state = make_state()

    def test_boundary_plus_constraint_keeps_both(self):
        self.state.last_ask_attribute = "color"
        self.machine.update(
            self.state, "I have no preference for color, but it must be waterproof", 2
        )
        self.assertIn("color", self.state.boundary_attributes)
        filed = [v.text.lower() for v in self.state.all_slot_values()]
        self.assertTrue(any("waterproof" in t for t in filed),
                        f"constraint clause lost; slots={filed}")

    def test_exhausted_plus_budget_keeps_budget(self):
        self.state.last_ask_attribute = "material"
        self.machine.update(
            self.state,
            "Nothing more about material; though the price should stay under $40",
            2,
        )
        self.assertIn("material", self.state.exhausted_attributes)
        self.assertTrue(self.state.slots.get("budget") or self.state.slots.get("feature"),
                        "budget clause was dropped")

    def test_pure_boundary_files_nothing(self):
        self.state.last_ask_attribute = "size"
        self.machine.update(
            self.state, "I'm easy on sizing - use your judgment there", 2
        )
        self.assertIn("size", self.state.boundary_attributes)
        self.assertEqual(self.state.all_slot_values(), [])

    def test_boundary_names_attribute_not_asked(self):
        # Customer volunteers a boundary about a DIFFERENT attribute than asked.
        self.state.last_ask_attribute = "material"
        self.machine.update(
            self.state, "Honestly any color works for me, no preference there", 2
        )
        self.assertIn("color", self.state.boundary_attributes,
                      "named attribute in the boundary clause should win over last_ask")


class OverrideScopeTest(unittest.TestCase):
    """Overrides must be scoped: category-wide rewrites the category; attribute-
    local replaces one slot and leaves the rest of the state untouched."""

    def setUp(self):
        self.machine = DialogStateMachine()
        self.state = make_state()

    def test_category_override_replaces_category(self):
        self.machine.update(self.state, "I'm looking for running shoes.", 1)
        self.machine.update(
            self.state, "Actually, change of plans: I need a hiking backpack", 3
        )
        terms = set(self.state.category_terms)
        self.assertIn("backpack", terms, f"category not rewritten: {terms}")
        self.assertNotIn("shoes", terms, f"stale category survives: {terms}")

    def test_category_override_retires_old_constraints_and_stall(self):
        self.machine.update(self.state, "I'm looking for running shoes.", 1)
        self.state.last_ask_attribute = "material"
        self.machine.update(self.state, "For that, what matters is: leather upper", 2)
        self.state.pool_size_history = [300, 300, 300]
        self.state.relax_filters = True
        self.machine.update(
            self.state, "Actually, change of plans: I need a hiking backpack", 3
        )
        old = [v for v in self.state.slots.get("material", []) if "leather" in v.text.lower()]
        self.assertTrue(old and all(not v.active for v in old),
                        "old-category constraint still active after category switch")
        self.assertFalse(self.state.relax_filters, "stall state must reset on category change")
        self.assertEqual(self.state.pool_size_history, [])

    def test_attribute_local_override_keeps_unrelated_slots(self):
        self.machine.update(self.state, "I'm looking for a winter jacket.", 1)
        self.state.last_ask_attribute = "color"
        self.machine.update(self.state, "For that, what matters is: color: black", 2)
        self.state.last_ask_attribute = None
        self.machine.update(
            self.state,
            "Actually, ignore my earlier preference. What I need is: 100% cotton fabric",
            3,
        )
        colors = self.state.slots.get("color", [])
        self.assertTrue(colors, "unrelated color slot vanished")
        for value in colors:
            self.assertTrue(value.active, "unrelated slot deactivated by local override")
            self.assertGreaterEqual(value.weight, 1.0,
                                    "unrelated slot decayed by local override")

    def test_local_override_retires_turn1_soft_preference(self):
        # Intent-override sessions state a soft preference on turn 1 and retract
        # it later - the retracted value must stop influencing retrieval.
        self.machine.update(
            self.state, "I'm looking for a winter jacket. I prefer a slim style fit", 1
        )
        self.machine.update(
            self.state,
            "Actually, ignore my earlier preference. What I need is: 100% cotton fabric",
            3,
        )
        soft = [v for values in self.state.slots.values() for v in values
                if v.turn == 1 and v.weight <= 0.9]
        self.assertTrue(soft, "test setup: turn-1 soft preference should exist")
        self.assertTrue(all(not v.active for v in soft),
                        "retracted turn-1 preference still active")


class TypedBudgetTest(unittest.TestCase):
    """Budget phrases carry operators, not just a number."""

    def _spec(self, text):
        from starter.attribute_extractor import parse_budget_spec
        return parse_budget_spec(text)

    def test_maximum(self):
        spec = self._spec("it should stay under $50")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.max, 50.0)
        self.assertIsNone(spec.min)
        self.assertTrue(spec.satisfied(45.0))
        self.assertTrue(spec.violated(60.0))

    def test_minimum(self):
        spec = self._spec("something over $50, quality matters")
        self.assertEqual(spec.min, 50.0)
        self.assertIsNone(spec.max)
        self.assertTrue(spec.satisfied(80.0))
        self.assertTrue(spec.violated(20.0))

    def test_range(self):
        spec = self._spec("between $20 and $40 please")
        self.assertEqual((spec.min, spec.max), (20.0, 40.0))
        self.assertTrue(spec.satisfied(30.0))
        self.assertTrue(spec.violated(45.0))
        self.assertTrue(spec.violated(15.0))

    def test_target(self):
        spec = self._spec("budget around $50")
        self.assertEqual(spec.target, 50.0)
        self.assertTrue(spec.satisfied(52.0))
        self.assertTrue(spec.violated(120.0))

    def test_size_number_is_not_budget(self):
        self.assertIsNone(self._spec("I wear size 12"))
        self.assertIsNone(self._spec("a 15 inch laptop sleeve"))

    def test_exclude_values_never_match_stage_b(self):
        """Excluded attribute tokens must not produce Stage-B match bonuses."""
        from starter.retriever import HybridRetriever
        from starter.dialog_state import SlotValue

        class StubAttrs:
            material = {"leather"}
            color = set()
            size = set()
            style = set()
            use_case = set()
            price = None
            def values_for(self, a): return getattr(self, a, set()) or set()

        class StubCatalog:
            def get_attributes(self, asin): return StubAttrs()
            def idf(self, t): return 1.0

        state = make_state()
        state.slots["material"] = [SlotValue("leather", polarity="exclude")]
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.catalog = StubCatalog()
        score = retriever._attribute_score(state, "X", {"leather"}, None, False)
        self.assertLessEqual(score, 0.0,
                             "excluded value produced a positive Stage-B bonus")


class QuestionPolicyDeterminismTest(unittest.TestCase):
    """Questions must be reproducible across hash seeds and never re-ask what
    the customer already answered."""

    def _catalog_stub(self):
        class StubAttrs:
            def __init__(self, material, color):
                self.material = material
                self.color = color
                self.size = set(); self.style = set(); self.use_case = set()
                self.price = None
            def values_for(self, a): return getattr(self, a, set()) or set()

        class StubCatalog:
            def __init__(self):
                self._attrs = {
                    "A": StubAttrs({"cotton"}, {"red"}),
                    "B": StubAttrs({"wool"}, {"blue"}),
                    "C": StubAttrs({"silk"}, {"red"}),
                    "D": StubAttrs({"denim"}, {"blue"}),
                }
            def get_attributes(self, asin): return self._attrs[asin]
        return StubCatalog()

    def test_askable_preserves_fixed_order(self):
        from starter import question_policy
        state = make_state()
        askable = question_policy._askable(state)
        from starter import config
        expected = [a for a in config.FIXED_QUESTION_ORDER if a in set(askable)]
        self.assertEqual(askable, expected,
                         "_askable must be an ordered list, not set-iteration order")

    def test_known_attribute_not_reasked(self):
        from starter import question_policy
        from starter.dialog_state import SlotValue
        state = make_state()
        state.slots["material"] = [SlotValue("100% merino wool", turn=2)]
        askable = question_policy._askable(state)
        self.assertNotIn("material", askable,
                         "an answered attribute must not be asked again")

    def test_selection_is_deterministic(self):
        from starter.question_policy import select_ask_attribute
        state = make_state()
        pool = [("A", 1.0), ("B", 0.9), ("C", 0.8), ("D", 0.7)]
        first = select_ask_attribute(pool, state, self._catalog_stub())
        for _ in range(20):
            self.assertEqual(
                select_ask_attribute(pool, state, self._catalog_stub()), first
            )

    def test_other_capped_at_one(self):
        from starter import config
        self.assertLessEqual(config.MAX_ASKS_PER_ATTRIBUTE.get("other", config.DEFAULT_MAX_ASKS), 1,
                             "'other' is a last resort: at most one ask per session")


class StallDetectionTest(unittest.TestCase):
    """Stall = the same candidates keep coming back with no new evidence —
    never just 'the list length did not change'."""

    def _agent_stub(self):
        from starter.agent import Agent
        agent = Agent.__new__(Agent)  # no catalog load
        return agent

    def _parsed(self, filled=False):
        from starter.dialog_state import ParsedTurn
        parsed = ParsedTurn()
        if filled:
            parsed.filled.append(("material", "cotton"))
        return parsed

    def test_different_rankings_same_length_is_not_stall(self):
        agent = self._agent_stub()
        state = make_state()
        for ranked in ([("A", 1.0), ("B", 0.9)], [("C", 1.0), ("D", 0.9)], [("E", 1.0), ("F", 0.9)]):
            agent._update_stall_detector(state, ranked, self._parsed())
        self.assertFalse(state.relax_filters,
                         "length-only comparison flagged distinct rankings as a stall")

    def test_repeated_signature_is_stall(self):
        agent = self._agent_stub()
        state = make_state()
        ranked = [("A", 1.0), ("B", 0.9), ("C", 0.8)]
        for _ in range(3):
            agent._update_stall_detector(state, ranked, self._parsed())
        self.assertTrue(state.relax_filters)

    def test_new_evidence_resets_stall(self):
        agent = self._agent_stub()
        state = make_state()
        ranked = [("A", 1.0), ("B", 0.9)]
        for _ in range(3):
            agent._update_stall_detector(state, ranked, self._parsed())
        self.assertTrue(state.relax_filters)
        agent._update_stall_detector(state, ranked, self._parsed(filled=True))
        self.assertFalse(state.relax_filters,
                         "a newly filed constraint must reset the stall flag")


class TransactionalTurnTest(unittest.TestCase):
    """A failure mid-turn must not commit partial conversation state."""

    def test_exception_after_parsing_does_not_commit_state(self):
        from starter.agent import Agent
        from starter.dialog_state import DialogStateMachine, SessionState

        agent = Agent.__new__(Agent)
        agent.state_machine = DialogStateMachine()
        agent._sessions = {}

        class ExplodingRetriever:
            def rank(self, state, top_k): raise RuntimeError("boom")

        class StubCatalog:
            catalog_ids = frozenset()
            def bm25_search(self, terms, k): return []
            def get_product(self, asin): return {}

        agent.retriever = ExplodingRetriever()
        agent.catalog = StubCatalog()
        agent.reset("s1", {})
        response = agent.respond("s1", "For that, what matters is: 100% cotton", 2, 10)
        self.assertIsInstance(response, dict)  # fallback, never a raise
        self.assertEqual(agent._sessions["s1"].slots, {},
                         "partial state committed despite mid-turn failure")
        self.assertEqual(agent._sessions["s1"].utterance_log, [],
                         "utterance log mutated despite mid-turn failure")


class RecencyTest(unittest.TestCase):
    """A post-override value must actually outweigh a stale one in phrase scoring."""

    def test_override_value_beats_stale_value(self):
        from starter.retriever import HybridRetriever
        from starter.dialog_state import SlotValue
        from starter import config

        class StubCatalog:
            def idf(self, t): return 1.0

        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.catalog = StubCatalog()
        values = [
            SlotValue("crimson silk scarf", weight=1.2, turn=2),
            SlotValue("navy wool beanie", weight=config.OVERRIDE_NEW_VALUE_WEIGHT, turn=4),
        ]
        doc_old = {"crimson", "silk", "scarf"}       # matches only the stale value
        doc_new = {"navy", "wool", "beanie"}          # matches only the override
        self.assertGreater(
            retriever._phrase_score(values, doc_new),
            retriever._phrase_score(values, doc_old),
            "override recency must make the new value dominate",
        )

    def test_lone_override_value_gets_absolute_boost(self):
        from starter.retriever import HybridRetriever
        from starter.dialog_state import SlotValue
        from starter import config

        class StubCatalog:
            def idf(self, t): return 1.0

        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.catalog = StubCatalog()
        plain = [SlotValue("navy wool beanie", weight=1.2, turn=2)]
        boosted = [SlotValue("navy wool beanie", weight=config.OVERRIDE_NEW_VALUE_WEIGHT, turn=4)]
        doc = {"navy", "wool", "beanie"}
        self.assertGreater(
            retriever._phrase_score(boosted, doc),
            retriever._phrase_score(plain, doc),
            "recency factor cancels out for a lone value (numerator AND denominator)",
        )


class ProfileRobustnessTest(unittest.TestCase):
    def test_string_tags_and_nan_rating_sanitized(self):
        from starter.agent import Agent
        agent = Agent.__new__(Agent)
        agent._sessions = {}
        agent.reset("s", {"preference_tags": "comfort", "average_prior_rating": float("nan")})
        profile = agent._sessions["s"].user_profile
        self.assertEqual(profile["preference_tags"], [],
                         "a string preference_tags must not survive as iterable chars")
        self.assertIsNone(profile["average_prior_rating"])

    def test_nan_product_rating_scores_zero(self):
        from starter.personalization import rating_prior
        self.assertEqual(rating_prior({"average_rating": float("nan"), "rating_number": 50}, ""), 0.0)


class DemoExposedBugsTest(unittest.TestCase):
    """Bugs surfaced by the free-form demo conversation (tools/demo_session.py)."""

    def test_junk_exclusion_not_filed(self):
        # "I don't like the look of it" must not exclude 'look'.
        machine = DialogStateMachine()
        state = make_state()
        machine.update(state, "No suede please, I don't like the look of it", 2)
        excludes = [v.text.lower() for v in state.exclude_values()]
        self.assertTrue(any("suede" in t for t in excludes), excludes)
        self.assertFalse(any("look" in t for t in excludes),
                         f"junk phrase filed as exclusion: {excludes}")

    def test_budget_slot_text_not_in_lexical_query(self):
        from starter.retriever import HybridRetriever
        from starter.dialog_state import SlotValue

        class StubCatalog:
            def idf(self, t): return 1.0

        state = make_state()
        state.slots["budget"] = [SlotValue("they should stay under $150", turn=2)]
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.catalog = StubCatalog()
        terms = retriever._query_terms(state)
        self.assertNotIn("stay", terms,
                         "budget operator text polluted the lexical query")

    def test_category_coverage_boosts_on_category_items(self):
        from starter.retriever import HybridRetriever
        from starter import config

        class StubCatalog:
            def idf(self, t): return 1.0

        state = make_state()
        state.category_terms = ["men", "leather", "shoes"]
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.catalog = StubCatalog()
        on_cat = retriever._category_score(state, {"men", "leather", "shoes", "oxford"})
        off_cat = retriever._category_score(state, {"belt", "buckle", "leather"})
        self.assertGreater(on_cat, off_cat,
                           "category coverage must separate shoes from belts")
        self.assertGreater(config.W_CATEGORY, 0)


class UnknownPriceTest(unittest.TestCase):
    def test_unknown_price_gets_partial_budget_credit(self):
        """A stated budget must not zero out candidates with missing prices —
        unknown is not a violation (demo-measured: cheap junk with known prices
        outranked the correct category match whose price field was empty)."""
        from starter.retriever import HybridRetriever
        from starter.attribute_extractor import Budget

        class StubAttrs:
            material = set(); color = set(); size = set()
            style = set(); use_case = set()
            def __init__(self, price): self.price = price
            def values_for(self, a): return getattr(self, a, set()) or set()

        class StubCatalog:
            def __init__(self): self.attrs = {}
            def get_attributes(self, asin): return self.attrs[asin]
            def idf(self, t): return 1.0

        retriever = HybridRetriever.__new__(HybridRetriever)
        catalog = StubCatalog()
        retriever.catalog = catalog
        state = make_state()
        budget = Budget(max=150.0)
        catalog.attrs = {"known": StubAttrs(20.0), "unknown": StubAttrs(None), "over": StubAttrs(400.0)}
        known = retriever._attribute_score(state, "known", set(), budget, False)
        unknown = retriever._attribute_score(state, "unknown", set(), budget, False)
        over = retriever._attribute_score(state, "over", set(), budget, False)
        self.assertGreater(unknown, 0.0)
        # Only VIOLATIONS move ranking: unknown price is not evidence of
        # non-compliance, so it earns no less than a verified-satisfied price.
        self.assertGreaterEqual(known, unknown)
        self.assertGreater(unknown, over)
