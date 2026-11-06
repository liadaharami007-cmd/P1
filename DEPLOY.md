# העלאת P1 לאוויר בחינם (פיילוט) + חיבור AI חינמי

כל השלבים חינמיים. אף מפתח לא נכתב בקוד — רק בהגדרות של GitHub / Hugging Face.

## שלב 1 — מפתח Gemini (AI חינמי, 2 דקות)
1. נכנסים ל-https://aistudio.google.com עם חשבון Google.
2. **Get API key** → **Create API key** → מעתיקים.
3. שומרים אותו בצד (משתמשים בו בשלב 3). לא שולחים אותו בצ'אט.

## שלב 2 — Space ב-Hugging Face (שרת חינמי עם HTTPS)
1. נרשמים ב-https://huggingface.co (חינם).
2. **New Space** → שם: `p1-ai` → SDK: **Docker** → Blank → Hardware: **CPU basic (free)** → Public.
3. בהגדרות החשבון: **Settings → Access Tokens → New token** מסוג **Write** → מעתיקים.

## שלב 3 — הגדרות ה-Space (Settings → Variables and secrets)
| סוג | שם | ערך |
|---|---|---|
| Secret | `GEMINI_API_KEY` | המפתח משלב 1 |
| Variable | `P1_PUBLIC_URL` | `https://<username>-p1-ai.hf.space` |
| Variable | `P1_BOOTSTRAP_EMAIL` | המייל שלך — רק הוא יוכל להירשם ראשון ולהיות מנהל |
| Variable | `P1_ALLOW_SIGNUP` | `0` (סגור לזרים) |

## שלב 4 — חיבור GitHub ל-Space (פריסה אוטומטית)
ב-GitHub: מאגר P1 → **Settings → Secrets and variables → Actions**:
- **Secret** `HF_TOKEN` = הטוקן משלב 2.
- **Variable** `HF_SPACE` = `<username>/p1-ai`.
אחר כך: **Actions → Deploy to Hugging Face Space → Run workflow**. הבנייה לוקחת ~5–10 דקות.

## שלב 5 — כניסה
פותחים את `https://<username>-p1-ai.hf.space` במחשב או בספארי באייפון → נרשמים עם המייל משלב 3 → "הוספה למסך הבית".

## מגבלות המסלול החינמי (חשוב לדעת)
- **הנתונים לא נשמרים לתמיד:** כשה-Space מופעל מחדש — המשתמשים והבדיקות נמחקים. מתאים להדגמה ולפיילוט קצר. אחסון קבוע ב-HF בתשלום (~5$ לחודש).
- **נרדם אחרי כ-48 שעות בלי שימוש** — בכניסה הבאה מתעורר תוך דקה-שתיים.
- **Gemini חינמי:** מגבלת בקשות לדקה/ליום. P1 מנסה שוב אוטומטית ומציג הודעה ברורה אם עברתם את המכסה.
