"""High-level session driver for the email game system"""

import asyncio
import webbrowser
import time
from datetime import datetime

from src.email_server import app as email_app
from src.dashboard import app as dashboard_app, dashboard

from .models import SessionResult
from .utils import load_agent_pool  # still used for legacy local testing only
from .utils import select_queued_agents
from .config import NUM_AGENTS, NUM_ROUNDS, KEEP_DASHBOARD_SEC
from .persistence import save_session_results
from .runtime import _run_server_in_thread, wait_for_server_ready, run_single_round


async def run_session(test_mode: bool = False) -> None:
    """Run a complete multi-round email game session"""
    print("Starting Inbox Arena Session")
    
    # Configure dashboard to work without moderator
    dashboard.moderator_url = None  # Disable moderator connections
    
    # 1. Start servers
    email_server_instance = _run_server_in_thread(email_app, 8000, "Email")
    await wait_for_server_ready(8000, "Email")

    dashboard_server_instance = _run_server_in_thread(dashboard_app, 8002, "Dashboard")
    await wait_for_server_ready(8002, "Dashboard")
    
    dashboard_url = "http://127.0.0.1:8002"
    if not test_mode:
        webbrowser.open(dashboard_url)

    # 2. Setup session
    # For the online deployment path we read agent IDs that have joined the
    # Redis *waiting_queue*.  During development (before the remote system is
    # fully wired up) we fall back to the JSON sample-agent pool when the
    # queue is empty so developers can still run a local demo.

    selected_agents = select_queued_agents(NUM_AGENTS)

    if len(selected_agents) < NUM_AGENTS:
        print(
            "⚠️  waiting_queue does not yet contain enough remote agents – "
            "falling back to local sample pool for this session."
        )
        agent_pool = load_agent_pool()
        # Keep first N from sample pool that are NOT already in *selected_agents*
        queued_ids = {a["id"] for a in selected_agents}
        fallback_agents = [a for a in agent_pool if a["id"] not in queued_ids]
        selected_agents.extend(fallback_agents[: (NUM_AGENTS - len(selected_agents))])

    # Create session
    session_id = f"arena_{int(time.time())}"
    session = SessionResult(session_id, selected_agents)
    
    print(f"Selected agents: {', '.join([agent['id'] for agent in selected_agents])}")

    # 3. No local agents are spawned – they will connect remotely.
    agents = []
    agent_tasks = []

    # 4. Run multiple rounds
    for round_num in range(1, NUM_ROUNDS + 1):
        print(f"\n🏁 Starting Round {round_num}/{NUM_ROUNDS}")
        
        # Run the round
        round_result = await run_single_round(round_num, selected_agents, agents, agent_tasks)
        
        # Add to session
        session.add_round_result(round_result)
        
        # Show round results with cumulative progress
        print(f"\nRound {round_num} Results:")
        sorted_cumulative = sorted(session.cumulative_scores.items(), key=lambda x: x[1], reverse=True)
        for agent_id, total_score in sorted_cumulative:
            round_score = round_result.agent_scores.get(agent_id, 0)
            
            # Get detailed breakdown for this agent
            perf = round_result.agent_performance.get(agent_id, {})
            actions = []
            if perf.get('submission_points', 0) > 0:
                submitted_for = perf.get('successfully_submitted_for', [])
                actions.append(f"submitted signature from {', '.join(submitted_for)}")
            if perf.get('signing_points', 0) > 0:
                signed_for = perf.get('successfully_signed_for', [])
                actions.append(f"authorized signature for {', '.join(signed_for)}")
            if perf.get('unauthorized_signing_penalties', 0) > 0:
                penalty_count = perf.get('unauthorized_signing_penalties', 0)
                actions.append(f"-{penalty_count} unauthorized signature")
            
            if round_score != 0:
                action_text = f" ({', '.join(actions)})" if actions else ""
                print(f"  {agent_id}: {total_score} cumulative points (+{round_score} this round{action_text})")
            else:
                print(f"  {agent_id}: {total_score} cumulative points (no activity)")
        
        
        # Inter-round pause (except after last round)
        if round_num < NUM_ROUNDS:
            await asyncio.sleep(3)

    # 5. Final session results
    session.end_time = datetime.now()
    
    print(f"\nSession Complete")
    
    # Final rankings
    final_rankings = sorted(session.cumulative_scores.items(), key=lambda x: x[1], reverse=True)
    for rank, (agent_id, total_score) in enumerate(final_rankings, 1):
        agent_config = next(a for a in selected_agents if a["id"] == agent_id)
        username = agent_config.get("username", agent_id)
        print(f"  {rank}. {agent_id} ({username}): {total_score} points")
    
    # 6. Save results and cleanup
    filepath = await save_session_results(session)
    
    # No local agents to stop
    
    # Keep dashboard running for review (unless in test mode)
    if not test_mode:
        print(f"\n📊 Dashboard available: {dashboard_url}")
        print("💾 Session results saved to:", filepath)
        keep_mins = KEEP_DASHBOARD_SEC // 60
        print(f"⏰ Keeping servers up for {keep_mins} minutes for review... (Ctrl+C to stop)")
        
        try:
            await asyncio.sleep(KEEP_DASHBOARD_SEC)  # 10 minutes
        except KeyboardInterrupt:
            print("\n⏹️ Stopping...")
    
    # Final cleanup
    email_server_instance.should_exit = True
    dashboard_server_instance.should_exit = True
    print("✅ Session complete!")