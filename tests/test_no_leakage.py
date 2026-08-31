"""Guards: production code never touches evaluator internals, public labels, or
ambient credentials. These tests protect the submission's integrity claims."""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

STARTER = Path(__file__).resolve().parent.parent / "starter"
FORBIDDEN_SOURCE_PATTERNS = [
    r"from\s+evaluator", r"import\s+evaluator",
    r"public_set\.jsonl", r"results\.json",
    r"ground_truth", r"sample_id", r"scenario_type",
]
# Catalog ASINs are only ever data, never literals in code.
HARDCODED_ASIN = re.compile(r'"B0[A-Z0-9]{8}"')


class NoLeakageTest(unittest.TestCase):
    def test_no_forbidden_references_in_source(self):
        for path in STARTER.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for pattern in FORBIDDEN_SOURCE_PATTERNS:
                self.assertIsNone(
                    re.search(pattern, source),
                    f"{path.name} references forbidden pattern {pattern!r}",
                )
            self.assertIsNone(
                HARDCODED_ASIN.search(source),
                f"{path.name} contains a hardcoded ASIN literal",
            )

    def test_importing_agent_does_not_import_evaluator(self):
        for name in list(sys.modules):
            if name.startswith("evaluator"):
                del sys.modules[name]
        import starter.agent  # noqa: F401
        loaded = [name for name in sys.modules if name.startswith("evaluator")]
        self.assertEqual(loaded, [], "importing starter.agent pulled in evaluator modules")


class LLMOptInTest(unittest.TestCase):
    def test_ambient_key_alone_does_not_enable(self):
        from starter.llm_adapter import LLMAdapter
        old_key = os.environ.get("ANTHROPIC_API_KEY")
        old_flag = os.environ.pop("TECHJAM_ENABLE_LLM", None)
        os.environ["ANTHROPIC_API_KEY"] = "sk-test-ambient-not-real"
        try:
            self.assertFalse(LLMAdapter().enabled,
                             "ambient ANTHROPIC_API_KEY must not enable the LLM without opt-in")
        finally:
            if old_key is None:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            else:
                os.environ["ANTHROPIC_API_KEY"] = old_key
            if old_flag is not None:
                os.environ["TECHJAM_ENABLE_LLM"] = old_flag

    def test_explicit_constructor_key_alone_does_not_enable(self):
        from starter.llm_adapter import LLMAdapter
        old_flag = os.environ.pop("TECHJAM_ENABLE_LLM", None)
        try:
            self.assertFalse(LLMAdapter(api_key="sk-test-not-real").enabled)
        finally:
            if old_flag is not None:
                os.environ["TECHJAM_ENABLE_LLM"] = old_flag


if __name__ == "__main__":
    unittest.main()
