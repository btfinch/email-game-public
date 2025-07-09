#!/usr/bin/env python
"""CLI: run_agent.py

Quick launcher for the StarterAgent.  Example:

    python scripts/run_agent.py --agent-id alice --server http://localhost:8000
"""

import argparse
import sys
from inbox_arena.agent_starter import StarterAgent


def main():
    ap = argparse.ArgumentParser(description="Launch an Inbox-Arena starter agent")
    ap.add_argument("--agent-id", required=True)
    ap.add_argument("--server", default="http://localhost:8000")
    args = ap.parse_args()

    agent = StarterAgent(agent_id=args.agent_id, server_url=args.server)
    token = agent.register()
    pos = agent.join_queue()
    print(f"✅ Registered {args.agent_id}, JWT length={len(token)}")
    print(f"📥 Joined queue at position {pos}")


if __name__ == "__main__":
    sys.exit(main()) 