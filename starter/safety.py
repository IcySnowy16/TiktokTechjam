"""Schema-safety choke point. Every Agent.respond() return path funnels through here."""

from __future__ import annotations

from .vocab import ALLOWED_ATTRIBUTES

_MAX_RECOMMENDATIONS = 10


def build_safe_response(
    message: object,
    ask_attribute: object,
    recommendations: object,
    usage: object,
    catalog_ids: frozenset[str] | set[str],
) -> dict:
    """Clamp arbitrary inputs into a turn_response the contract always accepts."""
    if isinstance(message, str):
        msg = message
    elif message is None:
        msg = ""
    else:
        msg = str(message)

    attr = ask_attribute if isinstance(ask_attribute, str) and ask_attribute in ALLOWED_ATTRIBUTES else None

    recs: list[dict] = []
    seen: set[str] = set()
    if isinstance(recommendations, list):
        for item in recommendations:
            value = item.get("parent_asin") if isinstance(item, dict) else item
            asin = str(value).strip() if value is not None else ""
            if asin and asin in catalog_ids and asin not in seen:
                seen.add(asin)
                recs.append({"parent_asin": asin})
            if len(recs) >= _MAX_RECOMMENDATIONS:
                break

    u = usage if isinstance(usage, dict) else {}
    prompt_tokens = u.get("prompt_tokens", 0)
    completion_tokens = u.get("completion_tokens", 0)
    safe_usage = {
        "prompt_tokens": prompt_tokens if isinstance(prompt_tokens, int) and prompt_tokens >= 0 else 0,
        "completion_tokens": completion_tokens if isinstance(completion_tokens, int) and completion_tokens >= 0 else 0,
    }

    return {
        "message": msg,
        "ask_attribute": attr,
        "recommendations": recs,
        "usage": safe_usage,
    }
