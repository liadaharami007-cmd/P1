"""לוגים מובנים (JSON בשורה) — קל לחפש ולשלוח לכלי ניטור (Datadog / Grafana / Sentry) בהמשך."""
from __future__ import annotations

import json
import logging
import os
import sys
import time


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)), "level": record.levelname,
                "logger": record.name, "msg": record.getMessage()}
        for k in ("request_id", "path", "method", "status", "ms", "audit_id", "account_id", "user_id"):
            if hasattr(record, k):
                data[k] = getattr(record, k)
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


def setup() -> None:
    root = logging.getLogger("p1")
    if root.handlers:
        return
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonFormatter())
    root.addHandler(h)
    root.setLevel(os.environ.get("P1_LOG_LEVEL", "INFO"))
    root.propagate = False


log = logging.getLogger("p1")
