"""Build the static live-demo site for GitHub Pages into ./site.

The site is the normal frontend plus the Python source of app/, which the
browser runs with Pyodide (see app/browser.py and web/pyodide-backend.js).
Usage: python scripts/build_site.py
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

shutil.rmtree(SITE, ignore_errors=True)
(SITE / "static").mkdir(parents=True)
for f in (ROOT / "frontend").iterdir():
    if f.name != "index.html":
        shutil.copy(f, SITE / "static" / f.name)
shutil.copy(ROOT / "web" / "pyodide-backend.js", SITE / "static" / "pyodide-backend.js")

html = (ROOT / "frontend" / "index.html").read_text()
html = html.replace('<script src="static/app.js"></script>',
                    '<script src="static/pyodide-backend.js"></script>\n  <script src="static/app.js"></script>')
(SITE / "index.html").write_text(html)

files = []
for py in sorted((ROOT / "app").rglob("*.py")):
    rel = py.relative_to(ROOT).as_posix()
    dest = SITE / "py" / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(py, dest)
    files.append(rel)
(SITE / "py" / "manifest.json").write_text(json.dumps(files))
(SITE / ".nojekyll").write_text("")
print(f"Built {SITE} with {len(files)} Python files")
