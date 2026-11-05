"""הגדרות המערכת — נקראות ממשתני סביבה (או מקובץ .env)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """טעינה פשוטה של קובץ .env (בלי ספרייה חיצונית). משתני סביבה קיימים גוברים."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

MODEL = os.environ.get("P1_MODEL", "claude-opus-5-5")
DB_PATH = Path(os.environ.get("P1_DB_PATH", ROOT / "data" / "p1.db"))
MAX_AGENT_STEPS = int(os.environ.get("P1_MAX_AGENT_STEPS", "8"))


def anthropic_configured() -> bool:
    """האם יש מפתח/אסימון לחיבור ל-Claude."""
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
