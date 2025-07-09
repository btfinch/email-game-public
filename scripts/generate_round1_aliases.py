"""Generate `round1_alias` values for agents using OpenAI.

Usage examples:
    # Dry-run on the first agent missing an alias
    python -m scripts.generate_round1_aliases --single-test

    # Fill aliases for every agent that has an empty round1_alias
    python -m scripts.generate_round1_aliases --apply-all

Environment:
    Requires OPENAI_API_KEY to be set.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from datetime import datetime
import random

import openai
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_FILE = PROJECT_ROOT / "data" / "sample_agents.json"

# Load environment variables from .env if present
load_dotenv()

# -------- OpenAI helper --------------------------------------------------

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# Few-shot prompt with examples to steer the model
PROMPT_TEMPLATE = (
    "You are given an agent's whimsical round-1 message. "
    "Rewrite it into a concise third-person alias that refers to the agent *without* reusing the same wording. "
    "Always start the alias with 'The agent who mentioned'. Keep it a single sentence.\n\n"
    "Examples (follow this style):\n"
    "Message: \"The dancing penguins have arrived at the ice cream parlor!\"\n"
    "Alias: The agent who mentioned waddling arctic birds visiting a frozen dessert establishment\n\n"
    "Message: \"My pet cactus just learned how to play the harmonica.\"\n"
    "Alias: The agent who mentioned a spiky desert plant mastering a small wind instrument\n\n"
    "Now generate an alias for the next message:\n\n"
    "Message: \"{msg}\"\n\n"
    "Alias:"
)

def generate_alias(message: str, client: openai.OpenAI | None = None) -> str:
    """Call OpenAI to create a round-1 alias from the given message."""
    if client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
        client = openai.OpenAI(api_key=api_key)  # type: ignore[attr-defined]

    prompt = PROMPT_TEMPLATE.format(msg=message)

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=40,
    )
    alias = resp.choices[0].message.content.strip().strip("\n")
    return alias

# -------- Main CLI -------------------------------------------------------

def load_agents():
    return json.loads(AGENT_FILE.read_text())


def save_agents(data):
    AGENT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def backup_file():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bkp = AGENT_FILE.with_suffix(f".backup_{ts}.json")
    bkp.write_text(AGENT_FILE.read_text())
    return bkp


def single_test() -> None:
    data = load_agents()
    agents = data.get("agents", [])
    if not agents:
        print("No agents found in JSON.")
        return

    agent = random.choice(agents)
    alias = generate_alias(agent["round1_message"])
    print(f"Randomly selected agent: {agent['id']}")
    print("Original message:", agent["round1_message"])
    print("Suggested alias :", alias)


def apply_all(confirm: bool = False) -> None:
    data = load_agents()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
    client = openai.OpenAI(api_key=api_key)  # type: ignore[attr-defined]

    agents = data.get("agents", [])

    to_update = [a for a in agents if not a.get("round1_alias")]
    if not to_update:
        print("Nothing to update – every agent already has an alias.")
        return

    print(f"Will generate aliases for {len(to_update)} agents.")
    if not confirm:
        proceed = input("Proceed and overwrite sample_agents.json? [y/N] ").lower().startswith("y")
        if not proceed:
            print("Aborted.")
            return

    backup = backup_file()
    print("Backup saved to", backup.name)

    for agent in to_update:
        alias = generate_alias(agent["round1_message"], client)
        agent["round1_alias"] = alias
        print(f"✓ {agent['id']} -> {alias}")

    save_agents(data)
    print("All aliases generated and saved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate round1_alias fields via OpenAI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--single-test", action="store_true", help="Print alias for first agent missing one")
    group.add_argument("--apply-all", action="store_true", help="Fill alias for every agent without one")

    args = parser.parse_args()

    if args.single_test:
        single_test()
    elif args.apply_all:
        apply_all() 