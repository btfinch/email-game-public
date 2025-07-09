"""Add sequential `id` field to each pair in data/message_alias_pool.json.

Run:
    python -m scripts.add_ids_to_alias_pool
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POOL_FILE = PROJECT_ROOT / "data" / "message_alias_pool.json"


def main() -> None:
    pool_data = json.loads(POOL_FILE.read_text())
    pairs = pool_data.get("pairs", [])

    # Assign IDs starting at 1
    for idx, pair in enumerate(pairs, 1):
        pair["id"] = idx

    # backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = POOL_FILE.with_suffix(f".backup_{ts}.json")
    backup.write_text(json.dumps(pool_data, indent=2, ensure_ascii=False))

    POOL_FILE.write_text(json.dumps(pool_data, indent=2, ensure_ascii=False) + "\n")
    print(f"Added id field to {len(pairs)} pairs. Backup saved as {backup.name}")


if __name__ == "__main__":
    main() 