# בניית ההדגמה הלחיצה (בלי שרת)

ההדגמה היא אותם מסכים של `app/static/pulse/`, עם צילום מצב של סביבת הדמו (`data.json`) ו-`snapshot.js` שמחליף את השרת:
קריאות מוגשות מהצילום, ופעולות על לקוחות ומשימות (התחלת טיפול, שיוך, אישור, התחייבויות, הערות, טיוטת עדכון) מבוצעות בזיכרון הדפדפן ומתאפסות ברענון.

```bash
. .venv/bin/activate
mkdir -p /tmp/pulse-demo && python clientpulse/demo-build/capture.py /tmp/pulse-demo/data.json
cp app/static/pulse/app.js app/static/pulse/views.js clientpulse/demo-build/snapshot.js clientpulse/demo-build/index.html /tmp/pulse-demo/
grep -v "^@font-face" app/static/pulse/pulse.css > /tmp/pulse-demo/pulse.css
```
אחר כך מפרסמים את התיקייה כ-Artifact (index.html + הקבצים לידו).
