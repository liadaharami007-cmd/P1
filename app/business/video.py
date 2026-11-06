"""סוכן וידאו (חינמי): תסריט → סצנות מונפשות (HTML/CSS בצבעי המותג) → הקלטה בדפדפן אמיתי (Playwright) → MP4 (ffmpeg, H.264).

זה וידאו "מוטיון טקסט" אנכי (9:16) לסטורי/רילס — לא וידאו שנוצר ע"י מודל וידאו (Veo וכו' בתשלום) ובלי קריינות.
כל טקסט ב-HTML עובר escape; אין סקריפטים בעמוד הסצנות.
"""
from __future__ import annotations

import asyncio
import html
import json
import shutil
import subprocess
import uuid
from pathlib import Path

from .. import config
from ..db import Database
from . import store

W, H = 720, 1280


def _seconds(v) -> float:
    """משך סצנה מכל פורמט שמודל עלול להחזיר: 3 · "3" · "3s" · "0-5" (טווח) · "00:03-00:06" · ריק → 3."""
    import re as _re
    nums = [float(x) for x in _re.findall(r"\d+(?:\.\d+)?", str(v or ""))]
    if ":" in str(v or "") and len(nums) >= 4:
        nums = [nums[0] * 60 + nums[1], nums[2] * 60 + nums[3]]
    d = (nums[1] - nums[0]) if len(nums) >= 2 and nums[1] > nums[0] else (nums[0] if nums else 3.0)
    return max(2.0, min(6.0, d))


def _scenes_html(scenes: list[dict], brand: str, color: str, cta: str) -> tuple[str, float]:
    e = html.escape
    t, parts = 0.0, []
    for s in scenes[:8]:
        dur = _seconds(s.get("seconds"))
        # הוראת הצילום (visual) נשארת בתסריט לצלם — בסרטון מוצג רק הטקסט לקהל
        parts.append(f"<section style='animation-delay:{t:.2f}s;animation-duration:{dur:.2f}s'>"
                     f"<h2>{e(s.get('voiceover') or s.get('text') or '')[:160]}</h2></section>")
        t += dur
    end = 3.0
    parts.append(f"<section class='end' style='animation-delay:{t:.2f}s;animation-duration:{end + 1:.2f}s;animation-fill-mode:forwards'>"
                 f"<h1>{e(brand)}</h1><div class='cta'>{e(cta or 'לפרטים')}</div></section>")
    total = t + end
    return f"""<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8"><style>
*{{margin:0;box-sizing:border-box}}body{{width:{W}px;height:{H}px;overflow:hidden;font-family:system-ui,"Noto Sans Hebrew",Arial,sans-serif;
background:radial-gradient(120% 80% at 80% 0%,color-mix(in srgb,{color} 55%,#fff),{color});color:#fff}}
section{{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;gap:28px;padding:90px 70px;opacity:0;animation-name:show;animation-timing-function:ease}}
h2{{font-size:62px;line-height:1.18;font-weight:800;text-shadow:0 6px 30px rgba(0,0,0,.25)}}.v{{font-size:28px;opacity:.85;background:rgba(0,0,0,.18);padding:10px 18px;border-radius:14px;align-self:flex-start}}
.end{{align-items:center;text-align:center}}h1{{font-size:84px;font-weight:900}}.cta{{background:#fff;color:{color};font-size:44px;font-weight:800;padding:22px 44px;border-radius:999px}}
@keyframes show{{0%{{opacity:0;transform:translateY(40px) scale(.98)}}12%{{opacity:1;transform:none}}85%{{opacity:1}}100%{{opacity:0}}}}
.end{{animation-name:showEnd}}@keyframes showEnd{{0%{{opacity:0;transform:scale(.9)}}20%{{opacity:1;transform:none}}100%{{opacity:1}}}}
</style></head><body>{''.join(parts)}</body></html>""", total


async def render(db: Database, account: dict, user_id: str | None, scenes: list[dict], cta: str, title: str) -> dict:
    from playwright.async_api import async_playwright
    from ..audit.browser import launch
    prof = (store.get_profile(db, account["id"]) or {"data": {}})["data"]
    brand = prof.get("business_name") or account.get("name") or ""
    color = "#5b54e8"
    page_html, total = _scenes_html(scenes, brand, color, cta)
    vid = uuid.uuid4().hex[:16]
    out_dir = config.DATA_DIR / "videos" / account["id"]
    tmp = out_dir / f"tmp-{vid}"
    tmp.mkdir(parents=True, exist_ok=True)
    fps = 10
    frames = int(total * fps) + 1
    async with async_playwright() as pw:
        browser = await launch(pw)
        try:
            ctx = await browser.new_context(viewport={"width": W, "height": H})
            page = await ctx.new_page()
            await page.set_content(page_html, wait_until="load")
            # שליטה מדויקת בזמן: עוצרים את כל האנימציות ומזיזים אותן פריים-פריים (בלי תלות במהירות המחשב)
            for i in range(frames):
                await page.evaluate("t => document.getAnimations().forEach(a => { a.pause(); a.currentTime = t; })", i * 1000 / fps)
                await page.screenshot(path=str(tmp / f"f{i:05d}.jpg"), type="jpeg", quality=88)
            await ctx.close()
        finally:
            await browser.close()
    mp4 = out_dir / f"{vid}.mp4"
    proc = await asyncio.to_thread(subprocess.run, ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(tmp / "f%05d.jpg"),
                                                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-r", "30", str(mp4)],
                                   capture_output=True, timeout=300)
    shutil.rmtree(tmp, ignore_errors=True)
    if proc.returncode != 0 or not mp4.exists():
        raise RuntimeError("המרת הווידאו נכשלה: " + proc.stderr.decode()[:200])
    with db._conn() as c:
        c.execute("INSERT INTO videos (id, account_id, title, scenes_json, path, seconds, created_by, created_at) VALUES (?,?,?,?,?,?,?,?)",
                  (vid, account["id"], title[:120], json.dumps(scenes, ensure_ascii=False), str(mp4), round(total, 1), user_id, store.now()))
    store.log(db, account["id"], "video_created", f"P1 יצר סרטון: {title[:60]}", ref_type="video", ref_id=vid, user_id=user_id)
    return {"id": vid, "title": title, "seconds": round(total, 1), "url": f"/api/videos/{vid}.mp4"}


def list_videos(db: Database, account_id: str) -> list[dict]:
    with db._conn() as c:
        return [{**{k: r[k] for k in ("id", "title", "seconds", "created_at")}, "url": f"/api/videos/{r['id']}.mp4"}
                for r in c.execute("SELECT * FROM videos WHERE account_id=? ORDER BY created_at DESC LIMIT 30", (account_id,))]


def video_path(db: Database, vid: str, account_id: str) -> Path | None:
    with db._conn() as c:
        r = c.execute("SELECT path FROM videos WHERE id=? AND account_id=?", (vid, account_id)).fetchone()
    return Path(r["path"]) if r and Path(r["path"]).exists() else None
