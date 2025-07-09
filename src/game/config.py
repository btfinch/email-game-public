"""Configuration constants for the email game system"""

from pathlib import Path

# Get project root - from src/game/config.py, need to go up 2 levels to reach project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Game configuration
NUM_AGENTS = 4  # Number of agents to select for each game
NUM_ROUNDS = 1  # Number of rounds per session (default: 3)
REQUESTS_PER_AGENT = 2  # How many signatures each agent must request and can sign per round (must be < NUM_AGENTS)
ROUND_DURATION_SEC = 60  # Extended time for agent communication

# ------------------------------------------------------------------
# OpenAI model configuration
# ------------------------------------------------------------------
# Default LLM model used by all agents unless overridden at runtime.
# Using the lighter "gpt-4o-mini" variant greatly reduces cost while
# retaining strong reasoning performance.

OPENAI_MODEL = "gpt-4o"

KEEP_DASHBOARD_SEC = 20  # How long to keep servers alive after the session