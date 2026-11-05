"""Fix Studio — תצוגה מקדימה אמיתית בעותק מבודד.

הדפדפן טוען את העמוד האמיתי מהאתר (קריאה בלבד), מצלם "לפני" עם סימון אזור הבעיה,
מחיל את התיקון רק בזיכרון של הדפדפן שלנו (DOM/CSS), ומצלם "אחרי" באותה נקודת גלילה.
האתר המקורי לא משתנה בשום צורה — אין לנו גישת כתיבה אליו.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from playwright.async_api import Error as PWError
from playwright.async_api import TimeoutError as PWTimeout
from playwright.async_api import async_playwright

from ..audit.browser import HostGuard, launch, new_context

_SEM = asyncio.Semaphore(2)  # הגבלת משאבים: עד 2 תצוגות מקדימות במקביל

JS_LIB = r"""
window.__p1fix = (() => {
  const ATC = /(הוסף|הוספה|הוסיפו)\s*(ל)?\s*(סל|עגלה)|add\s+to\s+(cart|bag|basket)|קנה\s+עכשיו|buy\s+now|לרכישה/i;
  const vis = (el) => { const r = el.getBoundingClientRect(), s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const find = {
    atc: () => document.querySelector('[data-p1-target=atc]') || [...document.querySelectorAll('button, input[type=submit], a, [role=button]')]
      .find((el) => vis(el) && (ATC.test(el.innerText || el.value || '') || el.name === 'add' || /add-to-cart/i.test(el.className))),
    h1: () => [...document.querySelectorAll('h1')].find(vis) || null,
    footer: () => document.querySelector('footer') || null,
    header: () => document.querySelector('header') || document.querySelector('nav') || null,
    overlay: () => [...document.querySelectorAll('body *')].find((el) => {
      const s = getComputedStyle(el); if (!(s.position === 'fixed' || s.position === 'sticky') || !vis(el)) return false;
      const r = el.getBoundingClientRect(), vw = innerWidth, vh = innerHeight;
      return (Math.min(r.right, vw) - Math.max(r.left, 0)) * (Math.min(r.bottom, vh) - Math.max(r.top, 0)) / (vw * vh) > 0.45; }) || null,
  };
  const outline = (el, color, label) => {
    if (!el) return false;
    el.style.outline = `3px solid ${color}`; el.style.outlineOffset = '4px';
    const tag = document.createElement('div'); tag.setAttribute('data-p1-mark', '');
    tag.textContent = label; const r = el.getBoundingClientRect();
    Object.assign(tag.style, { position: 'absolute', top: (scrollY + r.top - 30) + 'px', left: (scrollX + Math.max(r.left, 4)) + 'px', background: color,
      color: '#fff', font: '700 13px system-ui,Arial', padding: '4px 10px', borderRadius: '6px', zIndex: 2147483647 });
    document.body.appendChild(tag); return true;
  };
  return {
    mark(target) { const el = target ? find[target]?.() : null; if (el) el.scrollIntoView({ block: 'center' }); return outline(el, '#d03b3b', 'הבעיה'); },
    unmark() { document.querySelectorAll('[data-p1-mark]').forEach((n) => n.remove()); document.querySelectorAll('[style*="outline"]').forEach((n) => { n.style.outline = ''; }); },
    apply(ops) {
      const out = [];
      for (const op of ops) {
        let ok = false, note = '';
        try {
          if (op.op === 'insert_after') { const el = find[op.target]?.(); if (el) { (el.closest('form') && op.target === 'atc' ? el.closest('form') : el).insertAdjacentHTML('afterend', op.html); ok = true; } else note = 'target-not-found'; }
          else if (op.op === 'append_body') { document.body.insertAdjacentHTML('beforeend', op.html); ok = true; }
          else if (op.op === 'set_text') { const el = find[op.target]?.(); if (el) { el.textContent = op.text; el.setAttribute('data-p1-fix', ''); ok = true; } else note = 'target-not-found'; }
          else if (op.op === 'hide_overlays') { let n = 0; for (let i = 0; i < 5; i++) { const el = find.overlay(); if (!el) break; el.style.display = 'none'; n++; }
            document.documentElement.style.overflow = ''; document.body.style.overflow = ''; ok = n > 0; note = `hidden:${n}`; }
          else if (op.op === 'inject_css') { const s = document.createElement('style'); s.textContent = op.css; document.head.appendChild(s); ok = true; }
          else if (op.op === 'add_viewport') { if (!document.querySelector('meta[name=viewport]')) { const m = document.createElement('meta'); m.name = 'viewport'; m.content = 'width=device-width, initial-scale=1'; document.head.appendChild(m); } ok = true; }
          else if (op.op === 'append_footer') { const el = find.footer(); if (el) el.insertAdjacentHTML('afterbegin', op.html); else document.body.insertAdjacentHTML('beforeend', op.html); ok = true; note = el ? 'footer' : 'body-end'; }
          else if (op.op === 'insert_top') { const el = find.header(); if (el) el.insertAdjacentHTML('afterend', op.html); else document.body.insertAdjacentHTML('afterbegin', op.html); ok = true; }
          else if (op.op === 'mark_target') { const el = find[op.target]?.(); if (el) { el.setAttribute('data-p1-target', op.target); ok = true; } else note = 'target-not-found'; }
        } catch (e) { note = String(e).slice(0, 120); }
        out.push({ op: op.op, target: op.target || null, ok, note });
      }
      const added = document.querySelector('[data-p1-fix]');
      if (added) { added.style.outline = '3px solid #0ca30c'; added.style.outlineOffset = '3px'; }
      return out;
    },
  };
})();
"""

DESKTOP = {"viewport": {"width": 1366, "height": 900}, "locale": "he-IL"}


async def render_preview(url: str, preview: dict, out_dir: Path, *, allow_private: bool = False) -> dict:
    """מחזיר {before, after, applied} — נתיבי צילומים ורשימת פעולות שהוחלו בפועל. זורק RuntimeError בכשל."""
    out_dir.mkdir(parents=True, exist_ok=True)
    guard = HostGuard(allow_private)
    if not await guard.is_allowed(url):
        raise RuntimeError("הכתובת חסומה (כתובת פנימית)")
    async with _SEM, async_playwright() as pw:
        browser = await launch(pw)
        try:
            device = pw.devices["iPhone 13"] | {"locale": "he-IL"} if preview.get("device") == "mobile" else DESKTOP
            ctx = await new_context(browser, guard, device)
            page = await ctx.new_page()
            try:
                await page.goto(url, wait_until="load", timeout=45000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=4000)
                except PWTimeout:
                    pass
            except PWError as e:
                raise RuntimeError(f"לא הצלחתי לטעון את העמוד: {str(e).splitlines()[0][:150]}")
            await page.evaluate(JS_LIB)
            marked = await page.evaluate("t => window.__p1fix.mark(t)", preview.get("mark"))
            await page.wait_for_timeout(300)
            before = out_dir / "before.jpg"
            await page.screenshot(path=str(before), type="jpeg", quality=75)
            await page.evaluate("() => window.__p1fix.unmark()")
            applied = await page.evaluate("ops => window.__p1fix.apply(ops)", preview.get("ops", []))
            await page.wait_for_timeout(400)
            after = out_dir / "after.jpg"
            await page.screenshot(path=str(after), type="jpeg", quality=75)
            await ctx.close()
        finally:
            await browser.close()
    return {"before": str(before), "after": str(after), "applied": applied, "problem_marked": bool(marked),
            "page_url": url, "device": preview.get("device", "desktop")}


def summarize_applied(applied: list[dict]) -> str:
    return json.dumps(applied, ensure_ascii=False)
