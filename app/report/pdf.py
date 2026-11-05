"""דוח PDF מקצועי — HTML שמרונדר ע"י Chromium (אותו דפדפן של הבדיקות)."""
from __future__ import annotations

import base64
from html import escape as e
from pathlib import Path

from playwright.async_api import async_playwright

from .. import config
from ..audit.browser import launch

FONTS = config.ROOT / "app" / "static" / "fonts"
SEV = {"critical": "קריטי", "high": "חמור", "medium": "בינוני", "low": "נמוך"}
IMP = {"high": "גבוהה", "medium": "בינונית", "low": "נמוכה", None: "—"}
STEP = {"passed": "✓ עבר", "failed": "✕ נכשל", "warning": "! אזהרה", "skipped": "– לא נבדק"}
VERDICT = {"likely_buy": "כנראה יקנה", "hesitant": "מתלבט", "likely_leave": "כנראה יעזוב"}
LABELS = {"home": "עמוד הבית", "product": "עמוד מוצר", "after-add-to-cart": "אחרי הוספה לסל", "cart": "עגלה",
          "checkout": "קופה", "search": "חיפוש"}


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def _grade(score):
    if score is None:
        return "לא נבדק", "#8b8d98"
    if score >= 80:
        return "מצב טוב", "#0ca30c"
    if score >= 50:
        return "דורש שיפור", "#c98500"
    return "דורש טיפול דחוף", "#d03b3b"


def render_html(r: dict, shot_paths: dict[str, str]) -> str:
    cats = r["methodology"]["categories"]
    weights = r["methodology"]["weights"]
    grade, color = _grade(r["score"])
    ai = r["ai"]
    an = ai.get("analysis")
    measured = [f for f in r["findings"] if f["source"] == "measured"]
    ai_f = [f for f in r["findings"] if f["source"] == "ai"]
    host = r.get("site_name") or r.get("site_url")

    def bar(v):
        if v is None:
            return '<span class="muted">לא נבדק</span>'
        return f'<div class="bar"><div style="width:{v}%"></div></div><b>{v}</b>'

    def finding(f):
        return f"""<div class="finding sev-{f['severity']}"><div class="fh"><span class="sev">{SEV[f['severity']]}</span>
          <b>{e(f['title'])}</b><span class="tag">{e(cats.get(f['category'], f['category']))}</span></div>
          <p>{e(f['detail'])}</p><p><b>למה זה חשוב:</b> {e(f['why_it_matters'])}</p>
          <p><b>השפעה משוערת:</b> {IMP.get(f['impact'])} · <b>תיקון:</b> {e(' → '.join(f['fix_steps']))}</p></div>"""

    plan = (an or {}).get("action_plan") or r["action_plan_rules"]
    plan_src = "השערת AI (Claude) המבוססת על הראיות" if an else "דירוג אוטומטי לפי חומרה והשפעה (ללא AI)"
    shots_html = "".join(
        f'<figure><img src="data:image/jpeg;base64,{_b64(Path(p))}"><figcaption>{e(LABELS.get(lbl.split("|")[0], lbl))} · '
        f'{"טלפון" if lbl.endswith("mobile") else "מחשב"}</figcaption></figure>'
        for lbl, p in shot_paths.items())
    comp = r.get("comparison")
    comp_html = ""
    if comp:
        d = comp["score_delta"]
        dash = lambda x: "—" if x is None else x  # noqa: E731
        cat_rows = "".join(
            f"<tr><td>{e(cats[c])}</td><td>{dash(v['before'])}</td><td>{dash(v['after'])}</td>"
            f"<td>{'' if v['delta'] is None else format(v['delta'], '+d')}</td></tr>"
            for c, v in comp["categories"].items())
        comp_html = f"""<h2>השוואה לבדיקה הקודמת (Before / After)</h2>
        <table><tr><th>חלק</th><th>לפני</th><th>אחרי</th><th>שינוי</th></tr>
        <tr><td><b>ציון כללי</b></td><td>{comp['before']['score']}</td><td>{comp['after']['score']}</td><td>{'' if d is None else f'{d:+d}'}</td></tr>
        {cat_rows}
        </table><p><b>תוקנו:</b> {len(comp['fixed'])} · <b>חדשים:</b> {len(comp['new'])} · <b>נשארו:</b> {len(comp['persisting'])}</p>
        {''.join(f'<p class="ok">✓ תוקן: {e(x["title"])}</p>' for x in comp['fixed'][:10])}
        {''.join(f'<p class="bad">✕ חדש: {e(x["title"])}</p>' for x in comp['new'][:10])}"""

    personas_html = ""
    if ai["personas"]:
        for p in ai["personas"]:
            if not p["result"]:
                continue
            res = p["result"]
            personas_html += f"""<div class="persona"><b>{e(p['name'])}</b> — {VERDICT[res['verdict']]}
              <p>{e(res['understood'])}</p>
              {''.join(f'<p class="bad">✕ {e(x)}</p>' for x in (res['confusing'] + res['distrust'] + res['purchase_issues'])[:5])}
              {''.join(f'<p class="ok">→ {e(x)}</p>' for x in res['improvements'][:3])}</div>"""
    else:
        for p in r["personas"]:
            personas_html += f"""<div class="persona"><b>{e(p['persona'])}</b> — {VERDICT[p['verdict']]}
              {''.join(f'<p class="bad">✕ {e(x)}</p>' for x in p['blockers'][:4])}</div>"""

    return f"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><style>
