"""בדיקות לצד הלקוח: בדיקת טיפוסים (TypeScript על JSDoc) ושלמות התרגומים."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "app" / "static" / "js"


@pytest.mark.skipif(not (ROOT / "node_modules" / ".bin" / "tsc").exists() or not shutil.which("node"),
                    reason="typescript לא מותקן (npm install)")
def test_typescript_typecheck():
    r = subprocess.run([str(ROOT / "node_modules" / ".bin" / "tsc"), "-p", "tsconfig.json"], cwd=ROOT,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_translation_key_exists_in_both_languages():
    src = (JS / "i18n.js").read_text(encoding="utf-8")
    he_block = src[src.index("he: {"):src.index("en: {")]
    en_block = src[src.index("en: {"):src.index("const STORE_KEY")]
    key_re = re.compile(r'"([a-zA-Z0-9_.]+)":')
    he, en = set(key_re.findall(he_block)), set(key_re.findall(en_block))
    assert he == en, {"missing_in_en": sorted(he - en), "missing_in_he": sorted(en - he)}
    # מילון Business OS (i18n-biz.js) — אותה בדיקה
    biz = (JS / "i18n-biz.js").read_text(encoding="utf-8")
    bhe, ben = set(key_re.findall(biz[biz.index("he: {"):biz.index("en: {")])), set(key_re.findall(biz[biz.index("en: {"):]))
    assert bhe == ben, {"biz_missing_in_en": sorted(bhe - ben), "biz_missing_in_he": sorted(ben - bhe)}
    he, en = he | bhe, en | ben
    # כל מפתח סטטי שבשימוש בקוד קיים במילון
    used = set()
    for f in JS.rglob("*.js"):
        used |= set(re.findall(r'(?<![\w.$])t\("([a-zA-Z0-9_.]+)"', f.read_text(encoding="utf-8")))
    missing = sorted(k for k in used if k not in he and not k.endswith("."))
    assert not missing, missing
