"""Generate additional message/alias pairs and append to message_alias_pool.json.

Examples:
    # Dry-run, show 3 generated pairs without saving
    python -m scripts.generate_message_alias_pool --add 3 --dry-run

    # Actually append 50 new pairs
    python -m scripts.generate_message_alias_pool --add 50

Requires OPENAI_API_KEY and uses GPT-4o.
"""
from __future__ import annotations

import argparse
import json
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv
import openai

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POOL_FILE = PROJECT_ROOT / "data" / "message_alias_pool.json"

load_dotenv()
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# Few-shot examples for the model
FEWSHOT = (
    "You are creating quirky message/alias pairs for an inbox-arena game. "
    "Each pair is JSON with keys 'message' and 'alias'. "
    "Rules:\n"
    "1. Message is a whimsical single-sentence statement.\n"
    "2. Alias is a third-person description of the agent that *refers* to the message without re-using the same wording, and begins with 'The agent who mentioned'.\n"
    "Return ONLY the JSON object.\n\n"
    "Example 1:\n"
    "{\n  \"message\": \"The dancing penguins have arrived at the ice cream parlor!\",\n  \"alias\": \"The agent who mentioned waddling arctic birds visiting a frozen dessert establishment\"\n}\n\n"
    "Example 2:\n"
    "{\n  \"message\": \"My pet cactus just learned how to play the harmonica.\",\n  \"alias\": \"The agent who mentioned a spiky desert plant mastering a small wind instrument\"\n}\n\n"
    "Now produce ONE new pair in the same JSON format."
)


def openai_client() -> openai.OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY env var not set.")
    return openai.OpenAI(api_key=api_key)  # type: ignore[attr-defined]


def generate_pair(client: openai.OpenAI) -> Dict[str, str]:
    """Call GPT to get a single pair."""
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": FEWSHOT},
        ],
        temperature=0.9,
        max_tokens=120,
    )
    content = resp.choices[0].message.content.strip()

    # Ensure we have valid JSON – try to locate first { ... }
    first_brace = content.find('{')
    last_brace = content.rfind('}')
    if first_brace == -1 or last_brace == -1:
        raise ValueError("OpenAI response did not contain JSON object:", content)
    json_str = content[first_brace:last_brace+1]
    data: Dict[str, Any] = json.loads(json_str)
    message = data.get("message", "").strip()
    alias = data.get("alias", "").strip()
    if not message or not alias:
        raise ValueError("Parsed message/alias missing: ", data)
    return {"message": message, "alias": alias}


def load_pool() -> Dict[str, Any]:
    if POOL_FILE.exists():
        return json.loads(POOL_FILE.read_text())
    return {"pairs": []}


def save_pool(pool: Dict[str, Any]):
    POOL_FILE.write_text(json.dumps(pool, indent=2, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Generate new message/alias pairs via OpenAI")
    parser.add_argument("--add", type=int, default=1, help="Number of pairs to generate")
    parser.add_argument("--dry-run", action="store_true", help="Only print pairs, do not save")
    args = parser.parse_args()

    n = args.add
    client = openai_client()

    new_pairs = []
    for _ in range(n):
        pair = generate_pair(client)
        new_pairs.append(pair)

    # Display for user review
    print("Generated pairs:\n")
    for p in new_pairs:
        print("-", p["message"])
        print("  ", p["alias"])
        print()

    if args.dry_run:
        print("Dry-run: exiting without modifying pool file.")
        return

    # Load existing pool, find current max id
    pool = load_pool()
    existing_pairs = pool.get("pairs", [])
    max_id = max((p.get("id", 0) for p in existing_pairs), default=0)

    # Assign incremental ids and append
    for idx, p in enumerate(new_pairs, max_id + 1):
        p["id"] = idx
        existing_pairs.append(p)

    pool["pairs"] = existing_pairs

    # Backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = POOL_FILE.with_suffix(f".backup_{ts}.json")
    backup.write_text(json.dumps(pool, indent=2, ensure_ascii=False))

    save_pool(pool)
    print(f"\nSaved {n} new pairs to pool (backup: {backup.name}). Total now: {len(existing_pairs)}")


if __name__ == "__main__":
    main() 