"""Game-runner service interface (Step 0-f).

This module exposes a synchronous helper `start_session(agent_ids)` that the
email server (or any other orchestrator) can call once a full queue of agents
is ready.  The implementation now runs the full multi-round game logic for
remote authenticated agents.
"""

import asyncio
import json
from datetime import datetime
from typing import List, Dict
from pathlib import Path

from .models import SessionResult
from .runtime import run_single_round
from .config import NUM_ROUNDS, PROJECT_ROOT
from .persistence import save_session_results


def _resolve_agent_configs(agent_ids: List[str]) -> List[Dict[str, str]]:
    """Return list of {id, username} dicts for each agent.

    For now we just title-case the id to make a username.  Later we'll hydrate
    additional metadata from Redis (saved during registration).
    """
    return [{"id": aid, "username": aid.title()} for aid in agent_ids]


async def _update_game_state(session: SessionResult, round_num: int, status: str, round_result=None):
    """Update current_game.json with live game state for monitoring."""
    try:
        game_file = PROJECT_ROOT / "current_game.json"
        
        # Build round data
        rounds_data = []
        for i, round_res in enumerate(session.rounds, 1):
            round_data = {
                "round_number": i,
                "status": "completed",
                "agent_scores": round_res.agent_scores,
                "agent_performance": round_res.agent_performance,
                "request_lists": round_res.request_lists,
                "signing_permissions": round_res.signing_permissions,
                "total_messages": round_res.total_messages
            }
            rounds_data.append(round_data)
        
        # Add current round if starting
        if status == "starting" and round_num <= NUM_ROUNDS:
            rounds_data.append({
                "round_number": round_num,
                "status": "starting",
                "request_lists": round_result.request_lists if round_result else {},
                "signing_permissions": round_result.signing_permissions if round_result else {}
            })
        
        # Create full game state
        game_state = {
            "session_id": session.session_id,
            "agents": [agent["id"] for agent in session.agent_configs],
            "started_at": session.start_time.isoformat() if session.start_time else None,
            "total_rounds": NUM_ROUNDS,
            "rounds": rounds_data,
            "cumulative_scores": session.cumulative_scores
        }
        
        # Write to file
        with open(game_file, 'w') as f:
            json.dump(game_state, f, indent=2)
            
    except Exception as e:
        print(f"⚠️  Failed to update game state: {e}")


async def _run_session_async(agent_ids: List[str]) -> SessionResult:
    """Run the actual game session asynchronously."""
    if not agent_ids:
        raise ValueError("start_session() requires at least one agent id")

    agent_configs = _resolve_agent_configs(agent_ids)
    session_id = f"arena_{int(datetime.now().timestamp())}"
    session = SessionResult(session_id, agent_configs)
    session.start_time = datetime.now()
    
    print(f"🎮 Starting game session {session_id} with {len(agent_ids)} agents")
    print(f"📝 Agents: {', '.join(agent_ids)}")
    
    # Update initial game state
    await _update_game_state(session, 1, "starting")
    
    # Run multiple rounds
    for round_num in range(1, NUM_ROUNDS + 1):
        print(f"\n🏁 Starting Round {round_num}/{NUM_ROUNDS}")
        
        # Create a minimal round result for pre-round state update
        from .models import RoundResult
        from .assignment import generate_balanced_assignment_lists
        from .config import REQUESTS_PER_AGENT
        
        # Generate assignments for this round (this will be done again in run_single_round)
        agent_ids_list = [agent["id"] for agent in agent_configs]
        request_lists, signing_permissions = generate_balanced_assignment_lists(agent_ids_list, REQUESTS_PER_AGENT)
        
        # Create temporary round result for state update
        temp_round = RoundResult(round_num, agent_ids_list, request_lists, signing_permissions, {})
        
        # Update game state to show round starting
        await _update_game_state(session, round_num, "starting", temp_round)
        
        # For remote agents, we pass empty lists for agents and agent_tasks
        # since the agents are connected via WebSocket and will receive instructions
        round_result = await run_single_round(
            round_number=round_num,
            selected_agents=agent_configs,
            agents=[],  # Remote agents, not local processes
            agent_tasks=[]  # Remote agents, not local tasks
        )
        
        session.add_round_result(round_result)
        
        print(f"✅ Round {round_num} completed")
        print(f"📊 Scores: {round_result.agent_scores}")
        
        # Update game state to show round completed
        await _update_game_state(session, round_num, "completed")
    
    session.end_time = datetime.now()
    
    # Save session results
    try:
        await save_session_results(session)
        print(f"💾 Session results saved")
    except Exception as e:
        print(f"⚠️  Failed to save session results: {e}")
    
    print(f"🏆 Game session {session_id} completed!")
    print(f"🥇 Final scores: {session.cumulative_scores}")
    
    # Final game state update
    await _update_game_state(session, NUM_ROUNDS + 1, "completed")
    
    return session


def start_session(agent_ids: List[str]) -> SessionResult:  # noqa: D401
    """Start a full multi-round game session with the given agent IDs.
    
    This runs the complete game logic including:
    - Assignment generation
    - Moderator instructions 
    - Round execution
    - Signature collection and scoring
    - Session results persistence
    
    Note: This function runs synchronously but internally uses async for game logic.
    """
    
    # Run the async session in a new event loop (since this is called from a thread)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_run_session_async(agent_ids))
    finally:
        loop.close() 