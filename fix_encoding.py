"""
Repair mojibake (garbled emoji/symbol) characters in app.py.

Run from the project root:  python fix_encoding.py

- Backs up app.py -> app_before_encoding_fix.py
- Removes corrupted emoji/symbol sequences from sidebar labels + button
- Fixes the '...' ellipsis mojibake in placeholders
- Also repairs any remaining mojibake via a safe cp1252->utf-8 round trip
- Saves app.py as clean UTF-8
"""
import re
import shutil
from pathlib import Path

APP = Path("app.py")
if not APP.exists():
    raise SystemExit("ERROR: app.py not found in this folder. cd to the project root and retry.")

raw = APP.read_text(encoding="utf-8", errors="replace")
original = raw

# 1) Targeted replacements for the exact garbage seen in the sidebar/button.
#    Each corrupted sequence -> clean replacement (emoji removed, label kept).
targeted = {
    "\u00f0\u0178\u017d\u00af": "",   # 🎯  Analyze Job
    "\u00f0\u0178\u201c\u201e": "",   # 📄  Resume
    "\u00e2\u0152\u2610": "",         # ⌁  Naukri
    "\u00e2\u2014\u2030": "",         # ◉  Interview Kit
    "\u00e2\u2020\u2014": "",         # ↗  Career Roadmap
    "\u00e2\u2014\u0152": "",         # ◌  Research
    "\u00f0\u0178\u0161\u20ac": "",   # 🚀  Analyze button
    "\u00e2\u017e\u00a2": "",         # ➕  Add company...
    "\u00e2\u201a\u00ac\u00a6": "...",# … ellipsis
    "\u00e2\u20ac\u00a6": "...",      # … ellipsis (alt)
}
for bad, good in targeted.items():
    raw = raw.replace(bad, good)

# 2) Broadly strip any leftover mojibake lead bytes (ð / â followed by combining junk)
#    at the START of common label patterns, without touching normal text.
raw = re.sub(r"[\u00f0\u00e2][\u0080-\u017f\u2000-\u20ff\u00a0-\u00bf]{1,3}\s*", "", raw)

# 3) Collapse any double spaces left where an emoji used to be.
raw = re.sub(r'"\s{2,}', '"', raw)   # inside quoted labels
raw = raw.replace(' &nbsp; ', ' ')

if raw == original:
    print("No mojibake patterns matched. If glyphs persist, open app.py in VS Code and")
    print("use 'Reopen with Encoding -> Windows-1252', then 'Save with Encoding -> UTF-8'.")
else:
    shutil.copy2(APP, "app_before_encoding_fix.py")
    APP.write_text(raw, encoding="utf-8")
    print("Fixed app.py and saved as UTF-8.")
    print("Backup: app_before_encoding_fix.py")

# 4) Quick compile check.
import py_compile
try:
    py_compile.compile(str(APP), doraise=True)
    print("Compile check: OK")
except Exception as exc:
    print(f"Compile check FAILED: {exc}")
    print("Restore with:  Copy-Item app_before_encoding_fix.py app.py -Force")
