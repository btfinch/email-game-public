#!/usr/bin/env python3
"""
Local development server for testing agents quickly.
Automatically populates with base agents for easy testing.
"""

import asyncio
import sys
import subprocess
import time
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


async def start_dev_server(num_base_agents: int = 3, auto_start: bool = True):
    """Start a local server pre-populated with base agents.
    
    Args:
        num_base_agents: Number of base agents to create (1-3)
        auto_start: Whether to auto-start game when full
    """
    print("🚀 Starting Inbox Arena Development Server")
    print("=" * 50)
    
    # Start email server
    print("📧 Starting email server...")
    server_process = subprocess.Popen([
        sys.executable, "-m", "src.email_server"
    ], cwd=PROJECT_ROOT)
    
    # Wait for server to be ready
    await asyncio.sleep(3)
    
    # Start dashboard in background
    print("📊 Starting dashboard...")
    dashboard_process = subprocess.Popen([
        sys.executable, "-m", "src.dashboard"
    ], cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    print("✅ Services started:")
    print("   • Email Server: http://localhost:8000")
    print("   • Dashboard: http://localhost:8002")
    print("   • API Docs: http://localhost:8000/docs")
    
    # Populate with base agents
    base_agent_names = ["alice", "bob", "charlie"][:num_base_agents]
    base_agents = []
    
    if num_base_agents > 0:
        print(f"\n🤖 Starting {num_base_agents} base agents...")
        for agent_name in base_agent_names:
            process = populate_base_agent(agent_name)
            if process:
                base_agents.append((agent_name, process))
                await asyncio.sleep(1)
    
    print(f"\n🎮 Development server ready!")
    print(f"👥 {len(base_agents)} base agents in queue")
    print(f"🎯 Waiting for {4 - len(base_agents)} more agent(s) to start game")
    
    if auto_start:
        print("\n💡 Game will auto-start when 4 agents join the queue")
    
    print("\n📝 To join with your agent:")
    print("   python -m src.base_agent <agent_id> <username>")
    print("   OR")
    print("   arena join --agent-id <your_agent>")
    
    print("\n⏹️  Press Ctrl+C to stop the development server")
    
    try:
        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)
            
            # Check if processes are still running
            if server_process.poll() is not None:
                print("\n❌ Email server crashed!")
                break
                
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down development server...")
    
    # Cleanup
    print("🧹 Cleaning up processes...")
    
    # Stop base agents
    for agent_name, process in base_agents:
        process.terminate()
        print(f"   • Stopped {agent_name}")
    
    # Stop services
    dashboard_process.terminate()
    server_process.terminate()
    
    # Wait for processes to end
    await asyncio.sleep(1)
    
    print("✅ Development server stopped")


def populate_base_agent(agent_id: str):
    """Add a standard base agent to the queue."""
    try:
        process = subprocess.Popen([
            sys.executable, "-m", "src.base_agent",
            agent_id, agent_id.title()
        ], cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        print(f"   • Started {agent_id} (PID: {process.pid})")
        return process
        
    except Exception as e:
        print(f"   ❌ Failed to start {agent_id}: {e}")
        return None


async def main():
    """Run the development server with command line options."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Inbox Arena Development Server")
    parser.add_argument(
        "--agents", "-a", 
        type=int, 
        default=3, 
        choices=[0, 1, 2, 3],
        help="Number of base agents to start (0-3, default: 3)"
    )
    parser.add_argument(
        "--no-auto-start", 
        action="store_true",
        help="Don't auto-start game when queue is full"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8000,
        help="Email server port (default: 8000)"
    )
    
    args = parser.parse_args()
    
    # Check if OpenAI key is set
    if not os.getenv('OPENAI_API_KEY'):
        print("⚠️  Warning: OPENAI_API_KEY not set!")
        print("   Base agents will not function properly without it.")
        response = input("   Continue anyway? (y/N): ")
        if response.lower() != 'y':
            return
    
    # TODO: Support custom port
    if args.port != 8000:
        print("⚠️  Custom ports not yet supported, using 8000")
    
    await start_dev_server(
        num_base_agents=args.agents,
        auto_start=not args.no_auto_start
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  Interrupted")
        sys.exit(0)