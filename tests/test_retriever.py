"""Retriever tests on a tiny controlled catalog: phrase boost and soft attribute filtering."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from starter import config
from starter.catalog_store import CatalogStore
from starter.dialog_state import SessionState, SlotValue
from starter.retriever import HybridRetriever

MINI_CATALOG = [
    {
        "parent_asin": "TARGET1",
        "title": "Womens Running Shoes Lightweight Breathable Mesh Sneakers",
        "features": ["Breathable knit mesh upper keeps feet cool", "Memory foam insole"],
        "description": ["Great for running and gym workouts"],
        "price": 29.99, "categories": ["Shoes"], "details": {"Color": "black"},
        "average_rating": 4.5, "rating_number": 1200, "store": "RunCo",
    },
    {
        "parent_asin": "DISTRACT1",
        "title": "Womens Leather Ankle Boots Waterproof",
        "features": ["Full grain leather", "Waterproof seal"],
        "description": ["Winter ready boots"],
        "price": 89.99, "categories": ["Shoes"], "details": {"Color": "brown"},
        "average_rating": 4.2, "rating_number": 300, "store": "BootCo",
    },
    {
        "parent_asin": "DISTRACT2",
        "title": "Womens Canvas Slip On Casual Shoes",
        "features": ["Canvas upper", "Rubber sole"],
        "description": ["Everyday casual comfort"],
        "price": 24.99, "categories": ["Shoes"], "details": {"Color": "red"},
        "average_rating": 4.0, "rating_number": 800, "store": "CasualCo",
    },
]


class RetrieverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name) / "catalog.jsonl"
        path.write_text(
            "\n".join(json.dumps(p) for p in MINI_CATALOG) + "\n", encoding="utf-8"
        )
        cls.catalog = CatalogStore(path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _state(self) -> SessionState:
        state = SessionState("s", {"preference_tags": []})
        state.category_terms = ["womens", "shoes"]
        return state

    def test_phrase_boost_ranks_near_literal_fragment_holder_first(self):
        state = self._state()
        # Reworded fragment of TARGET1's own feature text (order shuffled, words dropped).
        state.slots["feature"] = [SlotValue("knit mesh upper breathable", weight=1.2, turn=2)]
        with mock.patch.object(config, "W_PHRASE", 3.0):
            ranked = HybridRetriever(self.catalog).rank(state)
        self.assertEqual(ranked[0][0], "TARGET1")

    def test_contradicting_attribute_is_penalized_not_excluded(self):
        state = self._state()
        state.slots["material"] = [SlotValue("full grain leather", weight=1.2, turn=2)]
        with mock.patch.object(config, "W_ATTR", 1.0):
            ranked = HybridRetriever(self.catalog).rank(state)
        asins = [asin for asin, _ in ranked]
        self.assertEqual(asins[0], "DISTRACT1")  # the leather product wins
        self.assertIn("TARGET1", asins)  # mesh product penalized but never dropped

    def test_budget_match_boosts_affordable_candidates(self):
        state = self._state()
        state.slots["budget"] = [SlotValue("budget around $28", weight=1.2, turn=2)]
        with mock.patch.object(config, "W_ATTR", 1.0):
            ranked = HybridRetriever(self.catalog).rank(state)
        scores = dict(ranked)
        self.assertGreater(scores["TARGET1"], scores["DISTRACT1"])


if __name__ == "__main__":
    unittest.main()
