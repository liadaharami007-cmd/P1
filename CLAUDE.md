# CLAUDE.md — P1 AI

הקובץ הזה נקרא אוטומטית בכל שיחה חדשה עם Claude Code. הוא מסכם את החזון, הארכיטקטורה, כללי העבודה והסטטוס.

## החזון
P1 AI היא **פלטפורמת SaaS ל-Commerce Intelligence**: בעל חנות מוסיף אתר → סוכני דפדפן אמיתיים בודקים אותו →
ממצאים אמיתיים מסודרים לפי עדיפות → **Fix Studio** מראה פתרון מוחשי עם תצוגה מקדימה ו-Before/After → מעקב חודשי (Smart Monitor).
יעד: מוצר שאפשר להציג לבוס/משקיעים ולמכור כמנוי חודשי. עובדים כ-CTO + צוות (Full-Stack, AI Architect, Product Designer, CRO, QA).

## כללי עבודה (חובה)
1. **רק מאגר P1.** אסור לגעת ב-EYES STUDIO או במאגר אחר. לא יוצרים פרויקט נוסף. לא מוחקים יכולות או מידע קיימים.
2. **אין הדמיות ואין נתוני דמו שמתחזים לאמת.** כפתור שלא עובד לא נבנה. יכולת לא מחוברת מוצגת "לא מחוברת" + מה חסר.
   חנות הדמו (`/demo-store/`) מסומנת "דמו" בכל מקום — אבל הבדיקה שרצה עליה אמיתית.
