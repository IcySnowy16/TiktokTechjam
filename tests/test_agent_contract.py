"""Contract tests: the real Agent must return schema-valid responses under adversarial input."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starter.agent import Agent
from starter.vocab import ALLOWED_ATTRIBUTES

MINI_CATALOG = [
    {
        "parent_asin": f"B00000000{i}",
        "title": f"Test Product {i} cotton shirt blue",
        "features": ["Soft cotton"], "description": ["A test product"],
        "price": 10.0 + i, "categories": ["Clothing"], "details": {},
        "average_rating": 4.0, "rating_number": 10, "store": "TestCo",
    }
    for i in range(5)
]

ADVERSARIAL_MESSAGES = [
    "",
    "   ",
    "a" * 5000,
    "☃☃☃ unicode ☃☃☃ nonsense ☃",
    'weird "quotes" AND (fts5) OR syntax * NEAR/2 injection',
    "I'm looking for cotton shirts. A key requirement is: blue.",
    "no preference; please use your judgment",
    "Actually, ignore that. What I need is: red socks.",
]


def assert_valid_response(testcase: unittest.TestCase, response: dict, catalog_ids: set[str]):
    testcase.assertIsInstance(response, dict)
    testcase.assertEqual(
        set(response.keys()), {"message", "ask_attribute", "recommendations", "usage"}
    )
    testcase.assertIsInstance(response["message"], str)
    attr = response["ask_attribute"]
    testcase.assertTrue(attr is None or attr in ALLOWED_ATTRIBUTES)
    recs = response["recommendations"]
    testcase.assertIsInstance(recs, list)
    testcase.assertLessEqual(len(recs), 10)
    seen = set()
    for rec in recs:
        testcase.assertEqual(set(rec.keys()), {"parent_asin"})
        testcase.assertIn(rec["parent_asin"], catalog_ids)
        testcase.assertNotIn(rec["parent_asin"], seen)
        seen.add(rec["parent_asin"])
    usage = response["usage"]
    testcase.assertGreaterEqual(usage["prompt_tokens"], 0)
    testcase.assertGreaterEqual(usage["completion_tokens"], 0)


class AgentContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name) / "catalog.jsonl"
        path.write_text("\n".join(json.dumps(p) for p in MINI_CATALOG) + "\n", encoding="utf-8")
        cls.agent = Agent(path)
        cls.catalog_ids = {p["parent_asin"] for p in MINI_CATALOG}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_adversarial_turn_returns_a_valid_response(self):
        self.agent.reset("sess-1", {"preference_tags": ["comfort"], "rating_style": "usually positive"})
        for turn, message in enumerate(ADVERSARIAL_MESSAGES, start=1):
            response = self.agent.respond("sess-1", message, turn, 10)
            assert_valid_response(self, response, self.catalog_ids)

    def test_missing_reset_still_returns_valid_response(self):
        response = self.agent.respond("never-reset", "hello", 1, 10)
        assert_valid_response(self, response, self.catalog_ids)

    def test_garbage_profile_is_tolerated(self):
        self.agent.reset("sess-2", None)  # type: ignore[arg-type]
        response = self.agent.respond("sess-2", "I'm looking for shirts.", 1, 10)
        assert_valid_response(self, response, self.catalog_ids)


if __name__ == "__main__":
    unittest.main()
