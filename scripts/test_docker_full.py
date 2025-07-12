#!/usr/bin/env python3
"""
Full game test using the new single-container Docker setup.
This tests the complete game flow with the containerized infrastructure.
"""

import sys
import os
import time
from pathlib import Path

# Set JWT secret for container compatibility  
os.environ['JWT_SECRET'] = 'inbox-arena-secret'

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Use the full game test but with containerized services
from scripts.full_game_tests.local_test import (
    check_openai_key,
    create_test_agents,
    wait_for_game_start,
    monitor_game_progress,
    wait_for_session_results,
    cleanup_agents
)
import asyncio
import httpx


async def _wait_for_containers_ready(timeout: int = 60):
    """Wait for containerized services to be ready."""
    services = [
        ("Email Server", "http://localhost:8000/health"),
        ("Dashboard", "http://localhost:8000/dashboard")
    ]
    
    start_time = time.time()
    
    for service_name, url in services:
        print(f"  🔍 Checking {service_name}...")
        
        while time.time() - start_time < timeout:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(url)
                    if response.status_code == 200:
                        print(f"  ✅ {service_name} ready")
                        break
            except Exception:
                await asyncio.sleep(2)
        else:
            raise TimeoutError(f"{service_name} not ready within {timeout}s")


async def main():
    """Test full game with containerized infrastructure."""
    print("🐳 Full Game Test with Single-Container Docker Setup")
    print("=" * 60)
    
    # Check prerequisites
    if not check_openai_key():
        return 1
    
    # Wait for containerized services to be ready
    print("⏳ Waiting for containerized services to start...")
    await _wait_for_containers_ready()
    
    # No Redis cache to clear in new architecture
    
    # Record test start time
    test_start_time = time.time()
    
    try:
        print("🤖 Creating agents that will connect to containerized services...")
        
        # Create 4 agents for testing
        agents = await create_test_agents(4)
        
        print("⏳ Waiting for containerized game to auto-start...")
        game_data = await wait_for_game_start()
        
        print("📊 Monitoring game progress...")
        await monitor_game_progress()
        
        print("💾 Waiting for session results...")
        results = await wait_for_session_results(timeout=300.0, test_start_time=test_start_time)
        
        # Cleanup
        await cleanup_agents(agents)
        
        if results:
            print("\n🎉 Containerized game test completed successfully!")
            print("✅ Single-container architecture working:")
            print("   • In-memory queue and agent storage")
            print("   • Single container running email server + dashboard")
            print("   • Local agents connecting to containerized services")
            print("   • Full game execution with results")
            print("   • Dashboard accessible at http://localhost:8002")
            return 0
        else:
            print("\n⚠️  Game completed but results unclear")
            return 1
            
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted")
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