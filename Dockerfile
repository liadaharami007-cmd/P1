# P1 AI — תמונת ייצור. הערה: נכתב לפי הנוהל המקובל אך עוד לא נבנה בסביבת הפיתוח (אין שם Docker daemon).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    P1_DATA_DIR=/data P1_DB_PATH=/data/p1.db P1_COOKIE_SECURE=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt && python -m playwright install --with-deps chromium \
    && useradd --create-home --uid 10001 p1 && mkdir -p /data && chown p1:p1 /data

COPY app ./app
USER p1
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
# PORT מוגדר ע"י רוב פלטפורמות האחסון (Hugging Face: 7860, Render: משתנה)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
