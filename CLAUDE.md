# CLAUDE.md — P1 AI

הקובץ הזה נקרא אוטומטית בכל שיחה חדשה עם Claude Code. הוא מסכם את החזון, הארכיטקטורה, כללי העבודה והסטטוס.

## החזון
P1 AI היא **חברת SaaS** לבעלי חנויות אונליין: מערכת שעובדת כמו צוות מומחי CRO, UX, QA, מכירות ושירות לקוחות.
בעל העסק מכניס כתובת — סוכן דפדפן אמיתי בודק את החנות, Claude מנתח את הראיות, ובעל העסק מקבל דוח, תוכנית פעולה ומעקב שיפור.
יעד: מוצר ברמה בינלאומית שאפשר להציג למשקיעים ולמכור כמנוי חודשי. אנחנו עובדים כ-CTO + צוות (Full-Stack, AI Architect, Product Designer, PM, QA, CRO).

## כללי עבודה (חובה)
1. **רק מאגר P1.** אסור לגעת ב-EYES STUDIO או במאגר אחר. לא יוצרים פרויקט נוסף. לא מוחקים יכולות עובדות.
2. **אין הדמיות ואין נתוני דמו שמתחזים לאמת.** כפתור שלא עובד לא נבנה. יכולת לא מחוברת מוצגת "לא מחוברת" + מה חסר.
3. **הפרדת מקורות מידע — חובה בכל פיצ'ר.** `findings.source`:
   `measured` (נבדק בדפדפן) · `simulation` (לקוח מדומה) · `store_data` (חיבור לחנות — עתידי) · `ai` (השערת Claude).
   הממשק וה-PDF מציגים תגית מקור. **הציון מחושב רק מ-`measured`.** אסור להמציא אחוזי המרה/נטישה/שיפור — השפעה = high/medium/low.
4. **לא מציגים תשובת AI מדומה כאילו Claude ענה.** בלי `ANTHROPIC_API_KEY`: `ai_status=not_configured`, והממשק אומר זאת. (Claude מדומה קיים רק בתוך `tests/`.)
5. **עברית פשוטה למשתמש** (מתחיל בפיתוח). ממשק דו-לשוני he/en.
6. **מריצים ובודקים בפועל לפני "עובד"**: `pytest` + `npm run typecheck` + שרת + מעבר בדפדפן במחשב ובמובייל.
7. **commits מסודרים** ודחיפה לענף `claude/p1-ai-initial-setup-2jx3ei` בסוף כל שלב.
8. **פעולה שדורשת הרשאות, תשלום או שינוי חיצוני — רק באישור המשתמש.** לא מבקשים מפתח API אם אפשר להתקדם בלעדיו.
9. סודות רק ב-`.env` (ב-`.gitignore`) או במשתני סביבה בשרת. לעולם לא בקוד, בלוגים או בדפדפן.
10. **בטיחות הסוכן:** לא ממלא פרטים, לא משלם, לא מזמין — עוצר בכניסה לקופה. דורש אישור בעלות/הרשאה. HostGuard חוסם כתובות פנימיות בכל בקשה (SSRF), כולל הפניות.

## ארכיטקטורה
```
Browser SPA (vanilla ES modules + JSDoc/TypeScript check, i18n he/en, RTL/LTR)
        │ JSON + session cookie (HttpOnly, SameSite=Lax)
        ▼
FastAPI (app/main.py) ── middleware: request-id, JSON logs, CSRF origin check, security headers (CSP)
  ├── saas/        auth.py (scrypt, sessions, rate limit) · plans.py (מסלולים + מכסות) · billing.py (ממשק לספק תשלומים — לא מחובר)
  ├── audit/       P1 Browser Agent
  │     collector.py  Playwright/Chromium: בית → אמון → קישורים → מוצר → סל → עגלה → קופה (עצירה) → חיפוש → iPhone
  │                   יומן פעולות חי (audit_events), צילומי מסך, טקסט עמודים כראיה, מגבלות משאבים
  │     rules.py      עובדות → ממצאים measured (+ שיוך שקוף לחלקי הדוח RULE_CATEGORY)
  │     scoring.py    שיטת ציון מוגדרת (methodology(): penalty, weights, cap) — רק measured
  │     personas.py   סימולציית לקוחות מבוססת כללים (simulation)
  │     compare.py    Before/After דטרמיניסטי בין בדיקות
  │     runner.py     תור עבודות מתמיד ב-DB + worker (בתוך השרת או `python -m app.worker`) + שלב AI
  ├── intelligence/ P1 Intelligence (Claude, צד שרת בלבד)
  │     client.py     AsyncAnthropic עם base_url מפורש, fallbacks, טיפול בשגיאות, חישוב עלות לפי מחירון
  │     evidence.py   חבילת ראיות: צעדים, ממצאים, עובדות, טקסט, צילומי מסך (vision)
  │     analyst.py    סיכום מנהלים, ai_findings (עם confidence + evidence_refs), הצעות ניסוח, תוכנית פעולה, פרשנות השוואה
  │     personas_ai.py 5 סוכני לקוח (Claude): מחיר, חושש, ממהר, לא מבין יתרונות, הגיע מפרסומת בטלפון
  ├── report/      data.py (הרכבת דוח משותף) · pdf.py (PDF ע"י Chromium, פונטים מוטמעים)
  ├── agent.py     עוזר צ'אט עם כלי analyze_website
  └── db.py        SQLite + מיגרציות (PRAGMA user_version). כל נתון עם account_id; כל שאילתת משתמש מסוננת לפיו
```
- **מודל:** `claude-opus-5-5`, thinking אדפטיבי, structured outputs (JSON schema), `fallbacks: "default"`; ניתוח `effort=medium`, סוכני לקוח `effort=low`. כל קריאה נרשמת ב-`ai_runs` עם טוקנים ועלות.
- **ai_status של בדיקה:** pending → running → done / partial / failed / not_configured / quota_exceeded. כשל AI לא מכשיל את הבדיקה.
- **חלקי הדוח (CATEGORIES):** conversion · checkout · trust · ux_mobile · technical. משקלים 25/25/20/15/15. קנסות 30/15/7/3. ממצא קריטי → תקרה 49. חלק שלא נבדק = null.
- **מסלולים (plans.py):** free (1 אתר, 10 בדיקות, 3 ניתוחי AI), pro (5/100/50), agency (25/500/300). נאכף בשרת (HTTP 402).
- **המשתמש הראשון** שנרשם = מנהל פלטפורמה ומקבל נתונים ישנים (לפני חשבונות).

