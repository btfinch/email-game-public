"""Utility functions for the email game system"""

from typing import Dict, List
import json
import os

from .config import PROJECT_ROOT

# ---------------------------------------------------------------------------
# Queue management helper - now handled in-memory by email server
# ---------------------------------------------------------------------------


def load_agent_pool() -> List[Dict[str, str]]:
    """Load the pool of available agents from JSON file"""
    agents_file = PROJECT_ROOT / "data" / "sample_agents.json"
    with open(agents_file, 'r') as f:
        data = json.load(f)
    return data["agents"]


# ---------------------------------------------------------------------------
# Queue-based agent selection (replaces *select_random_agents*)
# ---------------------------------------------------------------------------


def select_queued_agents(num_agents: int, pop: bool = True) -> List[Dict[str, str]]:
    """Legacy function for backwards compatibility.
    
    Queue management is now handled in-memory by the email server.
    This function returns an empty list since the auto-start mechanism
    in email_server.py handles the queue directly.
    
    Args:
        num_agents: Number of agents to dequeue (ignored).
        pop: If *True* the selected IDs are atomically removed (ignored).
    """
    # Queue is now managed in-memory by email_server.py
    # This function exists for backwards compatibility but returns empty
    # since the real queue management happens in the email server auto-start
    return []


# ---------------------------------------------------------------------------
# Message-alias pool utilities (Step 2 of message_alias_pool_plan)
# ---------------------------------------------------------------------------


def load_message_alias_pool() -> List[Dict[str, str]]:
    """Load the shared pool of {id, message, alias} objects.

    Returns an empty list if the pool file does not yet exist.
    """
    pool_file = PROJECT_ROOT / "data" / "message_alias_pool.json"
    if not pool_file.exists():
        return []
    with pool_file.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("pairs", [])