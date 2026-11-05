"""חיבור מאובטח ל-Claude בצד השרת בלבד.

- המפתח נקרא ממשתני סביבה / .env ולעולם לא נשלח לדפדפן.
- base_url מוגדר במפורש (לא יורש הגדרות proxy של סביבת הפיתוח).
- כל קריאה נרשמת עם צריכת טוקנים ועלות משוערת (לפי מחירון ציבורי).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import anthropic

from .. import config

BASE_URL = os.environ.get("P1_ANTHROPIC_BASE_URL", "https://api.anthropic.com")
BETAS = ["server-side-fallback-2026-07-01"]

# מחיר לכל מיליון טוקנים, דולר (מחירון ציבורי של Anthropic)
PRICING = {
    "claude-opus-5-5": {"in": 4.00, "out": 20.00, "cache_read": 0.20, "cache_write": 5.00},
    "claude-sonnet-5-5": {"in": 2.00, "out": 10.00, "cache_read": 0.20, "cache_write": 2.50},
    "claude-haiku-5-5": {"in": 0.10, "out": 0.50, "cache_read": 0.01, "cache_write": 0.125},
}


class IntelligenceError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.retryable = retryable


@dataclass
class Usage:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0

    @property
    def cost_usd(self) -> float:
        if self.model.startswith("ollama:"):
            return 0.0  # מודל מקומי — בלי עלות API
        p = PRICING.get(self.model, PRICING["claude-opus-5-5"])
        return round((self.input_tokens * p["in"] + self.output_tokens * p["out"]
                      + self.cache_read * p["cache_read"] + self.cache_write * p["cache_write"]) / 1_000_000, 6)


def configured() -> bool:
    return config.anthropic_configured()


_client: Any = None


def get_client() -> Any:
    global _client
    if _client is None:
        if not configured():
            raise IntelligenceError("חסר ANTHROPIC_API_KEY")
        _client = anthropic.AsyncAnthropic(base_url=BASE_URL, max_retries=2, timeout=300)
    return _client


def usage_of(response: Any, model: str) -> Usage:
    u = getattr(response, "usage", None)
    return Usage(
        model=getattr(response, "model", None) or model,
        input_tokens=getattr(u, "input_tokens", 0) or 0,
        output_tokens=getattr(u, "output_tokens", 0) or 0,
        cache_read=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_write=getattr(u, "cache_creation_input_tokens", 0) or 0,
    )


async def structured_call(client: Any, *, system: str, content: list[dict], schema: dict,
                          effort: str = "medium", max_tokens: int = 16000) -> tuple[dict, Usage]:
    """קריאה ל-Claude שמחזירה JSON תקף לפי סכמה. זורק IntelligenceError עם הודעה בעברית."""
    import json
    try:
        resp = await client.beta.messages.create(
            model=config.MODEL, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": content}],
            thinking={"type": "adaptive"},
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            betas=BETAS, fallbacks="default",
        )
    except anthropic.AuthenticationError:
        raise IntelligenceError("מפתח ה-API של Anthropic לא תקין")
    except anthropic.PermissionDeniedError:
        raise IntelligenceError("למפתח ה-API אין הרשאה למודל")
    except anthropic.RateLimitError:
        raise IntelligenceError("חריגה ממגבלת הבקשות של Anthropic — נסו שוב בעוד דקה", retryable=True)
    except anthropic.BadRequestError as e:
        raise IntelligenceError(f"בקשה לא תקינה ל-Claude: {e.message[:200]}")
    except anthropic.APIStatusError as e:
        raise IntelligenceError(f"שגיאה מצד Anthropic ({e.status_code})", retryable=True)
    except anthropic.APIConnectionError:
        raise IntelligenceError("אין חיבור לשרתי Anthropic", retryable=True)
    usage = usage_of(resp, config.MODEL)
    if resp.stop_reason == "refusal":
        raise IntelligenceError("Claude סירב לנתח את התוכן הזה")
    if resp.stop_reason == "max_tokens":
        raise IntelligenceError("התשובה של Claude נקטעה (ארוכה מדי)")
    text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), None)
    if not text:
        raise IntelligenceError("Claude לא החזיר תוכן")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise IntelligenceError("Claude החזיר JSON לא תקין")
    return data, usage
