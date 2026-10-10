"""Load the seed agent registry (backend/agents/seed/*.json) with prompts resolved.

Agents are data (D-005): this loader only reads and checks the seed files; the
DB seeding script inserts them as `agents` and `agent_versions` rows.
"""

from __future__ import annotations

import json
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = AGENTS_DIR.parent.parent
SCHEMAS_DIR = REPO_ROOT / "shared" / "schemas"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_tool_registry() -> dict:
    return _read_json(AGENTS_DIR / "tool_registry.json")["tools"]


def load_model_tiers() -> dict:
    return _read_json(AGENTS_DIR / "models.json")["tiers"]


def load_seed_agents() -> list[dict]:
    """Return seed records with `version.system_prompt` filled from the prompt file."""
    agents = []
    for path in sorted((AGENTS_DIR / "seed").glob("*.json")):
        record = _read_json(path)
        version = record["version"]
        version["system_prompt"] = (AGENTS_DIR / version["system_prompt_file"]).read_text(encoding="utf-8")
        agents.append(record)
    return agents


def load_output_schema(name: str) -> dict:
    return _read_json(SCHEMAS_DIR / name)


def council_judges(agents: list[dict]) -> list[dict]:
    return [a for a in agents if a["agent"]["role"] == "council_judge"]
