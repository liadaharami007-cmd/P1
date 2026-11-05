"""מנועי AI מודולריים — מחליפים ביניהם בלי לשנות את שאר המערכת.

- anthropic : Claude (בתשלום, דורש ANTHROPIC_API_KEY). המנוע המומלץ לאיכות.
- ollama    : מודל פתוח שרץ מקומית בחינם (Ollama). דורש התקנת Ollama + מודל על השרת.
- rules     : ניתוח דטרמיניסטי (כללים + תבניות) — תמיד זמין, בחינם, בלי מודל שפה.

המערכת מציגה איזה מנוע באמת פעיל. אין תשובות מדומות: אם אין מודל — רק מנוע הכללים פועל.
"""
from __future__ import annotations

import json
import os
from typing import Any, Protocol

import httpx

from .. import config
from .client import IntelligenceError, Usage, get_client, structured_call

OLLAMA_URL = os.environ.get("P1_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("P1_OLLAMA_MODEL", "qwen2.5:7b-instruct")
OLLAMA_VISION = os.environ.get("P1_OLLAMA_VISION", "0") == "1"
PREFERRED = os.environ.get("P1_AI_ENGINE", "auto")  # auto / anthropic / ollama / rules


class Engine(Protocol):
    id: str
    model: str

    async def structured(self, *, system: str, content: list[dict], schema: dict, effort: str = "medium",
                         max_tokens: int = 16000) -> tuple[dict, Usage]: ...


class AnthropicEngine:
    id = "anthropic"

    def __init__(self, client: Any = None):
        self.client = client or get_client()
        self.model = config.MODEL

    async def structured(self, **kw) -> tuple[dict, Usage]:
        return await structured_call(self.client, **kw)


class OllamaEngine:
    id = "ollama"

    def __init__(self, url: str = OLLAMA_URL, model: str = OLLAMA_MODEL, transport: httpx.AsyncBaseTransport | None = None):
        self.url, self.model, self.transport = url.rstrip("/"), model, transport

    async def structured(self, *, system: str, content: list[dict], schema: dict, effort: str = "medium",
                         max_tokens: int = 16000) -> tuple[dict, Usage]:
        text = "\n".join(b["text"] for b in content if b.get("type") == "text")
        images = [b["source"]["data"] for b in content if b.get("type") == "image"] if OLLAMA_VISION else []
        msg: dict = {"role": "user", "content": text}
        if images:
            msg["images"] = images
        body = {"model": self.model, "stream": False, "format": schema, "options": {"temperature": 0.2, "num_predict": max_tokens},
                "messages": [{"role": "system", "content": system}, msg]}
        try:
            async with httpx.AsyncClient(timeout=600, transport=self.transport, trust_env=False) as c:
                r = await c.post(f"{self.url}/api/chat", json=body)
        except httpx.HTTPError as e:
            raise IntelligenceError(f"אין חיבור ל-Ollama ({self.url}): {type(e).__name__}", retryable=True)
        if r.status_code != 200:
            raise IntelligenceError(f"Ollama החזיר {r.status_code}: {r.text[:150]}")
        data = r.json()
        try:
            out = json.loads(data["message"]["content"])
        except (KeyError, json.JSONDecodeError):
            raise IntelligenceError("המודל המקומי החזיר JSON לא תקין")
        return out, Usage(model=f"ollama:{self.model}", input_tokens=data.get("prompt_eval_count", 0),
                          output_tokens=data.get("eval_count", 0))  # עלות 0 — רץ מקומית


def ollama_status(timeout: float = 1.5) -> tuple[bool, str]:
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=timeout, trust_env=False)
        names = [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:  # noqa: BLE001
        return False, f"Ollama לא רץ בכתובת {OLLAMA_URL}"
    if not any(n == OLLAMA_MODEL or n.startswith(OLLAMA_MODEL.split(":")[0]) for n in names):
        return False, f"Ollama רץ אבל המודל {OLLAMA_MODEL} לא מותקן (ollama pull {OLLAMA_MODEL})"
    return True, f"Ollama · {OLLAMA_MODEL}"


def status() -> dict:
    """מצב כל המנועים + איזה מנוע פעיל בפועל."""
    a_ok = config.anthropic_configured()
    o_ok, o_msg = ollama_status()
    engines = [
        {"id": "anthropic", "name": f"Claude ({config.MODEL})", "available": a_ok, "cost": "paid",
         "detail": "מחובר" if a_ok else "חסר ANTHROPIC_API_KEY"},
        {"id": "ollama", "name": f"Ollama ({OLLAMA_MODEL})", "available": o_ok, "cost": "free", "detail": o_msg},
        {"id": "rules", "name": "P1 Rules Engine", "available": True, "cost": "free",
         "detail": "כללים + תבניות CRO — בלי מודל שפה"},
    ]
    order = {"anthropic": ["anthropic"], "ollama": ["ollama"], "rules": []}.get(PREFERRED, ["anthropic", "ollama"])
    active = next((e["id"] for e in engines if e["id"] in order and e["available"]), "rules")
    return {"active": active, "preferred": PREFERRED, "engines": engines}


def active_engine(override: Any = None) -> Engine | None:
    """המנוע שישמש לניתוח מבוסס מודל, או None אם רק מנוע הכללים זמין."""
    if override is not None:
        return override if hasattr(override, "structured") else AnthropicEngine(override)
    act = status()["active"]
    if act == "anthropic":
        return AnthropicEngine()
    if act == "ollama":
        return OllamaEngine()
    return None
