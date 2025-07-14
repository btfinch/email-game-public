#!/usr/bin/env python3
"""
Test production deployment with 4 local agents.
Connects local BaseAgent instances to the deployed server and runs a complete game.
"""

import asyncio
import sys
import time
import subprocess
import json
from pathlib import Path
import os
from dotenv import load_dotenv

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import removed - we're using subprocess instead


async def create_test_agent_subprocess(agent_id: str, server_url: str, use_custom: bool = False):
    """Create a test agent as a subprocess (allows logs to show)."""
    agent_type = "custom" if use_custom else "base"
    module_name = "src.custom_base_agent" if use_custom else "src.base_agent"
    
    print(f"🤖 Starting {agent_type} agent subprocess: {agent_id}")
    print(f"   🐍 Python executable: {sys.executable}")
    print(f"   📁 Working directory: {PROJECT_ROOT}")
    print(f"   📦 Module name: {module_name}")
    
    # Debug: Check if the module file exists
    module_path = PROJECT_ROOT / module_name.replace(".", "/") / "__init__.py"
    if not module_path.exists():
        module_path = PROJECT_ROOT / (module_name.replace(".", "/") + ".py")
    
    print(f"   📄 Module file path: {module_path}")
    print(f"   ✅ Module file exists: {module_path.exists()}")
    
    # Debug: Check Python path
    print(f"   🛤️  Python path includes project root: {str(PROJECT_ROOT) in sys.path}")
    
    try:
        # Start agent through wrapper for proper signal handling
        wrapper_path = PROJECT_ROOT / "scripts" / "runners" / "agent_wrapper.py"
        process = subprocess.Popen([
            sys.executable, str(wrapper_path), 
            module_name, agent_id, agent_id.title(), server_url
        ], cwd=PROJECT_ROOT)
        
        # Give the process a moment to start and potentially fail
        import time
        time.sleep(1.0)  # Increased wait time
        
        # Check if process is still running
        if process.poll() is not None:
            print(f"❌ {agent_type.title()} agent {agent_id} failed to start (exit code: {process.returncode})")
            print(f"   🔧 Try running manually: python -m {module_name} {agent_id} {agent_id.title()} {server_url}")
            print(f"   🔧 Or try: cd {PROJECT_ROOT} && python -m {module_name} {agent_id} {agent_id.title()} {server_url}")
            return None
        
        print(f"✅ {agent_type.title()} agent {agent_id} subprocess started (PID: {process.pid})")
        return process
        
    except Exception as e:
        print(f"❌ Failed to start {agent_type} agent {agent_id}: {e}")
        import traceback
        traceback.print_exc()
        return None


async def wait_for_server_ready(server_url: str, timeout: int = 60):
    """Wait for server to be ready and responsive."""
    import requests
    
    print("⏳ Waiting for server to be ready...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{server_url}/health", timeout=10)
            if response.status_code == 200:
                print("✅ Server is ready and healthy")
                return True
        except Exception:
            pass
        
        await asyncio.sleep(2)
    
    print(f"❌ Server not ready within {timeout}s")
    return False


