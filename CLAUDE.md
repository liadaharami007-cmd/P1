# CLAUDE.md — P1 AI

הקובץ הזה נקרא אוטומטית בכל שיחה חדשה עם Claude Code. הוא מסכם מה הפרויקט, איך הוא בנוי ואיך עובדים עליו.

## מטרת הפרויקט
P1 AI היא מערכת AI לעסקים: צ'אט כמו ChatGPT שגם **מבצע פעולות אמיתיות** —
חוקר אתרים, מזהה בעיות שפוגעות במכירות, מנתח שיווק, מטפל בלקוחות ומפעיל אוטומציות.

## כללי עבודה (חובה)
1. **עובדים רק במאגר P1.** אסור לגעת בפרויקט EYES STUDIO או בכל מאגר אחר.
2. **אין הדמיות.** לא בונים כפתור/מסך שלא עובד באמת. יכולת שלא מחוברת — מוצגת כ"לא מחוברת" ואומרים בדיוק מה חסר (איזה מפתח/חיבור).
3. **מסבירים למשתמש בעברית פשוטה** — המשתמש מתחיל בפיתוח.
4. **כותבים קוד, מריצים ובודקים בפועל**: `pytest` + הרצת השרת ובדיקה בדפדפן לפני שאומרים "עובד".
5. **commits מסודרים** ודחיפה ל-GitHub בסוף כל שלב.
6. **לפני פעולה שדורשת הרשאות, תשלום או שינוי חיצוני — מבקשים אישור** מהמשתמש.
7. מפתחות API לעולם לא נכנסים לקוד או ל-git — רק לקובץ `.env` (שנמצא ב-`.gitignore`).

## ארכיטקטורה
```
דפדפן (HTML/CSS/JS פשוט, RTL)  ──HTTP/JSON──►  FastAPI (Python)
                                                 ├── agent.py   ← לולאת סוכן מול Claude API (כלים)
                                                 ├── research/  ← חוקר אתרים אמיתי (httpx + BeautifulSoup)
                                                 └── db.py      ← SQLite: שיחות, הודעות, דוחות
```
- **שפה:** Python 3.10+ (נבדק על 3.13).
- **AI:** Anthropic Python SDK (`anthropic`), מודל ברירת מחדל `claude-opus-5-5` (ניתן לשנות ב-`P1_MODEL`).
  - thinking אדפטיבי, `effort: medium`, ו-`fallbacks: "default"` (beta `server-side-fallback-2026-07-01`) — אם המודל מסרב, השרת של Anthropic מנסה מודל חלופי.
  - לולאה ידנית (`Agent.send`): Claude → בקשת כלי → מריצים את הכלי → מחזירים תוצאה → עד שמסיים.
  - **ההיסטוריה נשמרת בדיוק בפורמט ה-API ולא נערכת אחרי שנשמרה** (append-only) — נדרש כדי שבלוקי thinking יישארו תקפים.
  - הודעות נשמרות רק בנקודות עקביות (אחרי תשובה מלאה + תוצאות כלים). אם הקריאה הראשונה נכשלה — שום דבר לא נשמר והמשתמש יכול לנסות שוב.
- **כלים לסוכן כרגע:** `analyze_website(url)` בלבד. כלי חדש = להוסיף ל-`TOOLS` ול-`Agent._run_tool` + לעדכן את `SYSTEM_PROMPT`.
- **חוקר אתרים** (`app/research/analyzer.py`): מוריד את העמוד, מודד זמן תגובה, בודק SEO, מובייל, יצירת קשר, CTA, כלי מדידה, Open Graph, נגישות בסיסית, robots/sitemap, עד 10 קישורים פנימיים. כל בעיה כוללת `sales_impact` (למה זה פוגע במכירות) ו-`recommendation`.
  - **הגנת SSRF:** חסימת כתובות פנימיות (localhost, 10.x, 192.168.x, 169.254.x וכו'), כולל אחרי הפניות (redirects).
- **מסד נתונים:** SQLite בקובץ `data/p1.db` (לא נכנס ל-git). טבלאות: `conversations`, `messages`, `research_reports`.

## מבנה תיקיות
```
app/
  config.py          הגדרות ממשתני סביבה / .env
  db.py              שכבת SQLite
  agent.py           הסוכן + הכלים + המרה לתצוגה
  main.py            FastAPI: API + הגשת הממשק
  research/analyzer.py  חוקר האתרים
  static/            index.html, app.css, app.js
tests/               pytest (Claude מדומה בבדיקות — אין צורך במפתח)
```

## API
| Method | Path | מה עושה |
|---|---|---|
| GET | `/api/status` | אילו יכולות מוכנות ומה חסר |
| GET/POST | `/api/conversations` | רשימה / יצירת שיחה |
| GET/DELETE | `/api/conversations/{id}` | שיחה עם ההודעות / מחיקה |
| POST | `/api/conversations/{id}/messages` | שליחת הודעה לסוכן (`{"text": ...}`) |
| POST | `/api/research` | חקירת אתר ישירה, בלי AI (`{"url": ...}`) |
| GET | `/api/research`, `/api/research/{id}` | היסטוריית דוחות / דוח מלא |

## פקודות
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # ולמלא ANTHROPIC_API_KEY
uvicorn app.main:app --reload --port 8000   # http://localhost:8000
python -m pytest -q
```

## סטטוס (עדכנו בסוף כל שלב)
### שלב 1 — בסיס (הושלם)
- [x] שרת FastAPI + ממשק צ'אט בעברית (RTL, מובייל)
- [x] שמירת שיחות ב-SQLite, רשימת שיחות, מחיקה
- [x] חוקר אתרים אמיתי + דוח בעיות שפוגעות במכירות + היסטוריית דוחות
- [x] סוכן Claude עם כלי `analyze_website` (נבדק עם Claude מדומה; **דורש ANTHROPIC_API_KEY להפעלה אמיתית**)
- [x] בדיקות אוטומטיות (pytest)

### מה חסר / השלבים הבאים
- [ ] `ANTHROPIC_API_KEY` — בלעדיו הצ'אט מושבת (חקירת אתרים עובדת גם בלעדיו)
- [ ] אירוח (deploy) — לא בוצע; דורש בחירת ספק ואישור המשתמש
- [ ] הזרמת תשובות (streaming) בצ'אט
- [ ] משתמשים והתחברות (כרגע אין הרשאות — לא לחשוף לאינטרנט בלי זה!)
- [ ] חקירה מעמיקה: כמה עמודים, רינדור JavaScript (Playwright), Core Web Vitals (PageSpeed API — דורש מפתח Google)
- [ ] ניתוח שיווק (Google Analytics / Meta Ads — דורש חיבורי OAuth)
- [ ] טיפול בלקוחות (וואטסאפ/מייל — דורש WhatsApp Business API / ספק מייל)
- [ ] אוטומציות (תזמון משימות, webhooks)

## הערות לסביבת הענן של Claude Code
בסביבת הפיתוח בענן הגישה לאינטרנט מוגבלת לרשימת דומיינים; אתרים רבים (למשל example.com) נחסמים שם ע"י ה-proxy. זו מגבלה של סביבת הפיתוח בלבד, לא של הקוד. pypi.org זמין שם ושימש לבדיקה חיה.
