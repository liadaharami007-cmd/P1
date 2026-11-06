"""בונה דפי נחיתה: Gemini כותב מפרט (sections) → P1 מרנדר HTML בטוח (בלי סקריפטים, הכול escaped) → עריכה בשיחה → גרסאות → ייצוא.

- אין המלצות/ביקורות מומצאות: אין סוג section כזה בכלל. מחירים רק מהפרופיל, אחרת [להשלמה].
- פרסום = דף ציבורי בשרת של P1 (/p/<id>/) — רק אחרי אישור. טופס בדף מפורסם יוצר ליד אמיתי ב-CRM.
"""
from __future__ import annotations

import html
import json
import re
import uuid

from ..db import Database
from . import store, studio

SECTION_TYPES = ["hero", "benefits", "features", "how", "about", "faq", "pricing", "form", "cta"]
S = {"type": "string"}
ITEM = {"type": "object", "additionalProperties": False, "properties": {"title": S, "text": S}, "required": ["title", "text"]}
SECTION = {"type": "object", "additionalProperties": False, "required": ["type", "heading", "text", "items", "button_text"],
           "properties": {"type": {"type": "string", "enum": SECTION_TYPES}, "heading": S, "text": S,
                          "items": {"type": "array", "items": ITEM}, "button_text": S}}
SPEC_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["title", "description", "primary_color", "sections", "missing_info"],
               "properties": {"title": S, "description": S, "primary_color": S, "sections": {"type": "array", "items": SECTION},
                              "missing_info": {"type": "array", "items": S}}}
SYSTEM = ("אתה מעצב וכותב דפי נחיתה ממירים לעסקים קטנים בישראל. בנה דף אחד ממוקד: hero עם הצעת ערך ברורה, יתרונות, איך זה עובד, "
          "שאלות נפוצות, טופס יצירת קשר (section מסוג form) וקריאה לפעולה. אל תכתוב המלצות או ביקורות של לקוחות. "
          "primary_color = צבע hex שמתאים למותג. טקסטים קצרים וברורים.")


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


async def generate(db: Database, account: dict, user_id: str | None, brief: str, engine=None, extra: dict | None = None) -> dict:
    res = await studio.run_custom(db, account, user_id, "landing_page", SYSTEM, SPEC_SCHEMA, brief or "דף נחיתה לעסק", extra=extra, engine=engine)
    spec = sanitize(res["output"])
    pid = _new_id()
    with db._conn() as c:
        c.execute("INSERT INTO pages (id, account_id, title, spec_json, version, status, created_at, updated_at) VALUES (?,?,?,?,1,'draft',?,?)",
                  (pid, account["id"], spec["title"][:120], json.dumps(spec, ensure_ascii=False), store.now(), store.now()))
        c.execute("INSERT INTO page_versions (page_id, version, spec_json, note, created_at) VALUES (?,?,?,?,?)",
                  (pid, 1, json.dumps(spec, ensure_ascii=False), brief[:300] or "יצירה", store.now()))
    store.log(db, account["id"], "page_created", f"P1 בנה דף נחיתה: {spec['title']}", ref_type="page", ref_id=pid, user_id=user_id)
    return get(db, pid, account["id"])  # type: ignore[return-value]


async def edit(db: Database, account: dict, user_id: str | None, page: dict, instruction: str, engine=None) -> dict:
    sysmsg = SYSTEM + " קיבלת דף קיים (current_spec) והוראת עריכה. החזר את הדף המלא המעודכן — שנה רק מה שהתבקש."
    res = await studio.run_custom(db, account, user_id, "landing_page_edit", sysmsg, SPEC_SCHEMA, instruction,
                                  extra={"current_spec": page["spec"]}, engine=engine)
    spec = sanitize(res["output"])
    v = page["version"] + 1
    with db._conn() as c:
        c.execute("UPDATE pages SET spec_json=?, version=?, title=?, updated_at=? WHERE id=? AND account_id=?",
                  (json.dumps(spec, ensure_ascii=False), v, spec["title"][:120], store.now(), page["id"], account["id"]))
        c.execute("INSERT INTO page_versions (page_id, version, spec_json, note, created_at) VALUES (?,?,?,?,?)",
                  (page["id"], v, json.dumps(spec, ensure_ascii=False), instruction[:300], store.now()))
    return get(db, page["id"], account["id"])  # type: ignore[return-value]


def restore(db: Database, page: dict, version: int) -> dict | None:
    with db._conn() as c:
        r = c.execute("SELECT spec_json FROM page_versions WHERE page_id=? AND version=?", (page["id"], version)).fetchone()
        if not r:
            return None
        v = page["version"] + 1
        c.execute("UPDATE pages SET spec_json=?, version=?, updated_at=? WHERE id=?", (r["spec_json"], v, store.now(), page["id"]))
        c.execute("INSERT INTO page_versions (page_id, version, spec_json, note, created_at) VALUES (?,?,?,?,?)",
                  (page["id"], v, r["spec_json"], f"שחזור לגרסה {version}", store.now()))
    return get(db, page["id"], page["account_id"])


def sanitize(spec: dict) -> dict:
    color = spec.get("primary_color") or "#5b54e8"
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        color = "#5b54e8"
    secs = [s for s in spec.get("sections", []) if s.get("type") in SECTION_TYPES][:12]
    if not any(s["type"] == "form" for s in secs):
        secs.append({"type": "form", "heading": "השאירו פרטים ונחזור אליכם", "text": "", "items": [], "button_text": "שליחה"})
    return {"title": (spec.get("title") or "דף נחיתה")[:120], "description": (spec.get("description") or "")[:300],
            "primary_color": color, "sections": secs, "missing_info": spec.get("missing_info") or []}