async def monitor_game_progress(server_url: str, timeout: int = 300):
    """Monitor game progress and wait for completion."""
    import requests
    
    print("📊 Monitoring game progress...")
    start_time = time.time()
    game_started = False
    
    while time.time() - start_time < timeout:
        try:
            # Check server health and game status
            response = requests.get(f"{server_url}/health", timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                # Look for game progress indicators
                if 'message_count' in data and data['message_count'] > 0:
                    if not game_started:
                        print("🎯 Game activity detected - messages being exchanged")
                        game_started = True
                
                # Check for session results (game completion) from server
                try:
                    results_response = requests.get(f"{server_url}/session_results", timeout=5)
                    if results_response.status_code == 200:
                        results_data = results_response.json()
                        # Debug logging
                        if results_data.get("files"):
                            print(f"📁 Found {len(results_data['files'])} total session files on server")
                        
                        if results_data.get("success") and results_data.get("files"):
                            # Look for files created since test started
                            recent_files = [
                                f for f in results_data["files"]
                                if f["modified"] > start_time
                            ]
                            
                            # Debug: show timing info
                            if results_data["files"] and not recent_files:
                                latest = max(results_data["files"], key=lambda f: f["modified"])
                                print(f"⏰ Latest file modified at {latest['modified']:.2f}, test started at {start_time:.2f}")
                                print(f"   Time diff: {latest['modified'] - start_time:.2f}s")
                            
                            if recent_files:
                                # Get the most recent file
                                latest_file = max(recent_files, key=lambda f: f["modified"])
                                print(f"🎉 Game completed! Results: {latest_file['filename']}")
                                
                                # Fetch the actual result data
                                result_response = requests.get(f"{server_url}/session_results/{latest_file['filename']}", timeout=5)
                                if result_response.status_code == 200:
                                    result_data = result_response.json()
                                    if result_data.get("success"):
                                        return {"filename": latest_file['filename'], "data": result_data["data"]}
                except Exception as e:
                    print(f"⚠️  Error checking session results: {e}")
            
            await asyncio.sleep(5)
            
        except Exception as e:
            print(f"⚠️  Error monitoring game: {e}")
            await asyncio.sleep(5)
    
    print(f"⏰ Timeout waiting for game completion ({timeout}s)")
    return None


async def cleanup_agent_processes(processes):
    """Clean up agent subprocesses with graceful shutdown."""
    print("🧹 Cleaning up agent processes (graceful shutdown)...")
    
    # First, send SIGTERM to all processes to trigger graceful shutdown
    for process in processes:
        if process and process.poll() is None:  # Check if still running
            try:
                print(f"  📡 Sending SIGTERM to PID {process.pid} for graceful shutdown...")
                process.terminate()  # This sends SIGTERM, which our wrapper handles
            except Exception as e:
                print(f"⚠️  Error sending signal to process: {e}")
    
    # Wait for all processes to shut down gracefully
    print("  ⏳ Waiting for agents to save transcripts and disconnect...")
    await asyncio.sleep(3)  # Give agents time to save transcripts
    
    # Now check if any processes need force killing
    for process in processes:
        if process and process.poll() is None:  # Still running after grace period
            try:
                print(f"  ⚠️  Process PID {process.pid} didn't stop gracefully")
                # Wait a bit more with timeout
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    print(f"  💥 Force killing PID {process.pid}")
                    process.kill()
                    process.wait()
                    
            except Exception as e:
                print(f"⚠️  Error cleaning up process: {e}")
    
    print("  ✅ Agent cleanup completed")


async def main():
    """Run the test with 4 local agents (1 custom + 3 base)."""
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Parse command line arguments
    local_mode = False
    server_url = None
    
    for arg in sys.argv[1:]:
        if arg == "--local":
            local_mode = True
        elif not arg.startswith("--"):
            server_url = arg.rstrip('/')
    
    # Set server URL based on mode
    if local_mode:
        server_url = "http://localhost:8000"
        test_mode = "Local Docker"
    else:
        if server_url is None:
            server_url = "https://inbox-arena-owk4jthsnq-uc.a.run.app"
        test_mode = "Production"
    
    print(f"🎮 {test_mode} Test: 4 Local Agents (1 Custom + 3 Base)")
    print("=" * 50)
    print(f"🌐 Server URL: {server_url}")
    print(f"🔑 OpenAI API Key: {'✅ Set' if os.getenv('OPENAI_API_KEY') else '❌ Missing'}")
    
    if not os.getenv('OPENAI_API_KEY'):
        print("❌ Please set OPENAI_API_KEY environment variable")
        return 1
    
    print()
    
    agent_processes = []
    test_start_time = time.time()
    
    try:
        # First, verify server is ready
        if not await wait_for_server_ready(server_url):
            print("❌ Server not ready, aborting test")
            return 1
        
        # Clear server state to ensure clean test
        print("🧹 Clearing server state for clean test...")
        import requests
        try:
            response = requests.post(f"{server_url}/clear_state", timeout=10)
            if response.status_code == 200:
                print("✅ Server state cleared successfully")
            else:
                print(f"⚠️  Server clear returned {response.status_code}: {response.text}")
        except Exception as e:
            print(f"⚠️  Failed to clear server state: {e}")
            print("   Continuing anyway...")
        
        # Small delay to ensure state is cleared
        await asyncio.sleep(1)
        
        # Create 4 test agents as subprocesses (1 custom + 3 base)
        agent_configs = [
            ("alice", True),    # Custom agent
            ("bob", False),     # Base agent
            ("charlie", False), # Base agent
            ("diana", False)    # Base agent
        ]
        
        print("🤖 Starting agent subprocesses (1 custom + 3 base)...")
        for agent_name, use_custom in agent_configs:
            process = await create_test_agent_subprocess(agent_name, server_url, use_custom)
            if process:
                agent_processes.append(process)
            else:
                print(f"❌ Failed to start agent {agent_name}")
                return 1
            
            # Small delay between agent creation
            await asyncio.sleep(2)
        
        print(f"\n✅ All {len(agent_processes)} agent processes started!")
        print("🎯 Agents should now be registering and joining queue...")
        print("📋 Agent logs will appear below:")
        print("=" * 50)
        
        # Monitor game progress and wait for completion
        result_file = await monitor_game_progress(server_url, timeout=300)
        
        print("=" * 50)
        
        if result_file:
            print(f"\n🎉 {test_mode} test completed successfully!")
            print("✅ Key validations:")
            if local_mode:
                print("   • Local agents connected to Docker containers")
                print("   • Containerized server handling game orchestration")
            else:
                print("   • Local agents connected to production server")
            print("   • Agents successfully registered and joined queue")
            print("   • Game auto-started with 4 agents") 
            print("   • Full game completed with results")
            
            if isinstance(result_file, dict):
                # New format with server data
                print(f"   • Session results retrieved: {result_file['filename']}")
                session_data = result_file['data']
                
                # Save a local copy if running against remote server
                if not local_mode:
                    try:
                        local_session_dir = PROJECT_ROOT / "session_results"
                        local_session_dir.mkdir(exist_ok=True)
                        local_filepath = local_session_dir / result_file['filename']
                        
                        with open(local_filepath, 'w') as f:
                            json.dump(session_data, f, indent=2)
                        
                        print(f"   • Local copy saved: {local_filepath}")
                    except Exception as e:
                        print(f"   ⚠️  Failed to save local copy: {e}")
                
                # Display final scores and winner
                if 'cumulative_scores' in session_data:
                    print("\n🏆 Final Scores:")
                    scores = session_data['cumulative_scores']
                    
                    # Sort agents by score (highest first)
                    sorted_agents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                    
                    # Display scores with ranking
                    for rank, (agent_id, score) in enumerate(sorted_agents, 1):
                        if rank == 1:
                            print(f"   🥇 {agent_id}: {score} points 👑 WINNER!")
                        elif rank == 2:
                            print(f"   🥈 {agent_id}: {score} points")
                        elif rank == 3:
                            print(f"   🥉 {agent_id}: {score} points")
                        else:
                            print(f"   {rank}. {agent_id}: {score} points")
                    
                    # Show total rounds played
                    if 'total_rounds' in session_data:
                        print(f"\n📊 Total rounds played: {session_data['total_rounds']}")
            else:
                # Old format (local file)
                print(f"   • Session results saved: {result_file.name}")
            
            return 0
        else:
            print("\n⚠️  Game may not have completed within timeout")
            print("💡 Check the server logs or try running again")
            return 1
            
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Always clean up agent processes
        await cleanup_agent_processes(agent_processes)
        print(f"⏱️  Total test time: {time.time() - test_start_time:.1f}s")
        
        # Remind about transcripts
        transcript_dir = PROJECT_ROOT / "transcripts"
        if transcript_dir.exists():
            transcript_count = len(list(transcript_dir.glob("*.json")))
            print(f"📝 Agent transcripts saved in: {transcript_dir}")
            print(f"   ({transcript_count} transcript files found)")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))