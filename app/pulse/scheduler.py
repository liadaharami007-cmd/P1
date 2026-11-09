"""ClientPulse — תזמון בצד שרת. נקרא מה-worker פעם בדקה; מריץ בדיקה מלאה פעם ביום לכל סוכנות שהפעילה בדיקה יומית.
הבדיקה היומית מפעילה את האוטומציות (סיכום בוקר, הסלמות, איחורים, דוח שבועי) עם מניעת כפילות לפי run_key."""
from __future__ import annotations

from ..db import Database
from ..logging_setup import log
from . import engine, service as S, store


def tick(db: Database) -> int:
    store.ensure(db)
    today = engine.today_idx()
    ran = 0
    for w in store.rows(db, "SELECT account_id, settings_json FROM pulse_workspaces"):
        s = store.uj(w["settings_json"], {})
        if not s.get("auto_daily", True) or s.get("last_auto_real_day") == today:
            continue
        if not store.one(db, "SELECT 1 FROM pulse_clients WHERE account_id=? LIMIT 1", (w["account_id"],)):
            continue
        acc = w["account_id"]
        try:
            if s.get("demo"):
                S.sync_demo(db, acc)  # ספק הדמו "מסנכרן" את היום החדש כמו ספק אמיתי
            S.run_check(db, acc)
            cur = S.ws(db, acc)["settings"]
            cur["last_auto_real_day"] = today
            S.save_settings(db, acc, cur)
            ran += 1
        except Exception:  # noqa: BLE001 — כישלון בסוכנות אחת לא עוצר אחרות; ינסה שוב בדקה הבאה
            log.exception("pulse daily check failed", extra={"account": acc})
    return ran