## API עיקרי
| | Path | |
|---|---|---|
| auth | `POST /api/auth/register · login · logout`, `GET /api/auth/me`, `GET /api/auth/config` | ציבורי |
| audits | `POST /api/audits` (202, דורש `confirm_permission`) · `GET /api/audits` · `GET/DELETE /api/audits/{id}` | |
| live | `GET /api/audits/{id}/events?after=` | יומן פעולות + התקדמות |
| AI | `POST /api/audits/{id}/analyze` | הרצה חוזרת של ניתוח AI |
| report | `GET /api/audits/{id}/report.pdf` · `GET /api/audits/{id}/compare?base=` · `GET /api/methodology` | |
| work | `PATCH /api/findings/{id}` · `GET /api/tasks` · `GET /api/dashboard` | |
| saas | `GET /api/account` · `PATCH /api/me` · `GET /api/admin/overview` · `PATCH /api/admin/accounts/{id}` | admin = מנהל פלטפורמה |
| other | `GET /api/status · /api/integrations · /api/screenshots/{id} · /api/health`, צ'אט: `/api/conversations…` | |

## פקודות
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python -m playwright install chromium     # במחשב מקומי (בענן: /opt/pw-browsers)
npm install                               # TypeScript לבדיקת טיפוסים
uvicorn app.main:app --reload --port 8000 # http://localhost:8000
python -m pytest -q                       # כולל מסעות רכישה מלאים מול חנויות בדיקה מקומיות + בדיקת טיפוסים
npm run typecheck
```
משתני סביבה: `ANTHROPIC_API_KEY`, `P1_MODEL`, `P1_DB_PATH`, `P1_DATA_DIR`, `P1_CHROMIUM_PATH`, `P1_MAX_CONCURRENT_AUDITS`,
`P1_RUN_WORKER` (0 = worker בתהליך נפרד), `P1_COOKIE_SECURE=1` (בייצור), `P1_ALLOW_SIGNUP`, `P1_LOG_LEVEL`,
`P1_DEV_ALLOW_PRIVATE_TARGETS=1` (**פיתוח בלבד** — מאפשר לבדוק את חנויות הבדיקה המקומיות).

## תוכנית פיתוח
- ✅ **שלב 1** בסיס · ✅ **שלב 2** MVP Auditor
- ✅ **שלב 3 (נוכחי):** מסלול מקצה לקצה — URL → דפדפן → מסע לקוח → ראיות → Claude → דוח 5 חלקים → PDF → היסטוריה + Before/After;
  יומן פעולות חי; SaaS (משתמשים, חשבונות, מכסות, עלויות AI, אדמין, תור עבודות); עיצוב v2; he/en; בדיקת טיפוסים.
- **שלב 4 — לפני לקוחות ראשונים:** Postgres + worker נפרד + Redis (תור/הגבלות), אחסון צילומים ב-S3, אימות בעלות על אתר (meta tag/DNS),
  איפוס סיסמה ואימות אימייל, הזמנת חברי צוות, תרגום טקסטי הכללים לאנגלית, Sentry/OTel, פריסה (Docker), גיבויים.
- **שלב 5 — סוכן מתקדם:** סוכני הלקוח מנווטים בעצמם בדפדפן (Claude + Playwright tools), כמה מוצרים/קטגוריות, שידור חי של הדפדפן.
- **שלב 6 — P1 Monitor:** בדיקות מתוזמנות + התראות על בעיות חדשות.
- **שלב 7 — P1 Shopify Integration / Conversion AI:** OAuth, הזמנות, עגלות נטושות, משפך אמיתי (source=store_data).
- **שלב 8 — P1 Support AI:** בסיס ידע מאומת, וידג'ט/וואטסאפ, "לא יודע" כשאין מקור.
- **שלב 9 — P1 Fix AI:** הצעות קוד/עיצוב, תצוגה מקדימה, פרסום רק באישור בעל האתר.
- **גבייה:** לממש `BillingProvider` (Stripe/Paddle/ספק ישראלי) + webhook שמעדכן `accounts.plan/subscription_status`.

## סטטוס וידוע
- נבדק: 37 בדיקות אוטומטיות (כולל Claude מדומה בבדיקות בלבד, PDF, הפרדת חשבונות, מכסות, CSRF, מיגרציה), typecheck, מעבר ידני מלא בדפדפן.
- **ניתוח Claude אמיתי טרם הורץ** — אין מפתח בסביבה. הצינור נבדק מקצה לקצה עם Claude מדומה בבדיקות.
- טקסטי הממצאים מהכללים בעברית בלבד (ה-AI עונה בשפת המשתמש).
- SQLite + worker בתוך תהליך השרת — מתאים לפיילוט, לא לסקייל.
- סביבת הענן חוסמת רוב האתרים → נבדק מול pypi.org וחנויות בדיקה מקומיות (`tests/fixtures`).
- `data-backup-v1/` = גיבוי נתוני פיתוח ישנים (לא ב-git).
