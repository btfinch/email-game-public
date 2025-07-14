#!/usr/bin/env python3
"""
Wrapper script that adds signal handling to agents for graceful shutdown.
This allows agents to save transcripts when terminated by runner.py.
"""

import asyncio
import signal
import sys
import os
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def create_signal_handler(agent, loop):
    """Create a signal handler that gracefully stops the agent."""
    shutdown_event = asyncio.Event()
    
    def handler(signum, frame):
        print(f"\n📡 Received signal {signum}, shutting down gracefully...")
        
        # Signal that we want to shutdown
        loop.call_soon_threadsafe(shutdown_event.set)
    
    return handler, shutdown_event


async def run_agent_with_signals(module_name: str, agent_id: str, username: str, server_url: str):
    """Run an agent with proper signal handling."""
    # Import the appropriate agent module
    if module_name == "src.base_agent":
        from src.base_agent import BaseAgent
        agent_class = BaseAgent
    elif module_name == "src.custom_base_agent":
        from src.custom_base_agent import CustomBaseAgent
        agent_class = CustomBaseAgent
    else:
        raise ValueError(f"Unknown module: {module_name}")
    
    # Create the agent
    agent = agent_class(agent_id, username, server_url)
    
    # Get the current event loop
    loop = asyncio.get_event_loop()
    
    # Set up signal handlers
    signal_handler, shutdown_event = create_signal_handler(agent, loop)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    print(f"🤖 Starting {agent_id} with signal handling enabled...")
    
    # Create tasks for both the agent and shutdown monitoring
    agent_task = asyncio.create_task(agent.run())
    shutdown_task = asyncio.create_task(shutdown_event.wait())
    
    try:
        # Wait for either the agent to finish or shutdown signal
        done, pending = await asyncio.wait(
            [agent_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # If shutdown was triggered, stop the agent
        if shutdown_task in done:
            print("📛 Shutdown signal received, stopping agent...")
            
            # Cancel the agent task if still running
            if agent_task in pending:
                agent_task.cancel()
                try:
                    await agent_task
                except asyncio.CancelledError:
                    pass
            
            # Stop the agent and save transcript
            print(f"💾 Saving transcript for {agent.agent_id}...")
            agent.stop()  # This should save the transcript (let the agent handle errors)
            
            # Disconnect gracefully
            await agent.disconnect_gracefully()
            print("✅ Agent shutdown complete")
            
    except asyncio.CancelledError:
        print("🛑 Agent task cancelled")
    except Exception as e:
        print(f"❌ Agent error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Ensure cleanup happens even if run() exits normally
        if getattr(agent, 'running', True):
            print(f"🧹 Final cleanup for {agent.agent_id}...")
            agent.stop()  # Let the agent handle transcript saving and errors
            await agent.disconnect_gracefully()


def main():
    """Main entry point."""
    if len(sys.argv) < 5:
        print("Usage: agent_wrapper.py <module_name> <agent_id> <username> <server_url>")
        sys.exit(1)
    
    module_name = sys.argv[1]
    agent_id = sys.argv[2]
    username = sys.argv[3]
    server_url = sys.argv[4]
    
    # Run the agent with signal handling
    try:
        asyncio.run(run_agent_with_signals(module_name, agent_id, username, server_url))
    except KeyboardInterrupt:
        print("\n⏹️  Agent interrupted")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()