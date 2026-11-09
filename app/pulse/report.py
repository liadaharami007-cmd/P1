"""ClientPulse — דוחות (HTML ממותג להדפסה / PDF ע"י Chromium). רק מנתונים קיימים במערכת."""
from __future__ import annotations

import html

from ..db import Database
from . import engine, service as S
from .engine import fmt_day, money, sgn


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _svg_line(points: list[float | None], w: int = 640, h: int = 150, color: str = "#4E5FE0") -> str:
    vals = [p for p in points if p is not None]
    if len(vals) < 2:
        return "<p class='muted'>אין מספיק נתונים לגרף</p>"
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    n = len(points)
    pts = []
    for i, p in enumerate(points):
        if p is None:
            continue
        x = 8 + i * (w - 16) / max(1, n - 1)
        y = h - 14 - (p - lo) / span * (h - 28)
        pts.append(f"{x:.1f},{y:.1f}")
    return (f"<svg viewBox='0 0 {w} {h}' width='100%' style='direction:ltr'><polyline fill='none' stroke='{color}' stroke-width='2.2' "
            f"points='{' '.join(pts)}'/><text x='8' y='12' font-size='10' fill='#888'>{_e(money(hi))}</text>"
            f"<text x='8' y='{h - 2}' font-size='10' fill='#888'>{_e(money(lo))}</text></svg>")


CSS = """body{font-family:Heebo,Arial,sans-serif;color:#15171B;margin:0;padding:28px;direction:rtl;font-size:13px;line-height:1.6}
h1{font-size:22px;margin:0}h2{font-size:15px;margin:22px 0 8px;border-bottom:1px solid #E6E5E1;padding-bottom:4px}
.top{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:3px solid #4E5FE0;padding-bottom:10px}
.brand{font-weight:700;color:#4E5FE0}.muted{color:#777}.k{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.k div{border:1px solid #E6E5E1;border-radius:10px;padding:8px 10px}.k b{display:block;font-size:18px}
table{width:100%;border-collapse:collapse}td,th{padding:6px 4px;border-bottom:1px solid #eee;text-align:start}
.pill{display:inline-block;padding:1px 8px;border-radius:99px;font-size:11px;font-weight:700}
.red{background:#FBE8E6;color:#D2453B}.yellow{background:#FBF1DC;color:#B87C0A}.green{background:#E5F4ED;color:#1E9C6A}
.demo{background:#FBF1DC;color:#B87C0A;padding:4px 10px;border-radius:8px;font-size:12px;margin-top:8px;display:inline-block}
@media print{body{padding:0}}"""


def client_report_html(db: Database, acc: str, cid: str, days: int = 30, agency: str = "") -> str | None:
    run = S.analysis(db, acc)
    r = run["byId"].get(cid)
    if not r:
        return None
    ref = run["ref"]
    cur = [d for d in r["days"] if ref - d["_i"] < days]
    prev = [d for d in r["days"] if days <= ref - d["_i"] < days * 2]
    sc, sp = engine.stats(cur), engine.stats(prev)

    def ch(a, b, inv=False):
        if a is None or not b:
            return ""
        return f"<span class='muted'>({sgn(a / b - 1)})</span>"
    tasks = S.all_tasks(db, acc, cid)
    resolved = [t for t in tasks if t["status"] == "closed" and t.get("verification") and t["verification"].get("ok")]
    acts = S.rows(db, "SELECT * FROM pulse_events WHERE account_id=? AND client_id=? AND day>? AND type IN ('task','verified','automation') ORDER BY id DESC LIMIT 12",
                  (acc, cid, ref - days))
    plan = [engine.investigate(r, a)["plan"][0]["text"] for a in r["alerts"]] or ["שימור הביצועים הנוכחיים ובחינת הזדמנויות להגדלת תקציב"]
    if r["improved"]:
        plan.append("לבחון הגדלת תקציב הדרגתית כל עוד העלות לליד יציבה")
    roll = S.rolling_cpl(r, days)
    sales_row = ""
    if sc.get("has_sales"):
        sales_row = (f"<div><span class='muted'>מכירות</span><b>{sc['sales']}</b>{ch(sc['sales'], sp.get('sales'))}</div>"
                     f"<div><span class='muted'>הכנסה מדווחת</span><b>{_e(money(sc['revenue']))}</b></div>")
    alerts_html = "".join(f"<tr><td><span class='pill {a['severity']}'>{'דחוף' if a['severity'] == 'red' else 'במעקב'}</span> {_e(a['title'])}</td><td>{_e(a['what'])}</td></tr>"
                          for a in r["alerts"]) or "<tr><td colspan=2>אין חריגות פתוחות</td></tr>"
    res_html = "".join(f"<tr><td>{_e(t['title'])}</td><td>{_e(money((t['before'] or {}).get('cpl')))} ← {_e(money(t['verification']['after'].get('cpl')))}</td></tr>"
                       for t in resolved) or "<tr><td colspan=2 class='muted'>אין עדיין טיפולים שאומתו בנתונים בתקופה</td></tr>"
    acts_html = "".join(f"<li>{fmt_day(e['day'])} · {_e(e['text'])}</li>" for e in acts) or "<li class='muted'>לא תועדו פעולות בתקופה</li>"
    return f"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><title>דוח ביצועים · {_e(r['name'])}</title><style>{CSS}</style></head><body>
