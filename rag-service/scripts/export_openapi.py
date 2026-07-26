import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("GEMINI_MODEL", "contract-model")
os.environ.setdefault("SPRING_BOOT_INTERNAL_API_KEY", "contract-secret")

from app.main import create_app


def main() -> int:
    target = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(create_app().openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
