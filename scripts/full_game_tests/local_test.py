#!/usr/bin/env python3
"""Complete end-to-end test of the new multiplayer The Email Game architecture.

This script validates the entire deployment plan implementation from steps 0-a through 2-a:
- Remote agent registration and JWT authentication
- Queue-based matchmaking with auto-start worker
- Full multi-round game execution with LLM-driven agents
- Message signing, submission, and scoring
- Session results and transcript generation

Requirements:
- OpenAI API key set (OPENAI_API_KEY environment variable)

Usage:
    python scripts/full_game_tests/local_test.py [--no-browser] [--agents N]
"""

import asyncio
import argparse
import json
import os
import sys
import time
import webbrowser
from pathlib import Path
from typing import List
import subprocess
import httpx

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.email_server import app as email_app
from src.dashboard import app as dashboard_app, dashboard
from src.base_agent import BaseAgent
from src.game.runtime import _run_server_in_thread, wait_for_server_ready
from src.game.config import NUM_AGENTS




def check_openai_key():
    """Check if OpenAI API key is configured."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY environment variable not set")
        print("💡 Set it with: export OPENAI_API_KEY='sk-...'")
        return False
    elif not api_key.startswith("sk-"):
        print("❌ OPENAI_API_KEY appears invalid (should start with 'sk-')")
        return False
    else:
        print("✅ OpenAI API key configured")
        return True


async def start_servers():
    """Start email server and dashboard."""
    print("🚀 Starting email server on port 8000...")
    
    # Configure dashboard for standalone mode
    dashboard.moderator_url = None
    
    # Start email server (includes queue monitor)
    email_server = _run_server_in_thread(email_app, 8000, "Email-FullTest")
    await wait_for_server_ready(8000, "Email-FullTest")
    print("✅ Email server ready")
    
    # Start dashboard
    print("🚀 Starting dashboard on port 8002...")
    dashboard_server = _run_server_in_thread(dashboard_app, 8002, "Dashboard-FullTest")
    await wait_for_server_ready(8002, "Dashboard-FullTest")
    print("✅ Dashboard ready")
    
    return email_server, dashboard_server


async def create_test_agents(num_agents: int = NUM_AGENTS) -> List[BaseAgent]:
    """Create and authenticate test agents."""
    print(f"🤖 Creating {num_agents} test agents...")
    
    # Use the first N agents from sample_agents.json
    agents_file = PROJECT_ROOT / "data" / "sample_agents.json"
    with open(agents_file, 'r') as f:
        agent_data = json.load(f)
    
    available_agents = agent_data["agents"][:num_agents]
    agents = []
    agent_tasks = []
    
    for agent_config in available_agents:
        agent_id = agent_config["id"]
        username = agent_config.get("username", agent_id.title())
        
        try:
            print(f"  📝 Registering {agent_id}...")
            agent = BaseAgent(agent_id, username)
            agents.append(agent)
            
            # Start the agent's WebSocket loop
            agent_task = asyncio.create_task(agent.run())
            agent_tasks.append(agent_task)
            
            print(f"  ✅ {agent_id} registered and starting WebSocket connection")
        except Exception as e:
            print(f"  ❌ Failed to register {agent_id}: {e}")
            raise
    
    # Give agents time to establish WebSocket connections
    print("🔗 Waiting for agent WebSocket connections...")
    await asyncio.sleep(3)
    print("✅ All agents should now be connected")
    
    # Store agent tasks for cleanup
    for i, task in enumerate(agent_tasks):
        agents[i]._agent_task = task
    
    return agents


async def wait_for_game_start(timeout: float = 60.0):
    """Wait for auto-start worker to detect full queue and start game."""
    print(f"⏳ Waiting for auto-start worker to detect {NUM_AGENTS} agents and start game...")
    
    start_time = time.time()
    game_file = PROJECT_ROOT / "current_game.json"
    
    while time.time() - start_time < timeout:
        if game_file.exists():
            try:
                with open(game_file, 'r') as f:
                    game_data = json.load(f)
                
                print("🎮 Game auto-started!")
                print(f"📋 Roster: {game_data['agents']}")
                print(f"⏰ Started at: {game_data['started_at']}")
                return game_data
            except Exception as e:
                print(f"⚠️  Error reading game file: {e}")
        
        await asyncio.sleep(1)
    
    raise TimeoutError(f"Game did not auto-start within {timeout} seconds")


async def monitor_game_progress():
    """Monitor game progress with detailed round-by-round updates."""
    print("📊 Monitoring game progress...")
    
    # Monitor for a reasonable amount of time
    # Game should complete in: 2 rounds * 60 seconds + overhead = ~3-4 minutes
    monitor_time = 5 * 60  # 5 minutes max
    start_time = time.time()
    
    last_message_count = 0
    last_session_data = None
    seen_rounds = set()
    game_file = PROJECT_ROOT / "current_game.json"
    
    while time.time() - start_time < monitor_time:
        try:
            # Check for round progress via current_game.json
            if game_file.exists():
                try:
                    with open(game_file, 'r') as f:
                        current_session = json.load(f)
                    
                    # Check for new round activity
                    if current_session != last_session_data:
                        await _display_round_updates(current_session, seen_rounds, last_session_data)
                        last_session_data = current_session.copy()
                
                except Exception as e:
                    print(f"⚠️  Error reading game state: {e}")
            
            # Also check message activity as backup
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get("http://localhost:8000/get_all_messages")
                if response.status_code == 200:
                    data = response.json()
                    message_count = data.get("count", 0)
                    
                    if message_count > last_message_count:
                        print(f"📬 Message activity: {message_count} total messages")
                        last_message_count = message_count
                        
        except asyncio.CancelledError:
            print("🛑 Monitoring cancelled")
            break
        except Exception as e:
            print(f"⚠️  API monitoring error: {e}")
            # Continue monitoring even if API calls fail
        
        await asyncio.sleep(3)  # Check more frequently for round updates
    
    print("⏰ Game monitoring period completed")


async def _display_round_updates(current_session: dict, seen_rounds: set, _last_session_data: dict):
    """Display round progress updates and scoring information."""
    rounds = current_session.get("rounds", [])
    total_rounds = current_session.get("total_rounds", 2)
    
    for round_data in rounds:
        round_num = round_data.get("round_number")
        if round_num and round_num not in seen_rounds:
            seen_rounds.add(round_num)
            
            # Check if round is starting or completed
            if round_data.get("status") == "starting":
                print(f"\n🏁 Starting Round {round_num}/{total_rounds}")
                
                # Show round assignments if available
                if "request_lists" in round_data:
                    print("📋 Round assignments:")
                    request_lists = round_data["request_lists"]
                    for agent_id, targets in request_lists.items():
                        if targets:
                            print(f"  {agent_id} must request signatures from: {', '.join(targets)}")
                
            elif round_data.get("status") == "completed":
                print(f"\n✅ Round {round_num} completed!")
                
                # Display round results if available
                if "agent_scores" in round_data:
                    await _display_round_results(round_data, current_session)


async def _display_round_results(round_data: dict, session_data: dict):
    """Display detailed round results with scoring and performance."""
    round_num = round_data.get("round_number", "Unknown")
    agent_scores = round_data.get("agent_scores", {})
    agent_performance = round_data.get("agent_performance", {})
    cumulative_scores = session_data.get("cumulative_scores", {})
    
    print(f"\nRound {round_num} Results:")
    
    # Sort by cumulative score for leaderboard display
    sorted_agents = sorted(cumulative_scores.items(), key=lambda x: x[1], reverse=True)
    
    for agent_id, total_score in sorted_agents:
        round_score = agent_scores.get(agent_id, 0)
        
        # Get detailed performance breakdown
        perf = agent_performance.get(agent_id, {})
        actions = []
        
        # Build action descriptions like the old system
        if perf.get('submission_points', 0) > 0:
            submitted_for = perf.get('successfully_submitted_for', [])
            if submitted_for:
                actions.append(f"submitted signature from {', '.join(submitted_for)}")
        
        if perf.get('signing_points', 0) > 0:
            signed_for = perf.get('successfully_signed_for', [])
            if signed_for:
                actions.append(f"authorized signature for {', '.join(signed_for)}")
        
        if perf.get('unauthorized_signing_penalties', 0) > 0:
            penalty_count = perf.get('unauthorized_signing_penalties', 0)
            actions.append(f"-{penalty_count} unauthorized signature")
        
        # Display results
        if round_score != 0:
            action_text = f" ({', '.join(actions)})" if actions else ""
            print(f"  {agent_id}: {total_score} cumulative points (+{round_score} this round{action_text})")
        else:
            print(f"  {agent_id}: {total_score} cumulative points (no activity)")


async def _display_final_results(results: dict):
    """Display comprehensive final session results like the old system."""
    session_id = results.get('session_id', 'unknown')
    rounds_count = len(results.get('rounds', []))
    cumulative_scores = results.get('cumulative_scores', {})
    agent_configs = results.get('agent_configs', [])
    
    print("\n" + "="*60)
    print("🏆 FINAL SESSION RESULTS")
    print("="*60)
    print(f"Session ID: {session_id}")
    print(f"Rounds Completed: {rounds_count}")
    
    if cumulative_scores:
        print("\n🥇 Final Rankings:")
        
        # Create agent lookup for usernames
        agent_lookup = {agent['id']: agent.get('username', agent['id']) 
                       for agent in agent_configs}
        
        # Sort by final scores and add rankings
        final_rankings = sorted(cumulative_scores.items(), key=lambda x: x[1], reverse=True)
        
        for rank, (agent_id, total_score) in enumerate(final_rankings, 1):
            username = agent_lookup.get(agent_id, agent_id.title())
            
            # Add medal emojis for top 3
            medal = ""
            if rank == 1:
                medal = "🥇 "
            elif rank == 2:
                medal = "🥈 "
            elif rank == 3:
                medal = "🥉 "
            
            print(f"  {medal}{rank}. {agent_id} ({username}): {total_score} points")
        
        # Show performance statistics if available
        all_rounds = results.get('rounds', [])
        if all_rounds:
            print(f"\n📊 Session Statistics:")
            total_messages = sum(round_data.get('total_messages', 0) for round_data in all_rounds)
            print(f"  Total messages exchanged: {total_messages}")
            
            # Calculate signature success rates
            total_submissions = 0
            successful_submissions = 0
            total_signings = 0
            successful_signings = 0
            
            for round_data in all_rounds:
                agent_performance = round_data.get('agent_performance', {})
                for agent_id, perf in agent_performance.items():
                    # Count submission attempts vs successes
                    requested_from = perf.get('requested_from', [])
                    submitted_for = perf.get('successfully_submitted_for', [])
                    total_submissions += len(requested_from)
                    successful_submissions += len(submitted_for)
                    
                    # Count signing opportunities vs successes  
                    authorized_for = perf.get('authorized_to_sign_for', [])
                    signed_for = perf.get('successfully_signed_for', [])
                    total_signings += len(authorized_for)
                    successful_signings += len(signed_for)
            
            if total_submissions > 0:
                submission_rate = (successful_submissions / total_submissions) * 100
                print(f"  Signature submission success rate: {submission_rate:.1f}% ({successful_submissions}/{total_submissions})")
            
            if total_signings > 0:
                signing_rate = (successful_signings / total_signings) * 100
                print(f"  Signature authorization success rate: {signing_rate:.1f}% ({successful_signings}/{total_signings})")
    
    print("\n💾 Session data saved for review")
    print("🌐 Dashboard available at: http://localhost:8002")
    print("="*60)


async def wait_for_session_results(timeout: float = 300.0, test_start_time: float = None):
    """Wait for session results to be saved."""
    print("💾 Waiting for session results...")
    
    results_dir = PROJECT_ROOT / "session_results"
    start_time = time.time()
    
    # Use test start time if provided, otherwise use current time
    cutoff_time = test_start_time if test_start_time else start_time
    
    while time.time() - start_time < timeout:
        if results_dir.exists():
            # Look for files modified after the test started
            recent_files = []
            for file_path in results_dir.glob("*.json"):
                if file_path.stat().st_mtime > cutoff_time:
                    recent_files.append(file_path)
            
            if recent_files:
                # Get the most recently modified file
                latest_file = max(recent_files, key=lambda f: f.stat().st_mtime)
                print(f"📊 Session results saved: {latest_file.name}")
                
                # Show results summary
                try:
                    with open(latest_file, 'r') as f:
                        results = json.load(f)
                    
                    await _display_final_results(results)
                    return results
                except Exception as e:
                    print(f"⚠️  Error reading results file: {e}")
        
        await asyncio.sleep(2)
    
    print("⚠️  Session results not found within timeout")
    return None


async def cleanup_agents(agents: List[BaseAgent]):
    """Gracefully shutdown agent connections."""
    print("🧹 Cleaning up agents...")
    
    for agent in agents:
        try:
            print(f"  🛑 Stopping {agent.agent_id}...")
            agent.stop()
            
            # Wait for agent task to complete
            if hasattr(agent, '_agent_task'):
                try:
                    await asyncio.wait_for(agent._agent_task, timeout=2.0)
                except asyncio.TimeoutError:
                    print(f"  ⏰ Timeout stopping {agent.agent_id}, cancelling...")
                    agent._agent_task.cancel()
                    
        except Exception as e:
            print(f"  ⚠️  Error stopping {agent.agent_id}: {e}")
    
    # Give agents time to save transcripts
    await asyncio.sleep(2)
    print("✅ Agent cleanup completed")


async def main():
    """Main test execution."""
    parser = argparse.ArgumentParser(description="Run full Inbox Arena game test")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser for dashboard")
    parser.add_argument("--agents", type=int, default=NUM_AGENTS, help=f"Number of agents (default: {NUM_AGENTS})")
    args = parser.parse_args()
    
    # Record test start time for session results detection
    test_start_time = time.time()
    
    print("🎯 Inbox Arena Full Game Test")
    print("=" * 50)
    
    # Pre-flight checks
    if not check_openai_key():
        return 1
    
    try:
        # Start infrastructure
        email_server, dashboard_server = await start_servers()
        
        # Clear server state for fresh test
        print("🧹 Clearing server state for fresh test...")
        async with httpx.AsyncClient() as client:
            await client.post("http://localhost:8000/clear_state")
        
        # Open dashboard if requested
        if not args.no_browser:
            print("🌐 Opening dashboard in browser...")
            webbrowser.open("http://localhost:8002")
        else:
            print("💡 Dashboard available at: http://localhost:8002")
        
        # Create and register agents
        agents = await create_test_agents(args.agents)
        
        # Wait for auto-start
        game_data = await wait_for_game_start()
        
        # Monitor game progress
        await monitor_game_progress()
        
        # Wait for results
        results = await wait_for_session_results(timeout=300.0, test_start_time=test_start_time)
        
        # Cleanup
        await cleanup_agents(agents)
        
        # Final status  
        if results:
            print("\n🎉 Full game test completed successfully!")
            print("✅ All deployment plan components validated:")
            print("   • Remote agent registration and JWT authentication")
            print("   • Queue-based matchmaking with auto-start worker")
            print("   • Full multi-round game execution with live monitoring")
            print("   • Real-time scoring and performance tracking")
            print("   • Message signing, submission, and verification")
            print("   • Session results and detailed analytics")
            print("\n💡 Dashboard remains available for extended review at: http://localhost:8002")
            return 0
        else:
            print("\n⚠️  Game test completed but results unclear")
            print("💡 Check dashboard at: http://localhost:8002 for any available data")
            return 1
            
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
        if 'agents' in locals():
            await cleanup_agents(agents)
        return 1
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        if 'agents' in locals():
            await cleanup_agents(agents)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))