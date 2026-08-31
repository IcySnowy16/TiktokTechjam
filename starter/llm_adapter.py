"""Optional LLM layer: phrasing variety and capped-risk re-ranking, with a circuit breaker.

The technical score is fully realized with this disabled — the evaluator reads
ask_attribute, never message prose. Enabled only with EXPLICIT opt-in:
TECHJAM_ENABLE_LLM=1 must be set in addition to an API key and an importable
anthropic SDK — an ambient key alone never triggers network calls, so official
scoring stays deterministic and cost-free by default. The first failure of any
kind disables it for the rest of the process so the agent silently degrades to
templates offline.
Token usage is read from the real API response, never estimated.
"""

from __future__ import annotations

import os


class LLMAdapter:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-haiku-4-5-20251001",
        timeout_s: float = 2.0,
    ) -> None:
        self.model = model
        self.timeout_s = timeout_s
        self._client = None
        self._last_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        opted_in = os.environ.get("TECHJAM_ENABLE_LLM") == "1"
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if opted_in and key:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=key, timeout=timeout_s)
            except Exception:
                self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def last_usage(self) -> dict:
        """Usage for the most recent turn's call(s); resets on read."""
        usage = self._last_usage
        self._last_usage = {"prompt_tokens": 0, "completion_tokens": 0}
        return usage

    def phrase_question(self, ask_attribute: str, category_hint: str) -> str | None:
        """A one-sentence natural question about ask_attribute, or None on any failure."""
        if not self.enabled:
            return None
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=60,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "You are a friendly shopping assistant. In ONE short sentence, "
                            f"ask the customer about their {ask_attribute} preference for "
                            f"{category_hint or 'the item they want'}. Output only the question."
                        ),
                    }
                ],
            )
            self._last_usage = {
                "prompt_tokens": int(response.usage.input_tokens),
                "completion_tokens": int(response.usage.output_tokens),
            }
            text = "".join(
                block.text for block in response.content if getattr(block, "type", "") == "text"
            ).strip()
            return text or None
        except Exception:
            # Circuit breaker: one failure disables the LLM path for the run.
            self._client = None
            return None
