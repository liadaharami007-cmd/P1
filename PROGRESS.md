# P1 AI — יומן התקדמות (להמשכיות בין שיחות)

עדכון אחרון: 2026-11-06 · ענף: `claude/p1-ai-initial-setup-2jx3ei` · נקודת שחזור לפני Business OS: tag `restore-point-before-business-os`

## מה נבנה בסבב "Business OS" (נבדק בפועל)
| שלב | מה | איך נבדק |
|---|---|---|
| 1 Stabilize | תיקון SSRF בכפתור הדמו (כתובת מהגדרות השרת, לא מכותרת Host) | pytest מלא |
| 3 Business OS | **Business Brain** — פרופיל עסק (`/api/business/profile`), אימות קלט, שלמות פרופיל | test_business + דפדפן |
| 3 | **P1 CEO** (`app/business/ceo.py`, engine=rules): בריאות עסק לפי תחומים (ציון כולל רק כשיש ≥3 תחומים מדודים), תוכנית צמיחה, **3 הפעולות הבאות**, הוכחת ערך, ציר זמן, דוח שבועי | test_business |
| 3 | סיכום מנהלים ע"י מודל — רק כשמנוע אמיתי פעיל (`/api/business/brief`), אחרת `not_configured` | בדיקה עם מנוע מדומה |
| 4 | **Human Approval Center** (`app/business/actions.py`): run_audit · verify_fix · enable_monitor · fix_package. כל פעולה: "מה ישתנה" + סיכון → אישור → ביצוע | test_business + דפדפן |
| 4 | לולאת תיקון סגורה: חבילת תיקון להורדה → "סימנתי שיושם" → בדיקה חוזרת שמודדת מה נעלם | test_business |
| 6 | UI: מרכז פיקוד (בית), פרופיל עסק, אישורים, ציר צמיחה. סקירת האתר עברה ל-`#/site` | Playwright מחשב + iPhone, בלי גלילה אופקית |
| 6 | **PWA**: manifest, אייקונים, service worker (מעטפת בלבד — API לא נשמר במטמון), מסך "אין חיבור", הסבר התקנה באייפון | Playwright: SW נרשם, מסך offline |
| 6 | **אתר שיווקי** `/welcome`: צילומי מסך אמיתיים, "עובד / עוד לא", מחשבון חיסכון שקוף, מסלולים מהמגבלות האמיתיות (בלי מחירים מומצאים), FAQ | test + Playwright |
| 5 | **תשלומים**: ממשק ספק + Paddle (Stripe לא תומך בעסקים מישראל). webhook חתום, הגנת שידור חוזר, אידמפוטנטיות | test_billing (מוק בלבד) |
| 5 | **שחזור סיסמה**: אסימון חד-פעמי, ביטול סשנים, SMTP או קישור ממנהל | test_billing + דפדפן |
| 7 | Dockerfile + .dockerignore | **לא נבנה** — אין Docker daemon בסביבה |

סה"כ בדיקות אוטומטיות: ראו `python -m pytest -q` (כולל דפדפן אמיתי).

## מה עדיין לא קיים (ולא מוצג כקיים)
- מודל שפה פעיל (חסר מפתח / Ollama) · אחסון באוויר · Paddle אמיתי · SMTP אמיתי — ראו `REQUIREMENTS.md`.
- Website Builder, Marketing Studio, Competitor Research, Sales/Leads, Customer Support, Profit Doctor, Integrations (Shopify/GA/WhatsApp), צוותים והרשאות מרובות משתמשים בחשבון, אימות מייל.
- ModelBrain לסוכנים (היום rules), אימות בעלות אוטומטי (meta/DNS).

## הצעדים הבאים לפי סדר
1. אישור המשתמש לאחסון (Hugging Face Spaces חינמי) → בניית Docker ופריסה → קישור HTTPS לטלפון.
2. בדיקה על 3 אתרים אמיתיים באישור הבעלים (מחוץ לסביבת הענן החסומה).
3. בדיקת טפסי לידים / כפתור וואטסאפ בדפי נחיתה (ICP: סוכנויות שיווק ועסקים שמקבלים פניות).
4. התראות לוואטסאפ/מייל על תקלות חדשות.
5. חיבור מנוע מודל (אחרי אישור עלות) → ModelBrain לסוכנים + סיכומים.
6. צוותים והרשאות, אימות מייל, Postgres + worker נפרד.
