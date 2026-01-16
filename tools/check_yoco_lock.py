import hashlib
import re
import sys
from pathlib import Path

APP = Path("app.py")
LOCK = Path("tools/yoco_lock.hash")

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def extract_yoco_block(src: str) -> str:
    config_lines = []
    for line in src.splitlines():
        if re.match(r"^\s*(YOCO_|PUBLIC_URL|YOCO_CHECKOUT_URL)\b", line):
            config_lines.append(line.rstrip())

    pattern = r'@app\.route\(\s*["\']\/pay\/yoco\/start["\'].*?\)\s*\n\s*def\s+yoco_start\s*\(.*?\):\s*\n(?:(?:.|\n)*?)(?=\n@app\.route|\Z)'
    m = re.search(pattern, src, flags=re.MULTILINE)
    if not m:
        raise RuntimeError("Could not find the /pay/yoco/start route in app.py")

    locked = "\n".join(config_lines).strip() + "\n\n" + m.group(0).strip()
    return locked

def main():
    if not APP.exists():
        print("ERROR: app.py not found")
        sys.exit(2)

    src = APP.read_text(encoding="utf-8")
    digest = sha256(extract_yoco_block(src))

    if not LOCK.exists():
        LOCK.write_text(digest, encoding="utf-8")
        print("YOCO LOCK CREATED ✅")
        sys.exit(0)

    if LOCK.read_text().strip() != digest:
        print("YOCO LOCK FAILED ❌")
        sys.exit(1)

    print("YOCO LOCK OK ✅")

if __name__ == "__main__":
    main()
