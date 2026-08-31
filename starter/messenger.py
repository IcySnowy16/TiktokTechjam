"""Customer-facing message composition. Templates are the default and always-correct path;
an optional LLM may vary phrasing later (M5) but never changes what is asked or ranked."""

from __future__ import annotations

from .dialog_state import SessionState

_QUESTION_TEMPLATES = {
    "category": "What kind of item are you shopping for today?",
    "material": "Do you have a material preference — cotton, leather, something else?",
    "color": "Any color you're leaning toward?",
    "size": "What size or fit works best for you?",
    "style": "Is there a particular style or cut you like?",
    "brand": "Do you have a favorite brand or store?",
    "budget": "Roughly what budget did you have in mind?",
    "feature": "Is there a specific feature that matters most to you?",
    "use_case": "What will you mainly use it for — work, workouts, everyday wear?",
    "other": "Anything else that matters to you — I'll factor it in.",
}


def compose(
    state: SessionState,
    ask_attribute: str | None,
    top_product: dict | None,
    question_override: str | None = None,
) -> str:
    """A friendly message consistent with the structured ask_attribute field.

    Only facts present in the catalog record (title, price) ever appear —
    no invented claims, no promotions.
    """
    parts: list[str] = []
    if top_product:
        title = str(top_product.get("title") or "").strip()
        if title:
            short = title if len(title) <= 70 else title[:67].rstrip() + "..."
            parts.append(f"My current top pick is \"{short}\".")
        budget = state.budget_value()
        price = top_product.get("price")
        try:
            price_value = float(price) if price not in (None, "") else None
        except (TypeError, ValueError):
            price_value = None
        if budget is not None and price_value is not None and price_value <= budget:
            parts.append(f"It comes in under your ${budget:.0f} budget.")

    if ask_attribute:
        parts.append(
            question_override
            or _QUESTION_TEMPLATES.get(ask_attribute, _QUESTION_TEMPLATES["other"])
        )
    elif not parts:
        parts.append("Here are the closest matches I found — let me know what you think.")
    else:
        parts.append("Here are my best matches so far.")
    return " ".join(parts)
