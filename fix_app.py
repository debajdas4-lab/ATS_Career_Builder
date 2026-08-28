"""
Permanently remove garbled (mojibake) characters from app.py - SAFE v3.

Run from the project root (the folder that contains app.py):
    python fix_app.py

Why v3 is bulletproof:
- It uses str.splitlines(), which natively treats U+2028, U+2029 and U+0085
  as line boundaries, then rejoins with normal "\\n". This GUARANTEES line
  breaks are preserved (no merged statements), which is what broke v1/v2.
- Then, per line, it converts Unicode spaces to a normal space, removes the
  corrupted page_icon argument, and strips any remaining non-ASCII (mojibake
  emojis/symbols). Your app.py has no legitimate non-ASCII text, so this is
  safe and idempotent.

Also:
- Backs up app.py -> app_before_fix.py
- Keeps all labels intact (only icons/garbage are removed)
- Guarantees line count never decreases
- Compile-checks the result and tells you how to restore if needed
"""
import re
import shutil
from pathlib import Path

APP = Path("app.py")
if not APP.exists():
    raise SystemExit("ERROR: app.py not found here. cd into the folder that has app.py, then rerun.")

original_text = APP.read_text(encoding="utf-8", errors="replace")

# 1) Split on ALL line boundaries (including U+2028/U+2029/U+0085) -> rejoin with \n.
lines = original_text.splitlines()

SPACE_LIKE = {
    "\u00a0", "\u2007", "\u202f", "\u200b", "\u200c", "\u200d", "\ufeff",
    "\u2000", "\u2001", "\u2002", "\u2003", "\u2004", "\u2005", "\u2006",
    "\u2008", "\u2009", "\u200a",
}

cleaned_lines = []
for line in lines:
    # a) Unicode spaces -> normal space
    for sp in SPACE_LIKE:
        if sp in line:
            line = line.replace(sp, " ")
    # b) ellipsis mojibake -> '...'
    for ell in ("\u00e2\u20ac\u00a6", "\u00e2\u201a\u00ac\u00a6", "\u2026"):
        if ell in line:
            line = line.replace(ell, "...")
    # c) remove corrupted page_icon argument
    line = re.sub(r',\s*page_icon\s*=\s*"[^"]*"', "", line)
    line = re.sub(r'page_icon\s*=\s*"[^"]*"\s*,\s*', "", line)
    # d) strip any remaining non-ASCII (mojibake emojis/symbols)
    line = "".join(ch for ch in line if ord(ch) < 128)
    cleaned_lines.append(line)

new_text = "\n".join(cleaned_lines)
if original_text.endswith("\n"):
    new_text += "\n"

# 2) Tidy label spacing where an icon was removed.
#    IMPORTANT: use [ \t] (spaces/tabs only) - never \s, which would match
#    newlines and merge adjacent lines.
new_text = new_text.replace('f"{icon} {label}"', 'f"{icon} {label}".strip()')
new_text = re.sub(r'st\.button\(\s*"[ \t]+', 'st.button("', new_text)
new_text = re.sub(r'"[ \t]{2,}([A-Za-z])', r'"\1', new_text)

# 3) Safety: line count must never decrease.
if new_text.count("\n") < original_text.count("\n"):
    raise SystemExit(
        "ABORTED: line count would decrease. No changes written. "
        "Please share app.py so it can be inspected."
    )

if new_text == original_text:
    print("Nothing to change - app.py is already clean.")
else:
    shutil.copy2(APP, "app_before_fix.py")
    APP.write_text(new_text, encoding="utf-8")
    print("Cleaned app.py and saved as UTF-8.")
    print("Backup written to: app_before_fix.py")

import py_compile
try:
    py_compile.compile(str(APP), doraise=True)
    print("Compile check: OK")
except Exception as exc:
    print(f"Compile check FAILED: {exc}")
    print("Restore with:  Copy-Item app_before_fix.py app.py -Force")
