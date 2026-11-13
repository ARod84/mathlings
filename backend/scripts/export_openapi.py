"""Writes the API's OpenAPI document to openapi.json at the repo root.

    uv run python scripts/export_openapi.py

The frontend will generate its typed client from that file. Run this after
changing a route or a response model, and commit the result. No database is
needed: the document is built from the route definitions alone.
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.main import create_app  # noqa: E402

OUTPUT = BACKEND_DIR.parent / "openapi.json"


def main() -> None:
    document = create_app().openapi()
    OUTPUT.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {len(document['paths'])} paths to {OUTPUT}")


if __name__ == "__main__":
    main()
