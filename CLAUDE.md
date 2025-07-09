# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Set up OpenAI API key
export OPENAI_API_KEY="sk-..."

# Set JWT secret for production (use a strong random key)
export JWT_SECRET="your-secure-jwt-secret-here"
```

### Running the System
```bash
# Start the email server (required first)
python -m src.email_server
# Alternative: uvicorn src.email_server:app --reload

# Start an agent in another terminal
python -m src.base_agent <agent_id> <username>

# Run live demo with multiple components
python -m scripts.live_agent_demo
```

### Web Interfaces
```bash
# Start the dashboard (monitors live game activity)
python -m src.dashboard
# Available at: http://localhost:8002

# Start the logs viewer (browse completed game sessions)
python scripts/start_logs_viewer.py
# Available at: http://localhost:8003
```

### Testing
```bash
# Run all tests
pytest

# Run specific test categories
pytest tests/1-email-server/
pytest tests/base_agents/

# Test individual components
python tests/test_llm_driver.py
python tests/test_moderator.py
```

## Architecture Overview

### Core Components

**Email Server (`src/email_server.py`)**
- FastAPI-based message routing system with WebSocket support
- Handles message storage, delivery tracking, and batch operations
- Includes request queuing for concurrent message handling
- REST endpoints for sending messages and WebSocket for real-time notifications

**Base Agent (`src/base_agent.py`)**
- LLM-powered agent that connects to email server via WebSocket
- Forwards incoming emails to GPT-4o with system prompt from `docs/agent_prompt.md`
- Executes `send_email` tool calls returned by the model
- Maintains connection state and message tracking

**LLM Driver (`src/llm_driver.py`)**
- Lightweight wrapper around OpenAI chat completion API
- Handles function calling for the `send_email` tool
- Supports GPT-4o model with configurable parameters

**Dashboard (`src/dashboard.py`)**
- Web-based real-time monitoring interface
- Shows live message activity and agent status
- Runs on port 8002

**Logs Viewer (`src/logs_viewer.py`)**
- Web interface for browsing completed game sessions
- Provides formatted view of session logs and message history
- Runs on port 8003

**Moderator (`src/moderator.py`)**
- Game coordination component for multi-agent scenarios
- Sends instructions and manages game state

### Agent Communication Flow

1. Agents connect to email server WebSocket for real-time message delivery
2. Incoming emails are forwarded to LLM with system prompt
3. LLM responds with natural language and/or `send_email` tool calls
4. Tool calls are executed via REST API to send messages to other agents

### System Prompt Location
The agent system prompt is stored in `docs/agent_prompt.md` and defines the game rules, email format, and agent behavior for The Email Game competition framework.

### Configuration
- Python 3.9+ required
- Dependencies managed via `requirements.txt`
- OpenAI API key required for LLM functionality
- pytest configuration in `pytest.ini`