@font-face {{ font-family: Heebo; src: url(data:font/woff2;base64,{_b64(FONTS / 'heebo-hebrew-wght-normal.woff2')}) format('woff2'); font-weight: 100 900; unicode-range: U+0590-05FF, U+200C-2010, U+20AA, U+25CC, U+FB1D-FB4F; }}
@font-face {{ font-family: Heebo; src: url(data:font/woff2;base64,{_b64(FONTS / 'heebo-latin-wght-normal.woff2')}) format('woff2'); font-weight: 100 900; }}
@page {{ size: A4; margin: 16mm 14mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: Heebo, Arial, sans-serif; color: #13131c; font-size: 10.5pt; line-height: 1.5; margin: 0; }}
h1 {{ font-size: 26pt; margin: 0; letter-spacing: -.01em; }} h2 {{ font-size: 15pt; margin: 22px 0 10px; padding-bottom: 6px; border-bottom: 2px solid #ececf3; break-after: avoid; }}
.cover {{ background: linear-gradient(135deg, #12112a, #2a2468); color: #fff; border-radius: 16px; padding: 28px; display: flex; justify-content: space-between; align-items: center; }}
.cover .muted {{ color: #c7c6e6; }} .score {{ font-size: 54pt; font-weight: 800; line-height: 1; text-align: center; }}
.muted {{ color: #777a8c; }} .small {{ font-size: 9pt; }}
.brand {{ font-weight: 800; color: #a99ffb; letter-spacing: .02em; }}
table {{ width: 100%; border-collapse: collapse; margin: 6px 0; }} th, td {{ text-align: right; padding: 6px 8px; border-bottom: 1px solid #ececf3; vertical-align: top; }}
th {{ color: #777a8c; font-weight: 600; font-size: 9pt; }}
.bar {{ display: inline-block; width: 140px; height: 7px; background: #f0f0f6; border-radius: 4px; margin-left: 8px; vertical-align: middle; }}
.bar div {{ height: 100%; background: #2a78d6; border-radius: 4px; }}
.finding {{ border: 1px solid #ececf3; border-right: 4px solid #8b8d98; border-radius: 8px; padding: 8px 12px; margin: 8px 0; break-inside: avoid; }}
.finding p {{ margin: 3px 0; }} .sev-critical {{ border-right-color: #d03b3b; }} .sev-high {{ border-right-color: #ec835a; }} .sev-medium {{ border-right-color: #fab219; }}
.fh {{ display: flex; gap: 8px; align-items: baseline; }} .sev {{ font-size: 8.5pt; font-weight: 700; color: #555; }}
.tag {{ margin-right: auto; font-size: 8.5pt; color: #777a8c; }}
.src {{ display: inline-block; font-size: 8.5pt; font-weight: 700; padding: 2px 8px; border-radius: 99px; }}
.src-m {{ background: #e3f5ef; color: #0f8a6c; }} .src-ai {{ background: #fdf3e2; color: #a8670a; }} .src-sim {{ background: #f0ebff; color: #6d4ce0; }}
.box {{ background: #f6f6fa; border-radius: 10px; padding: 12px 14px; margin: 8px 0; break-inside: avoid; }}
.ok {{ color: #0a7a0a; margin: 2px 0; }} .bad {{ color: #b42f2f; margin: 2px 0; }}
.persona {{ border: 1px solid #ececf3; border-radius: 8px; padding: 8px 12px; margin: 6px 0; break-inside: avoid; }} .persona p {{ margin: 2px 0; }}
.shots {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }} figure {{ margin: 0; break-inside: avoid; }}
figure img {{ width: 100%; max-height: 260px; object-fit: cover; object-position: top; border: 1px solid #ececf3; border-radius: 6px; }}
figcaption {{ font-size: 8.5pt; color: #777a8c; }} .page-break {{ break-before: page; }}
</style></head><body>
<div class="cover"><div><div class="brand">P1 AI · דוח בדיקת אתר</div><h1>{e(host)}</h1>
  <div class="muted">{e(r['start_url'])}</div><div class="muted small">נבדק: {e((r.get('finished_at') or '')[:16].replace('T', ' '))} UTC · מזהה {r['id'][:8]}</div></div>
  <div><div class="score">{r['score'] if r['score'] is not None else '—'}</div><div style="text-align:center;color:{color};font-weight:700;background:#fff;border-radius:99px;padding:2px 10px;margin-top:6px">{grade}</div></div></div>

<h2>ציונים לפי חלקי הדוח</h2>
<table><tr><th>חלק</th><th>ציון</th><th>משקל</th></tr>
{''.join(f"<tr><td>{e(cats[c])}</td><td>{bar((r['category_scores'] or {}).get(c))}</td><td>{weights[c]}%</td></tr>" for c in cats)}</table>
<div class="box small"><b>איך חושב הציון (גרסה {r['methodology']['version']}):</b> כל חלק מתחיל ב-100 ומופחת לפי חומרת כל ממצא שנבדק בפועל
(קריטי {r['methodology']['penalty']['critical']}, חמור {r['methodology']['penalty']['high']}, בינוני {r['methodology']['penalty']['medium']}, נמוך {r['methodology']['penalty']['low']}).
הציון הכללי הוא ממוצע משוקלל של החלקים שנבדקו בלבד; חלק שלא נבדק לא מקבל ציון. ממצא קריטי מגביל את הציון הכללי ל-{r['methodology']['critical_cap']}.
סימולציות והשערות AI <b>אינן</b> משפיעות על הציון.</div>
<p class="small"><span class="src src-m">נבדק בפועל</span> ממצא שנמדד בדפדפן אמיתי · <span class="src src-sim">סימולציה</span> לקוח מדומה, לא לקוח אמיתי ·
<span class="src src-ai">השערת AI</span> הערכה של Claude על בסיס הראיות — יש לאמת</p>

<h2>סיכום מנהלים <span class="src src-ai">השערת AI</span></h2>
{f'<div class="box">{e(an["executive_summary"])}</div><div class="box"><b>מוכנות להמרה:</b> {e(an["conversion_readiness"])}</div>' if an else
 f'<div class="box muted">ניתוח AI לא בוצע ({e({"not_configured": "Claude לא מחובר — חסר ANTHROPIC_API_KEY", "quota_exceeded": "נוצלה מכסת ה-AI החודשית", "failed": "הניתוח נכשל"}.get(ai["status"] or "", ai.get("analysis_error") or "לא זמין"))}). כל שאר הדוח מבוסס על בדיקות אמיתיות.</div>'}

<h2>תוכנית פעולה <span class="small muted">({plan_src})</span></h2>
<table><tr><th>#</th><th>מה לעשות</th><th>למה עכשיו</th></tr>
{''.join(f"<tr><td>{p['priority']}</td><td><b>{e(p['title'])}</b></td><td>{e(p['why_first'])}</td></tr>" for p in plan)}</table>

{comp_html}

<h2 class="page-break">ממצאים שנבדקו בפועל ({len(measured)}) <span class="src src-m">נבדק בפועל</span></h2>
{''.join(finding(f) for f in measured) or '<p class="muted">לא נמצאו בעיות בבדיקות האוטומטיות.</p>'}

{f'<h2>תובנות AI ({len(ai_f)}) <span class="src src-ai">השערת AI</span></h2>' + ''.join(finding(f) for f in ai_f) if ai_f else ''}
{('<h2>הצעות ניסוח <span class="src src-ai">השערת AI</span></h2>' + ''.join(f'<div class="box"><b>{e(c["area"])}</b><br>{("לפני: " + e(c["current_text"]) + "<br>") if c["current_text"] else ""}<b>מוצע:</b> {e(c["suggested_text"])}<br><span class="muted small">{e(c["rationale"])}</span></div>' for c in an["copy_suggestions"])) if an and an.get("copy_suggestions") else ''}

<h2>לקוחות מדומים <span class="src src-sim">סימולציה</span>{' <span class="src src-ai">סוכני AI</span>' if ai['personas'] else ''}</h2>
<p class="small muted">אלה לקוחות מדומים ולא נתוני התנהגות של לקוחות אמיתיים.</p>
{personas_html}

<h2 class="page-break">מסע הרכישה כפי שהדפדפן ביצע אותו</h2>
<table><tr><th>שלב</th><th>תוצאה</th><th>פירוט</th></tr>
{''.join(f"<tr><td>{e(s['title'])}</td><td>{STEP[s['status']]}</td><td>{e(s['detail'] or '')}</td></tr>" for s in r['steps'])}</table>
<p class="small muted">הבדיקה לא ממלאת פרטים אישיים ולא מבצעת הזמנה — היא עוצרת בכניסה לקופה.</p>
<h2>ראיות — צילומי מסך</h2><div class="shots">{shots_html}</div>
<p class="small muted" style="margin-top:20px">הופק ע"י P1 AI. {f"ניתוח AI: {e(ai['model'] or '')}." if an else ''}</p>
</body></html>"""


async def render_pdf(r: dict, shots_with_paths: list[dict]) -> bytes:
    wanted = ["home|desktop", "product|desktop", "cart|desktop", "checkout|desktop", "home|mobile", "product|mobile"]
    by = {f"{s['label']}|{s['device']}": s["path"] for s in shots_with_paths if Path(s["path"]).exists()}
    shot_paths = {k: by[k] for k in wanted if k in by}
    html = render_html(r, shot_paths)
    async with async_playwright() as pw:
        browser = await launch(pw)
        try:
            page = await browser.new_page()
            await page.route("**/*", lambda route: route.abort() if not route.request.url.startswith("data:") else route.continue_())
            await page.set_content(html, wait_until="load")
            return await page.pdf(format="A4", print_background=True, margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"})
        finally:
            await browser.close()
