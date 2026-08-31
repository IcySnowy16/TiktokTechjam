"""Question policy tests: entropy scoring, stop rules, and retired attributes."""

from __future__ import annotations

import unittest
from unittest import mock

from starter import config
from starter.attribute_extractor import ProductAttributes
from starter.dialog_state import SessionState
from starter.question_policy import select_ask_attribute


class FakeCatalog:
    """Half the pool is red, half blue (color splits); everything is cotton (material doesn't)."""

    def __init__(self):
        self.attrs = {}
        for i in range(10):
            color = {"red"} if i % 2 == 0 else {"blue"}
            self.attrs[f"A{i}"] = ProductAttributes(material={"cotton"}, color=color)

    def get_attributes(self, asin):
        return self.attrs.get(asin, ProductAttributes())


def make_pool(n=10):
    return [(f"A{i}", 1.0 - i * 0.01) for i in range(n)]


class AdaptiveSelectionTest(unittest.TestCase):
    def setUp(self):
        self._patch = mock.patch.object(config, "ADAPTIVE_QUESTIONS", True)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_entropy_prefers_the_splitting_attribute(self):
        state = SessionState("s", {}, turn=2)
        picked = select_ask_attribute(make_pool(), state, FakeCatalog())
        self.assertEqual(picked, "color")

    def test_boundary_attribute_is_never_selected(self):
        state = SessionState("s", {}, turn=2)
        state.boundary_attributes.add("color")
        picked = select_ask_attribute(make_pool(), state, FakeCatalog())
        self.assertNotEqual(picked, "color")

    def test_exhausted_attribute_is_never_selected(self):
        state = SessionState("s", {}, turn=2)
        state.exhausted_attributes.add("color")
        picked = select_ask_attribute(make_pool(), state, FakeCatalog())
        self.assertNotEqual(picked, "color")


class StopRuleTest(unittest.TestCase):
    def test_stops_after_max_question_turn(self):
        state = SessionState("s", {}, turn=config.MAX_QUESTION_TURN)
        self.assertIsNone(select_ask_attribute(make_pool(), state, FakeCatalog()))

    def test_stops_on_tiny_pool(self):
        state = SessionState("s", {}, turn=2)
        tiny = make_pool()[: config.CONFIDENT_POOL_SIZE]
        self.assertIsNone(select_ask_attribute(tiny, state, FakeCatalog()))

    def test_stops_on_clear_leader(self):
        state = SessionState("s", {}, turn=2)
        pool = [("A0", 10.0), ("A1", 1.0), ("A2", 0.9), ("A3", 0.8), ("A4", 0.7)]
        self.assertIsNone(select_ask_attribute(pool, state, FakeCatalog()))

    def test_keeps_asking_on_flat_large_pool(self):
        state = SessionState("s", {}, turn=2)
        self.assertIsNotNone(select_ask_attribute(make_pool(), state, FakeCatalog()))


if __name__ == "__main__":
    unittest.main()
