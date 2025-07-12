"""Moderator instruction functions for the email game system"""

from typing import Dict, List, Optional
import json
import asyncio
import httpx
import jwt
import os

from .config import PROJECT_ROOT

# Get JWT secret for moderator authentication
JWT_SECRET = os.getenv("JWT_SECRET", "inbox-arena-secret")

def _get_moderator_token() -> str:
    """Generate a JWT token for the moderator."""
    import time
    now = int(time.time())
    payload = {
        "sub": "moderator",
        "iat": now,
        "exp": now + 3600  # 1 hour expiry
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


async def send_moderator_instructions(
    request_lists: Dict[str, List[str]],
    signing_permissions: Dict[str, List[str]],
    agent_messages: Dict[str, str],
    alias_by_agent: Dict[str, str],
    round_number: int = 1,
    previous_signing_permissions: Dict[str, List[str]] | None = None,
    all_agent_names: List[str] | None = None,
) -> None:
    """Send customized instructions to each agent with signing requirements"""
    
    # Use alias_by_agent for fuzzy descriptions instead of reading from file
    agent_data = alias_by_agent if round_number > 1 else {}
    
    # Generate instructions for each agent based on their signing lists
    instructions = {}
    
    for agent_id in request_lists.keys():
        agent_requests = request_lists[agent_id]
        agent_can_sign_for = signing_permissions[agent_id].copy()  # Copy to avoid modifying original
        agent_message = agent_messages.get(agent_id, "Unknown message")
        
        # Apply fuzzy description replacement for signing permissions (only if round > 1)
        if round_number > 1 and previous_signing_permissions and agent_data:
            for i, target_agent in enumerate(agent_can_sign_for):
                # Check if this agent was authorized to sign for the target agent in the previous round
                # This means the target agent sent a message to this agent in the previous round
                if target_agent in previous_signing_permissions.get(agent_id, []):
                    # Replace with fuzzy description if available
                    if target_agent in agent_data:
                        alias_text = agent_data[target_agent]
                        agent_can_sign_for[i] = f"{alias_text} (from last round; their message this round may be different)"
        
        # Create instruction text - request lists stay explicit, signing permissions may have fuzzy descriptions
        request_text = ", ".join(agent_requests) if agent_requests else "none"
        sign_for_text = ", ".join(agent_can_sign_for) if agent_can_sign_for else "none"
        
        # Prepare agent names text
        agents_text = ", ".join(sorted(all_agent_names)) if all_agent_names else "unknown"
        
        instructions[agent_id] = {
            "subject": f"📢 Inbox Arena – Round {round_number} Instructions for {agent_id.title()}",
            "body": (
                f"Welcome, {agent_id.title()}!\n\n"
                f"**ROUND {round_number}** - Message signing and verification round.\n\n"
                f"**Participating Agents:** {agents_text}\n\n"
                "**Your Assigned Message:**\n"
                f"You must get signatures for this EXACT message: \"{agent_message}\"\n\n"
                "**Your Signing Requirements:**\n"
                f"1. You must REQUEST signatures from these agents: {request_text}\n"
                f"2. You are AUTHORIZED to sign messages for these agents: {sign_for_text}\n\n"
                "**Instructions:**\n"
                f"1. Send requests to agents asking them to sign your assigned message: \"{agent_message}\"\n"
                "2. When other agents request signatures from you (and you're authorized), provide signed messages\n"
                "3. Submit all received signatures to the moderator for scoring\n"
                "4. When you send your **submission email to the moderator**, make sure the subject contains the word 'submission' (any case) so it is detected by scoring. You do NOT need this keyword in signature request emails to other agents.\n"
                f"5. Use the format: 'Please sign this message for me: {agent_message}' when requesting signatures.\n\n"
                "**Important:**\n"
                "- Only request signatures for your assigned message\n"
                "- Only sign messages when you're authorized for that agent\n\n"
                "**Scoring:**\n"
                "- +1 point for each valid signature you successfully obtain and submit\n"
                "- +1 point for each signature you provide when authorized\n"
                "- -1 point for each signature you provide when NOT authorized\n\n"
                "– Moderator"
            )
        }
    
    # Send batch instructions
    try:
        # Get moderator JWT token
        moderator_token = _get_moderator_token()
        headers = {"Authorization": f"Bearer {moderator_token}"}
        
        batch_messages = []
        for agent_id, instruction in instructions.items():
            batch_messages.append({
                "to": agent_id,
                "subject": instruction["subject"],
                "body": instruction["body"]
            })
        
        batch_payload = {"messages": batch_messages}
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post("http://127.0.0.1:8000/send_batch", json=batch_payload, headers=headers)
            
        if response.status_code == 200:
            print(f"[instructions] Successfully sent batch instructions to {len(batch_messages)} agents")
        else:
            raise Exception(f"Batch send failed with status {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"[instructions] Batch send failed: {e}. Falling back to individual sends…")
        # Fallback to individual sends
        moderator_token = _get_moderator_token()
        headers = {"Authorization": f"Bearer {moderator_token}"}
        
        for agent_id, instruction in instructions.items():
            try:
                payload = {
                    "to": agent_id,
                    "subject": instruction["subject"],
                    "body": instruction["body"]
                }
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post("http://127.0.0.1:8000/send_message_queued", json=payload, headers=headers)
                    
                if response.status_code == 200:
                    print(f"[instructions] Sent individual instruction to {agent_id}")
                else:
                    print(f"[instructions] Failed to send to {agent_id}: {response.status_code}")
                    
                await asyncio.sleep(0.05)
                
            except Exception as e:
                print(f"[instructions] Error sending to {agent_id}: {e}")
                continue