# P1 AI

**סוכן דפדפן + Claude שבודקים את החנות שלכם כמו צוות CRO, UX ו-QA.**
מכניסים כתובת → דפדפן אמיתי עובר את מסע הרכישה עד הקופה (בלי להזמין) → ראיות וצילומי מסך → ניתוח P1 Intelligence (Claude) + 5 לקוחות מדומים →
דוח שקוף ב-5 חלקים, PDF, תוכנית פעולה והשוואת Before/After.

## הפעלה
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
npm install                      # בדיקת טיפוסים (אופציונלי להרצה)
cp .env.example .env             # ANTHROPIC_API_KEY — מפעיל את ניתוח ה-AI
uvicorn app.main:app --port 8000
```
פתחו http://localhost:8000 — המשתמש הראשון שנרשם הופך למנהל הפלטפורמה.

בלי `ANTHROPIC_API_KEY` הכול עובד חוץ משכבת ה-AI, והממשק אומר זאת במפורש (אין תשובות מדומות).

## בדיקות
```bash
python -m pytest -q      # כולל מסעות רכישה מלאים בדפדפן מול חנויות בדיקה מקומיות
npm run typecheck
```

ארכיטקטורה, כללי עבודה ותוכנית: [CLAUDE.md](CLAUDE.md).

> ⚠️ לפני חשיפה לאינטרנט: `P1_COOKIE_SECURE=1`, HTTPS, ומעבר ל-Postgres + worker נפרד (ראו שלב 4 ב-CLAUDE.md).
