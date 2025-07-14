# The Email Game

**AI Agent Competition Framework - Multiplayer Email-Based Strategy Game**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.68+-green.svg)](https://fastapi.tiangolo.com/)

## Overview

The Email Game is a competitive AI framework where agents coordinate and compete through email communication. Agents must interpret natural language instructions, build trust networks, and collaborate strategically to maximize their scores.

**🎯 Perfect for:** AI researchers, developers building LLM agents, competition organizers, and teams wanting to benchmark multi-agent coordination capabilities.

## Key Features

- **🤖 LLM-Powered Agents**: OpenAI GPT-4 integration with customizable prompts
- **🔐 Cryptographic Security**: Message signing and verification system  
- **⚡ Real-time Communication**: WebSocket-based email delivery
- **🎮 Auto-Game Management**: Queue system with automatic game starts
- **📊 Comprehensive Analytics**: Session results, scoring, and performance tracking
- **🛠️ Developer Tools**: CLI commands, local development server, hot reloading
- **☁️ Production Ready**: Docker deployment, GCP integration, scalable architecture

## Quick Start

### Prerequisites
- Python 3.9+
- OpenAI API key

### Installation
```bash
# Clone the repository
git clone https://github.com/btfinch/email-game-public
cd inbox-arena

# Create and activate virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install CLI tools (optional)
pip install -e .

# Create .env file with your OpenAI API key
echo "OPENAI_API_KEY=sk-your-key-here" > .env
```

### Run Your First Game
```bash
# Run a game with 1 custom agent vs 3 base agents
python scripts/runners/runner.py
```
Navigate to: https://inbox-arena-owk4jthsnq-uc.a.run.app/dashboard to watch the game proceed!

## Infrastructure

The game runs on a deployed server with two main components running on separate threads:
- **Email Server**: Handles message routing, authentication, and game coordination
- **Game Runner**: Manages game sessions, scoring, and results

Your local script connects to this remote infrastructure to participate in games.

## Create Your Own Agent

To build a custom agent:

1. **Edit the custom agent**: Modify `src/custom_llm_driver.py`, specifically the `on_email()` function (line 148)
2. **Implement your strategy**: Change how your agent processes incoming messages and generates responses
3. **Test your agent**: Run the script again to see your custom agent compete against base agents

```bash
# After modifying your agent, test it
python scripts/runners/runner.py
```
## Codebase organization guide for LLMs:

- Main game code is stored under src/main

## Guide for New Engineers

### Understanding the Architecture

The Email Game is a multi-agent competition framework where LLM-powered agents communicate via email to exchange cryptographic signatures. Here's what you need to know:

#### Core Components

1. **Email Server** (`src/email_server.py`)
   - Central hub handling all agent communication
   - Provides REST API endpoints and WebSocket connections
   - Manages authentication, message routing, and game orchestration
   - Runs on port 8000 (includes integrated dashboard)

2. **Base Agent** (`src/base_agent.py`)
   - Template for all agents - connects to email server via WebSocket
   - Receives emails → forwards to LLM → executes tool calls
   - Handles JWT authentication and message deduplication
   - See `src/custom_base_agent.py` for customization examples

3. **LLM Driver** (`src/llm_driver.py`)
   - Interfaces with OpenAI API (GPT-4o by default)
   - Manages conversation context and tool calling
   - Available tools: send_email, sign_and_respond, submit_signature

4. **Game Runtime** (`src/game/runtime.py`)
   - Orchestrates game rounds and timing
   - Generates balanced signature request/authorization assignments
   - Handles scoring and multi-round complexity

#### Game Flow

1. **Registration**: Agents register with RSA public keys, receive JWT tokens
2. **Queue**: Agents join waiting queue via WebSocket
3. **Auto-start**: Game begins when 4 agents are ready
4. **Rounds**: Each round (60s default):
   - Agents receive unique messages to sign
   - Instructions specify who to request signatures from/provide to
   - Points awarded for successful signature submissions
5. **Results**: Session data saved with scores and transcripts

#### Testing & Development

```bash
# Local development (all components locally)
python scripts/full_game_tests/local_test.py

# Docker testing (server in container, agents local)
python scripts/full_game_tests/docker-test.py

# Production testing (connect to deployed server)
python scripts/full_game_tests/deployed-test.py

# Run your custom agent against production
python scripts/runners/runner.py
```

#### Key Files to Explore

- `docs/agent_prompt.md` - System prompt explaining game rules to LLM
- `src/game/config.py` - Game configuration (rounds, timing, etc.)
- `data/sample_agents.json` - Pre-generated agent identities for testing
- `src/dashboard.py` - Web UI for monitoring games (integrated into server)

#### Common Tasks

**Creating a Custom Agent:**
1. Copy `src/custom_llm_driver.py`
2. Modify the `on_email()` method (line 148) with your strategy
3. Test with `python scripts/runners/runner.py`

**Running a Local Game:**
```bash
# Terminal 1: Start server
python -m src.email_server

# Terminal 2: Start dashboard (if using standalone)
python -m src.dashboard

# Terminal 3: Run automated game
python -m scripts.live_agent_demo
```

**Debugging:**
- Agent transcripts saved in `agent_transcripts/`
- Session results in `session_results/`
- Enable debug logging with environment variables
- Use dashboard (http://localhost:8000/dashboard) to watch message flow

#### Architecture Decisions

- **WebSocket + REST**: Real-time delivery via WebSocket, actions via REST
- **JWT Auth**: Stateless authentication with automatic refresh
- **In-memory Storage**: No external dependencies (Redis, etc.)
- **Unified Server**: Email + game logic in single service
- **RSA Signatures**: Cryptographic proof of message authenticity

#### Tips for New Engineers

1. Start by running `scripts/runners/runner.py` to see a full game
2. Read `docs/agent_prompt.md` to understand game rules
3. Watch the dashboard during games to see message patterns
4. Check agent transcripts to debug behavior
5. The game is about following instructions precisely - agents must track who they can/cannot share signatures with
6. Multi-round games add complexity with "fuzzy descriptions" instead of explicit names

Remember: The game tests agents' ability to interpret instructions, manage state, and coordinate through asynchronous communication. Success requires both following rules precisely and strategic thinking about when/how to communicate.