3. **הפרדת מקורות מידע — חובה.** `findings.source`: `measured` (נמדד בדפדפן / ע"י סוכן) · `simulation` · `store_data` (עתידי) · `ai`.
   **הציון רק מ-`measured`.** אסור להמציא אחוזי המרה/נטישה/שיפור — השפעה = high/medium/low.
4. **לא קוראים לדבר "AI" אם אין בו מודל.** סוכני הלקוח היום = `engine: rules` ומוצגים כ"מבוססי כללים". תבניות Fix Studio = `templates`.
   בלי מנוע מודל זמין: `ai_status=not_configured`. (Claude מדומה קיים רק בתוך `tests/`.)
5. **אין להוציא כסף** על API / שרתים בלי אישור. קודם חינמי וקוד פתוח.
6. **עברית פשוטה למשתמש** (מתחיל בפיתוח). ממשק he/en.
7. **מריצים ובודקים בפועל לפני "עובד"**: `pytest` + `npm run typecheck` + שרת + מעבר בדפדפן (מחשב + iPhone).
8. **commits מסודרים** ודחיפה לענף `claude/p1-ai-initial-setup-2jx3ei` בסוף כל שלב.
9. **פעולה שדורשת הרשאות / תשלום / שינוי חיצוני — רק באישור המשתמש.** סודות רק ב-`.env` / משתני סביבה.
10. **בטיחות:** הסוכנים לא ממלאים פרטים, לא משלמים, לא מזמינים (עוצרים בקופה). Fix Studio **לעולם לא משנה את האתר** — רק עותק בזיכרון של הדפדפן שלנו.
    בדיקה דורשת אישור בעלות/הרשאה. HostGuard חוסם כתובות פנימיות (SSRF) בכל בקשה, כולל הפניות. חריג יחיד: חנות הדמו של השרת עצמו.

## ארכיטקטורה
```
SPA (vanilla ES modules + JSDoc/TypeScript check, i18n he/en, RTL/LTR) ── JSON + SSE + session cookie
FastAPI (app/main.py): request-id, JSON logs, CSRF origin check, CSP, auth על כל endpoint, סינון לפי account_id
  saas/          auth (scrypt, sessions, rate limit) · plans (מכסות + תדירויות מעקב) · billing (ממשק — לא מחובר)
  audit/         collector.py   ליבת המסלול: בית → אמון → קישורים → מוצר → סל → עגלה → קופה (עצירה) → חיפוש → iPhone
                 rules.py       עובדות + תוצאות סוכנים → ממצאים measured (כולל Conversion Intelligence) · RULE_CATEGORY
                 priority.py    סדר עדיפות שקוף: חומרה × השפעה ÷ מאמץ
                 scoring.py · compare.py · personas.py (סימולציה מבוססת כללים — legacy, נשמר)
                 runner.py      תור מתמיד ב-DB + worker + שלבים: ליבה → 5 סוכנים → finalize → התראות → AI. עצירה/חידוש.
  agents/        base.py (AgentContext: יומן, צילום, retry, סגירת חלונות קופצים, עצירה, Brain interface) ·
                 customers.py (trust / fast_buyer / price / confused / mobile_ad) · orchestrator.py (דפדפן אחד, 2 במקביל)
  fixstudio/     catalog.py (מחוללי תיקון לכל rule_id: copy/structure/design/code/preview ops; יתרונות אמיתיים מהעמוד; [להשלמה] במקום המצאה)
                 sandbox.py (Chromium: טוען עמוד אמיתי → מסמן בעיה → מחיל ops על DOM מבודד → צילום לפני/אחרי) · service.py
  business/      Business OS: store.py (פרופיל/פעולות/יומן, מסונן לפי account) · brain.py (שדות פרופיל + אימות) ·
                 ceo.py (בריאות לפי תחום — ציון כולל רק עם ≥3 תחומים מדודים · תוכנית + top3 · הוכחת ערך · ציר זמן · דוח שבועי · ai_brief) ·
                 actions.py (Approval Center: run_audit / verify_fix / enable_monitor / fix_package — אף אחד לא משנה אתר חי) · routes.py
  saas/billing.py  ממשק ספק + Paddle (Stripe לא תומך בישראל). webhook חתום (Paddle-Signature) + billing_events לאידמפוטנטיות
  saas/recovery.py שחזור סיסמה (אסימון hash חד-פעמי 30 דק', SMTP או קישור ממנהל)
  static/welcome.html  אתר שיווקי ציבורי (/welcome) · static/sw.js + manifest.webmanifest = PWA
  intelligence/  engines.py (anthropic / ollama / rules — מציג איזה פעיל) · analyst.py · personas_ai.py · client.py (עלויות)
  monitor.py     Smart Monitor: tick כל דקה מה-worker, השוואה, התראות new/fixed/score
  report/        data.py · pdf.py (PDF ע"י Chromium)
  static/demo-store/  חנות דמו "סדנת פשתן" עם בעיות מכוונות (חלון קופץ, מדיניות דלה, כפתור לא בולט, קופה עם הרשמה כפויה, קישור שבור…)
  db.py          SQLite + מיגרציות (user_version=4: business_profiles, actions, activity, password_resets, billing_events): agent_runs, fix_previews, monitors, notifications, findings.fix_status/priority…
```
- **מנועי AI (engines.py):** `P1_AI_ENGINE=auto|anthropic|ollama|rules`. Ollama: `P1_OLLAMA_URL`, `P1_OLLAMA_MODEL` (ברירת מחדל qwen2.5:7b-instruct), `P1_OLLAMA_VISION=1`.
  Claude: `claude-opus-5-5`, adaptive thinking, structured outputs, `fallbacks: "default"`. כל קריאה ב-`ai_runs` (Ollama = עלות 0).
- **Live Mission Control:** `GET /api/audits/{id}/stream` (SSE, נתונים מה-DB בלבד, אירוע `end` בסיום).
- **אירועי יומן:** `audit_events(kind, message, page_url, screenshot_id, ref=step, agent)`.

## API עיקרי (בנוסף לקודם)
| Path | |
|---|---|
| `GET /api/audits/{id}/stream` | SSE חי |
| `POST /api/audits/{id}/stop` · `/resume` | עצירה · חידוש סוכנים שלא הסתיימו |
| `GET /api/audits/{id}/fixes` · `POST /api/findings/{id}/preview` · `PATCH /api/findings/{id}/fix` | Fix Studio |
| `GET/POST /api/sites` · `PUT /api/sites/{id}/monitor` · `GET /api/sites/{id}/progress` | אתרים מורשים + Smart Monitor |
| `GET /api/notifications` · `POST /api/notifications/read` | התראות |
| `GET /api/engines` · `POST /api/demo/start` | מנועים · בדיקת דמו |
| `GET/PUT /api/business/profile` · `GET /api/business/overview` · `/weekly` · `/timeline` · `POST /api/business/brief` | Business OS |
| `GET/POST /api/actions` · `POST /api/actions/{id}/approve` · `/reject` · `GET /api/actions/{id}/package.html` | מרכז אישורים |
| `GET /api/billing` · `POST /api/billing/checkout` · `/portal` · `/webhook` | תשלומים (Paddle) |
| `POST /api/auth/forgot` · `/api/auth/reset` · `POST /api/admin/reset-link` | שחזור סיסמה |
| `GET /welcome` · `GET /api/public/plans` · `/manifest.webmanifest` · `/sw.js` | ציבורי |
(קיימים: auth, audits, report.pdf, compare, methodology, tasks, dashboard, account, admin, conversations.)

## פקודות
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m playwright install chromium     # מקומי (בענן: /opt/pw-browsers)
npm install && npm run typecheck
uvicorn app.main:app --port 8000          # http://localhost:8000 → מצב הדגמה: #/demo
python -m pytest -q                       # ~3 דק' — כולל מסעות רכישה + 5 סוכנים + תצוגות Fix Studio בדפדפן אמיתי
```
משתני סביבה נוספים: `P1_RUN_WORKER` (0 = worker נפרד: `python -m app.worker`), `P1_COOKIE_SECURE=1`, `P1_ALLOW_SIGNUP`,
`P1_DEV_ALLOW_PRIVATE_TARGETS=1` (**פיתוח בלבד**), `P1_MAX_CONCURRENT_AUDITS`.

## תוכנית
- ✅ 1 בסיס · ✅ 2 MVP Auditor · ✅ 3 מקצה לקצה + SaaS + עיצוב v2
- ✅ **3.0 (נוכחי):** Fix Studio (תצוגה מקדימה אמיתית + Before/After + סטטוס יישום) · 5 סוכני לקוח גולשים (rules) ·
  Live Mission Control (SSE) · Conversion Intelligence + סדר עדיפויות · Design System 3.0 · Smart Monitor + התראות · Demo Experience · מנועי AI מודולריים
- ✅ **Business OS (נוכחי):** מרכז פיקוד (3 הפעולות הבאות) · פרופיל עסק · מרכז אישורים · אימות תיקון במדידה · ציר צמיחה · דוח שבועי ·
  PWA לאייפון · אתר שיווקי + מחשבון חיסכון · Paddle (מוק) · שחזור סיסמה · Dockerfile (לא נבנה). פירוט: `PROGRESS.md`. מה חסר מהמשתמש: `REQUIREMENTS.md`.
- **הבא:** פריסה (באישור) · בדיקת טפסי לידים/וואטסאפ · התראות וואטסאפ/מייל · ModelBrain לסוכנים (Ollama/Claude מחליטים על הצעד הבא) · שכתוב AI ב-Fix Studio כשמנוע זמין · Postgres + worker נפרד + Redis ·
  אימות בעלות (meta/DNS) · איפוס סיסמה/אימות מייל · צוותים · אחסון S3 · Shopify OAuth (store_data) · ספק תשלומים · פריסה (Docker) · תרגום טקסטי כללים לאנגלית.

## סטטוס וידוע
- נבדק: pytest מלא (כולל בדפדפן אמיתי), typecheck, מעבר מלא בדפדפן על חנות הדמו (מחשב + iPhone).
- **אין מודל שפה פעיל בסביבת הענן:** ollama.com / Hugging Face חסומים ברשת, ואין ANTHROPIC_API_KEY → המנוע הפעיל = rules.
- חנויות אמיתיות מהאינטרנט חסומות בסביבת הענן (pypi.org פתוח). בדיקות: חנויות fixtures + חנות הדמו.
- חנות הדמו רצה על http://localhost → ממצא "אין HTTPS" נכון לסביבה הזו (בפריסה עם HTTPS ייעלם).
- SQLite + worker בתהליך השרת — מתאים לפיילוט. `data-backup-v1/` = גיבוי נתוני פיתוח ישנים (לא ב-git).