def get(db: Database, pid: str, account_id: str | None) -> dict | None:
    q = "SELECT * FROM pages WHERE id=?" + (" AND account_id=?" if account_id else "")
    with db._conn() as c:
        r = c.execute(q, (pid, account_id) if account_id else (pid,)).fetchone()
        if not r:
            return None
        vers = [dict(x) for x in c.execute("SELECT version, note, created_at FROM page_versions WHERE page_id=? ORDER BY version DESC", (pid,))]
    d = dict(r)
    d["spec"] = json.loads(d.pop("spec_json"))
    d["versions"] = vers
    return d


def list_pages(db: Database, account_id: str) -> list[dict]:
    with db._conn() as c:
        return [dict(r) for r in c.execute("SELECT id, title, version, status, created_at, updated_at FROM pages WHERE account_id=? ORDER BY updated_at DESC", (account_id,))]


def set_status(db: Database, pid: str, account_id: str, status: str) -> None:
    with db._conn() as c:
        c.execute("UPDATE pages SET status=?, updated_at=? WHERE id=? AND account_id=?", (status, store.now(), pid, account_id))


# ---------------------------------------------------------------- רינדור בטוח
def render(spec: dict, page_id: str, mode: str = "preview") -> str:
    e = html.escape
    c = spec["primary_color"]
    out = []
    for s in spec["sections"]:
        t = s["type"]
        items = "".join(f"<div class='item'><h3>{e(i['title'])}</h3><p>{e(i['text'])}</p></div>" for i in s.get("items", []))
        btn = f"<a class='btn' href='#form'>{e(s['button_text'])}</a>" if s.get("button_text") and t in ("hero", "cta", "pricing") else ""
        if t == "hero":
            out.append(f"<header class='hero'><h1>{e(s['heading'])}</h1><p class='lead'>{e(s['text'])}</p>{btn}</header>")
        elif t == "faq":
            qa = "".join(f"<details><summary>{e(i['title'])}</summary><p>{e(i['text'])}</p></details>" for i in s.get("items", []))
            out.append(f"<section><h2>{e(s['heading'])}</h2>{qa}</section>")
        elif t == "form":
            action = f"/p/{page_id}/lead" if mode == "public" else ""
            note = "" if mode == "public" else "<p class='note'>תצוגה מקדימה — הטופס יתחיל לקלוט פניות אחרי פרסום (באישור).</p>"
            out.append(f"""<section id='form' class='form'><h2>{e(s['heading'])}</h2><p>{e(s['text'])}</p>{note}
<form method='post' action='{action}'><input name='name' placeholder='שם' required autocomplete='name'>
<input name='phone' type='tel' placeholder='טלפון' required autocomplete='tel'><input name='email' type='email' placeholder='אימייל (לא חובה)' autocomplete='email'>
<textarea name='message' placeholder='הודעה (לא חובה)'></textarea><input name='website' class='hp' tabindex='-1' autocomplete='off' aria-hidden='true'>
<button type='submit' {'disabled' if mode != 'public' else ''}>{e(s.get('button_text') or 'שליחה')}</button></form></section>""")
        else:
            out.append(f"<section class='{t}'><h2>{e(s['heading'])}</h2><p>{e(s['text'])}</p><div class='grid'>{items}</div>{btn}</section>")
    return f"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(spec['title'])}</title><meta name="description" content="{e(spec['description'])}">
<style>:root{{--c:{c}}}*{{box-sizing:border-box}}body{{margin:0;font:17px/1.65 system-ui,-apple-system,"Segoe UI",Arial,sans-serif;color:#16161d;background:#fff}}
header.hero{{padding:72px 20px 56px;text-align:center;background:linear-gradient(160deg,color-mix(in srgb,var(--c) 14%,#fff),#fff)}}
h1{{font-size:clamp(30px,6vw,48px);line-height:1.15;margin:0 auto 14px;max-width:760px;letter-spacing:-.02em}}h2{{font-size:clamp(24px,4vw,32px);margin:0 0 10px}}
.lead{{font-size:19px;color:#4a4b5c;max-width:620px;margin:0 auto 26px}}section{{padding:56px 20px;max-width:980px;margin:0 auto}}
section>p{{color:#4a4b5c;max-width:680px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px;margin-top:20px}}
.item{{border:1px solid #e7e7ef;border-radius:14px;padding:18px}}.item h3{{margin:0 0 6px;font-size:18px}}.item p{{margin:0;color:#4a4b5c}}
.btn,button{{display:inline-block;background:var(--c);color:#fff;border:0;border-radius:12px;padding:14px 26px;font:600 17px inherit;text-decoration:none;cursor:pointer}}
details{{border-bottom:1px solid #e7e7ef;padding:14px 0}}summary{{font-weight:600;cursor:pointer}}
.form form{{display:grid;gap:10px;max-width:460px}}input,textarea{{font:inherit;padding:12px 14px;border:1px solid #d6d6e2;border-radius:10px}}
.hp{{position:absolute;left:-9999px}}.note{{background:#fff4d9;padding:8px 12px;border-radius:8px;font-size:14px}}
button[disabled]{{opacity:.6;cursor:not-allowed}}footer{{text-align:center;color:#8a8ca0;font-size:13px;padding:30px}}</style></head>
<body>{''.join(out)}<footer>נבנה עם P1 AI</footer></body></html>"""
