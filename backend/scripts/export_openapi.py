"""Write shared/openapi.yaml from the FastAPI app (COORDINATION.md section 3: generated files are committed).

Run from backend/:  python scripts/export_openapi.py      (add --check to fail if the file is stale)
"""

import sys
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

OUT = BACKEND.parent / "shared" / "openapi.yaml"


def render() -> str:
    # Placeholder settings: the schema does not depend on secrets or the DB.
    settings = Settings(app_secret="x" * 32, database_url="sqlite://", _env_file=None)
    spec = create_app(settings).openapi()
    return yaml.safe_dump(spec, sort_keys=False, allow_unicode=True)


if __name__ == "__main__":
    text = render()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            sys.exit("shared/openapi.yaml is stale: run python scripts/export_openapi.py")
        print("shared/openapi.yaml is up to date")
    else:
        OUT.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {OUT}")
