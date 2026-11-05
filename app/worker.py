"""הרצת worker בדיקות כתהליך נפרד (לייצור): python -m app.worker
בשרת ה-web יש להגדיר P1_RUN_WORKER=0 כדי שלא ירוץ worker כפול."""
import asyncio

from . import config
from .audit.runner import AuditRunner
from .db import Database
from .logging_setup import setup


async def main() -> None:
    setup()
    db = Database(config.DB_PATH)
    db.fail_stale_audits()
    await AuditRunner(db, allow_private=config.DEV_ALLOW_PRIVATE_TARGETS).worker()


if __name__ == "__main__":
    asyncio.run(main())
