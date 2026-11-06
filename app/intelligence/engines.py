"""מנועי AI מודולריים — מחליפים ביניהם בלי לשנות את שאר המערכת.

- anthropic : Claude (בתשלום, דורש ANTHROPIC_API_KEY). המנוע המומלץ לאיכות.
- gemini    : Google Gemini API — מסלול חינמי (מגבלת קצב). דורש GEMINI_API_KEY (חינם ב-aistudio.google.com).
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
PREFERRED = os.environ.get("P1_AI_ENGINE", "auto")  # auto / anthropic / gemini / ollama / rules
GEMINI_URL = os.environ.get("P1_GEMINI_URL", "https://generativelanguage.googleapis.com/v1beta")
GEMINI_MODEL = os.environ.get("P1_GEMINI_MODEL", "")  # ריק = בחירה אוטומטית של מודל Flash זמין
# בסביבת הענן של Claude Code המפתח מוזרק ע"י ה-proxy (P1_GEMINI_PROXY_KEY=1) — האפליקציה עצמה לא רואה אותו
GEMINI_PROXY_KEY = os.environ.get("P1_GEMINI_PROXY_KEY") == "1"


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


def _gemini_key() -> str | None:
    k = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    return k or ("proxy-injected" if GEMINI_PROXY_KEY else None)


_gemini_cache: dict = {"at": 0.0, "ok": False, "msg": "", "model": None, "candidates": []}


def gemini_status(timeout: float = 6, force: bool = False) -> tuple[bool, str, str | None]:
    """בדיקה אמיתית מול ה-API (רשימת מודלים) — לא רק "יש מפתח". נשמר במטמון 5 דקות."""
    import time as _t
    key = _gemini_key()
    if not key:
        return False, "חסר GEMINI_API_KEY (חינם: aistudio.google.com → Get API key)", None
    if not force and _t.time() - _gemini_cache["at"] < 300:
        return _gemini_cache["ok"], _gemini_cache["msg"], _gemini_cache["model"]
    try:
        r = httpx.get(f"{GEMINI_URL}/models", headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=timeout)
        if r.status_code != 200:
            res = (False, f"Gemini החזיר {r.status_code} — בדקו את המפתח", None)
        else:
            names = [m["name"].split("/")[-1] for m in r.json().get("models", [])
                     if "generateContent" in m.get("supportedGenerationMethods", [])]
            cands = gemini_candidates(names)
            if GEMINI_MODEL in names:
                cands = [GEMINI_MODEL] + [c for c in cands if c != GEMINI_MODEL]
            model = cands[0] if cands else None
            _gemini_cache["candidates"] = cands
            res = (bool(model), f"Gemini · {model} (+{len(cands) - 1} גיבוי)" if model else "לא נמצא מודל Gemini זמין", model)
    except httpx.HTTPError as e:
        res = (False, f"אין חיבור ל-Gemini: {type(e).__name__}", None)
    _gemini_cache.update(at=_t.time(), ok=res[0], msg=res[1], model=res[2])
    return res


def gemini_candidates(names: list[str]) -> list[str]:
    """מודלים מתאימים לפי סדר עדיפות: Flash יציב בגרסה הגבוהה → Flash-Lite. בלי preview/image/tts/omni/כלים מיוחדים."""
    import re as _re
    bad = r"image|tts|live|audio|thinking|exp|preview|embedding|omni|robotics|computer|antigravity|research|nano|transcribe|customtools|latest"

    def ver(n: str) -> tuple:
        m = _re.search(r"gemini-(\d+)(?:\.(\d+))?", n)
        return (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)
    flash = [n for n in names if "flash" in n and not _re.search(bad, n)]
    full = sorted([n for n in flash if "lite" not in n], key=ver, reverse=True)
    lite = sorted([n for n in flash if "lite" in n], key=ver, reverse=True)
    return full + lite


def pick_gemini_model(names: list[str]) -> str | None:
    c = gemini_candidates(names)
    return c[0] if c else None


class GeminiEngine:
    """Google Gemini דרך REST. פלט JSON מובנה (responseJsonSchema). עלות 0 במסלול החינמי."""
    id = "gemini"

    def __init__(self, model: str | None = None, transport: httpx.AsyncBaseTransport | None = None, key: str | None = None,
                 fallbacks: list[str] | None = None):
        if model is None:
            gemini_status()
        cands = [model] if model else list(_gemini_cache.get("candidates") or [])
        self.models = (cands + [m for m in (fallbacks or []) if m not in cands]) or ["gemini-flash-latest"]
        self.model = self.models[0]
        self.transport, self.key = transport, key or _gemini_key() or ""

    async def structured(self, *, system: str, content: list[dict], schema: dict, effort: str = "medium",
                         max_tokens: int = 16000) -> tuple[dict, Usage]:
        import asyncio as _a
        parts: list[dict] = []
        for b in content:
            if b.get("type") == "text":
                parts.append({"text": b["text"]})
            elif b.get("type") == "image":
                parts.append({"inline_data": {"mime_type": b["source"].get("media_type", "image/jpeg"), "data": b["source"]["data"]}})
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"responseMimeType": "application/json", "responseJsonSchema": schema,
                                     "temperature": 0.3, "maxOutputTokens": min(max_tokens, 32000)}}
        last = ""
        queue = list(self.models)
        tried = 0
        async with httpx.AsyncClient(timeout=120, transport=self.transport) as c:
            while queue and tried < 8:
                model = queue[0]
                tried += 1
                try:
                    r = await c.post(f"{GEMINI_URL}/models/{model}:generateContent", json=body, headers={"x-goog-api-key": self.key})
                except httpx.HTTPError as e:
                    last = f"{model}: {type(e).__name__}"
                    queue.pop(0)  # מודל שלא עונה בזמן — עוברים למודל הבא
                    continue
                if r.status_code in (503, 404) or (r.status_code == 429 and len(queue) > 1):  # עמוס / לא זמין / מכסה של מודל → המודל הבא
                    last = f"{model} {r.status_code}"
                    queue.pop(0)
                    continue
                if r.status_code == 429 or r.status_code >= 500:
                    last = f"{model} {r.status_code}"
                    await _a.sleep(min(30, 4 * tried))
                    continue
                if r.status_code == 400 and "responseJsonSchema" in r.text:  # גרסת API ישנה — סכימה בתוך ההנחיה
                    body["generationConfig"].pop("responseJsonSchema", None)
                    body["systemInstruction"]["parts"][0]["text"] = system + "\nהחזר JSON בלבד לפי הסכימה: " + json.dumps(schema, ensure_ascii=False)
                    continue
                if r.status_code != 200:
                    raise IntelligenceError(f"Gemini החזיר {r.status_code}: {r.text[:200]}")
                data = r.json()
                try:
                    cand = data["candidates"][0]
                    text = "".join(p.get("text", "") for p in cand["content"]["parts"] if not p.get("thought"))
                    out = json.loads(text)
                except (KeyError, IndexError, json.JSONDecodeError):
                    reason = (data.get("candidates") or [{}])[0].get("finishReason") or data.get("promptFeedback", {}).get("blockReason")
                    raise IntelligenceError(f"Gemini לא החזיר JSON תקין ({reason or 'ללא סיבה'})", retryable=reason == "MAX_TOKENS")
                um = data.get("usageMetadata", {})
                self.model = model
                return out, Usage(model=f"gemini:{model}", input_tokens=um.get("promptTokenCount", 0),
                                  output_tokens=um.get("candidatesTokenCount", 0) + um.get("thoughtsTokenCount", 0))
        raise IntelligenceError(f"Gemini עמוס או שהגעתם למגבלת המסלול החינמי ({last}). נסו שוב בעוד דקה.", retryable=True)


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
    g_ok, g_msg, g_model = gemini_status()
    engines = [
        {"id": "anthropic", "name": f"Claude ({config.MODEL})", "available": a_ok, "cost": "paid",
         "detail": "מחובר" if a_ok else "חסר ANTHROPIC_API_KEY"},
        {"id": "gemini", "name": f"Google Gemini ({g_model or 'Flash'})", "available": g_ok, "cost": "free", "detail": g_msg},
        {"id": "ollama", "name": f"Ollama ({OLLAMA_MODEL})", "available": o_ok, "cost": "free", "detail": o_msg},
        {"id": "rules", "name": "P1 Rules Engine", "available": True, "cost": "free",
         "detail": "כללים + תבניות CRO — בלי מודל שפה"},
    ]
    order = {"anthropic": ["anthropic"], "gemini": ["gemini"], "ollama": ["ollama"], "rules": []}.get(PREFERRED, ["anthropic", "gemini", "ollama"])
    active = next((e["id"] for e in engines if e["id"] in order and e["available"]), "rules")
    return {"active": active, "preferred": PREFERRED, "engines": engines}


def active_engine(override: Any = None) -> Engine | None:
    """המנוע שישמש לניתוח מבוסס מודל, או None אם רק מנוע הכללים זמין."""
    if override is not None:
        return override if hasattr(override, "structured") else AnthropicEngine(override)
    act = status()["active"]
    if act == "anthropic":
        return AnthropicEngine()
    if act == "gemini":
        return GeminiEngine()
    if act == "ollama":
        return OllamaEngine()
    return None
