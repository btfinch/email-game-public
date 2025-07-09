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