<div class="top"><div><div class="brand">{_e(agency or 'ClientPulse')}</div><h1>דוח ביצועים · {_e(r['name'])}</h1>
<div class="muted">{fmt_day(ref - days + 1)}–{fmt_day(ref)} ({days} ימים) · השוואה ל-{days} הימים שלפני</div></div>
<div><span class="pill {r['status']}">{S.SL[r['status']]}</span></div></div>
{"<div class='demo'>דוח על נתוני דמו (מדומים) — להמחשה בלבד</div>" if r['is_demo'] else ""}
<h2>שורה תחתונה</h2><div class="k">
<div><span class='muted'>הוצאה</span><b>{_e(money(sc['spend']))}</b>{ch(sc['spend'], sp['spend'])}</div>
<div><span class='muted'>לידים</span><b>{sc['leads']}</b>{ch(sc['leads'], sp['leads'])}</div>
<div><span class='muted'>עלות לליד</span><b>{_e(money(sc['cpl']))}</b>{ch(sc['cpl'], sp['cpl'])}</div>
<div><span class='muted'>יעד עלות לליד</span><b>{_e(money(r['goals'].get('targetCpl')))}</b></div>{sales_row}</div>
<h2>עלות לליד — ממוצע נע 7 ימים</h2>{_svg_line([p['cpl'] for p in roll])}
<h2>נושאים פתוחים</h2><table>{alerts_html}</table>
<h2>מה טופל ואומת בנתונים</h2><table>{res_html}</table>
<h2>פעולות שבוצעו</h2><ul>{acts_html}</ul>
<h2>הצעדים הבאים</h2><ol>{''.join(f'<li>{_e(p)}</li>' for p in plan)}</ol>
<p class="muted">כל המספרים מחושבים מנתוני הפרסום שבמערכת ({'דמו' if r['is_demo'] else 'מקור: ' + _e(run['clients'][cid]['source'])}). אין בדוח הערכות שלא ניתן לחשב.</p>
</body></html>"""


def weekly_html(db: Database, acc: str, agency: str = "") -> str:
    run = S.analysis(db, acc)
    ref = run["ref"]
    imp = S.impact(db, acc)
    c = run["counts"]
    rows_ = ""
    for r in run["results"][:15]:
        rows_ += (f"<tr><td>{_e(r['name'])}</td><td><span class='pill {r['status']}'>{S.SL[r['status']]}</span></td>"
                  f"<td>{_e(money(r['rec']['cpl']))}</td><td>{_e(money(r['base']['cpl']))}</td><td>{_e(r['alerts'][0]['title'] if r['alerts'] else '—')}</td></tr>")
    demo = any(r["is_demo"] for r in run["results"])
    return f"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><title>דוח שבועי למשרד</title><style>{CSS}</style></head><body>
<div class="top"><div><div class="brand">{_e(agency or 'ClientPulse')}</div><h1>דוח שבועי למשרד</h1><div class="muted">שבוע שמסתיים ב-{fmt_day(ref)}</div></div></div>
{"<div class='demo'>כולל נתוני דמו (מדומים)</div>" if demo else ""}
<h2>מצב התיק</h2><div class="k"><div>תקינים<b>{c['green']}</b></div><div>במעקב<b>{c['yellow']}</b></div><div>דחופים<b>{c['red']}</b></div><div>השתפרו<b>{c['improved']}</b></div></div>
<h2>טיפול ותוצאות</h2><div class="k"><div>חריגות שזוהו<b>{imp['detected']}</b></div><div>טופלו<b>{imp['handled']}</b></div>
<div>אומתו בנתונים<b>{imp['verified']}</b></div><div>זמן ממוצע עד טיפול<b>{_e(str(imp['avg_days_to_handle']) + ' ימים' if imp['avg_days_to_handle'] is not None else '—')}</b></div></div>
<h2>הלקוחות בעדיפות</h2><table><tr><th>לקוח</th><th>מצב</th><th>עלות לליד 7 ימים</th><th>קודם</th><th>נושא</th></tr>{rows_}</table>
<h2>מה עושים השבוע</h2><ol>{''.join(f"<li>{_e(x['text'])}</li>" for x in S.top_actions(db, acc, run, 5))}</ol>
</body></html>"""


async def to_pdf(html_doc: str) -> bytes:
    from playwright.async_api import async_playwright

    from ..audit.browser import launch
    async with async_playwright() as pw:
        browser = await launch(pw)
        try:
            page = await browser.new_page()
            await page.route("**/*", lambda route: route.abort() if not route.request.url.startswith("data:") else route.continue_())
            await page.set_content(html_doc, wait_until="load")
            return await page.pdf(format="A4", print_background=True, margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"})
        finally:
            await browser.close()
