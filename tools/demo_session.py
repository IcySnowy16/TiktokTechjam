"""Scripted demo conversation for the video — REAL agent, fixed inputs.

The agent is deterministic, so this exact transcript reproduces on every run
and every machine: definite answers with nothing hardcoded. The customer side
is scripted; every agent turn (questions, state, rankings) is computed live by
the shipped pipeline. Judges can rerun this command and see the same output.

Usage:  python -m tools.demo_session
"""

from __future__ import annotations

from starter.agent import Agent

SESSION = "demo-video"

# The customer's side of the conversation — chosen to showcase, in order:
# typed budget (max operator), negation (exclusion), boundary handling, and a
# scoped attribute override. Everything else on screen is computed.
SCRIPT = [
    "I'm looking for men's leather oxford dress shoes for the office.",
    "Genuine leather dress shoes for sure. And my budget is under $150.",
    "No suede please, I don't like the look of it.",
    "I have no preference for size, just make sure they look professional.",
    "Actually, ignore my earlier preference. What I need is: brown wingtip brogue dress shoes.",
]


def show_state(agent: Agent) -> None:
    state = agent._sessions[SESSION]
    active = {
        attr: [f"{'NOT ' if v.polarity == 'exclude' else ''}{v.text[:44]}"
               for v in values if v.active]
        for attr, values in state.slots.items()
        if any(v.active for v in values)
    }
    print(f"  [state] category={' '.join(state.category_terms)!r}")
    for attr, values in active.items():
        print(f"  [state] {attr}: {values}")
    if state.boundary_attributes:
        print(f"  [state] no-preference (never re-ask): {sorted(state.boundary_attributes)}")
    spec = state.budget_spec()
    if spec:
        print(f"  [state] budget: min={spec.min} max={spec.max} target={spec.target}")


def main() -> None:
    print("Loading catalog + building index (one-time)...")
    agent = Agent("data/catalog.jsonl")
    agent.reset(SESSION, {
        "purchase_frequency": "3-4 prior purchases",
        "average_prior_rating": 4.5,
        "rating_style": "usually positive",
        "preference_tags": ["comfort", "quality"],
        "summary": "Prior purchases emphasize comfort and quality.",
    })
    for turn, message in enumerate(SCRIPT, start=1):
        print(f"\n{'=' * 78}\nTURN {turn} — customer: {message}")
        response = agent.respond(SESSION, message, turn, 10)
        show_state(agent)
        if response["ask_attribute"]:
            print(f"  agent asks ({response['ask_attribute']}): {response['message']}")
        else:
            print(f"  agent: {response['message']}")
        print("  top recommendations:")
        for rank, rec in enumerate(response["recommendations"][:5], start=1):
            product = agent.catalog.get_product(rec["parent_asin"])
            price = product.get("price")
            price_str = f"${price}" if price not in (None, "") else "n/a"
            print(f"   {rank}. [{price_str:>8}] {str(product.get('title'))[:70]}")
    print(f"\n{'=' * 78}\nDeterminism note: rerun this command — the transcript is identical.")


if __name__ == "__main__":
    main()
