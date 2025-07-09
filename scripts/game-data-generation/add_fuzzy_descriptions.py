"""Utility: ensure every agent entry has a `fuzzy_description` key.

Run:
    python -m scripts.add_fuzzy_descriptions

• Reads data/sample_agents.json.
• For each agent dict, if "fuzzy_description" is missing, it adds it with an
  empty string value "".
• Writes the updated JSON back (pretty-printed, 2-space indent).
• Creates a timestamped backup of the original file alongside it.

Remove this helper when you're done.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_FILE = PROJECT_ROOT / "data" / "sample_agents.json"


def main() -> None:
    print(f"Loading {AGENT_FILE.relative_to(PROJECT_ROOT)} …")
    data = json.loads(AGENT_FILE.read_text())

    agents = data.get("agents", [])
    updated = False
    for agent in agents:
        if "fuzzy_description" not in agent:
            agent["fuzzy_description"] = ""
            updated = True

    if not updated:
        print("✅ All agents already have fuzzy_description. No changes made.")
        return

    # Backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = AGENT_FILE.with_suffix(f".backup_{ts}.json")
    backup_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"📦 Backup written to {backup_path.name}")

    # Write updated file (pretty print, 2-space indent)
    AGENT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print("💾 sample_agents.json updated with empty fuzzy_description fields where needed.")


if __name__ == "__main__":
    main() 