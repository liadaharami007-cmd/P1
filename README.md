# P1 AI

מערכת AI לעסקים: צ'אט חכם שגם מבצע פעולות — מתחיל בחקירת אתרים ואיתור בעיות שפוגעות במכירות.

## הפעלה מהירה
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # הכניסו ANTHROPIC_API_KEY (מ-https://console.anthropic.com)
uvicorn app.main:app --reload --port 8000
```
פתחו http://localhost:8000

- **חקירת אתר** — עובדת מיד, גם בלי מפתח.
- **צ'אט AI** — דורש `ANTHROPIC_API_KEY`. בלעדיו הממשק מציג בבירור שהצ'אט לא מחובר.

## בדיקות
```bash
python -m pytest -q
```

פרטים על הארכיטקטורה וכללי העבודה: [CLAUDE.md](CLAUDE.md).
