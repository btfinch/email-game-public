"""Assignment generation functions for the email game system"""

from typing import Dict, List
import random


def generate_balanced_assignment_lists(agent_ids: List[str], requests_per_agent: int = 2) -> tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """Generate perfectly balanced request and signing assignment lists.
    
    Each agent will request signatures from exactly N agents AND 
    be authorized to sign for exactly N agents.
    
    This creates a fair assignment where all agents have equal opportunities
    for both requesting signatures (+1 point each) and providing signatures (+1 point each).
    
    Args:
        agent_ids: List of agent identifiers
        requests_per_agent: Number of requests/signings per agent (must allow balanced assignment)
    
    Returns:
        Tuple of (request_lists, signing_permission_lists)
        
    Raises:
        ValueError: If balanced assignment is mathematically impossible
    """
    num_agents = len(agent_ids)
    
    # Validate that balanced assignment is possible
    if requests_per_agent >= num_agents:
        raise ValueError(f"requests_per_agent ({requests_per_agent}) must be less than num_agents ({num_agents})")
    
    # For a balanced assignment to exist, the total number of edges must be even
    # Each edge represents: Agent A requests from Agent B (and Agent B signs for Agent A)
    total_edges = num_agents * requests_per_agent
    if total_edges % 2 != 0:
        raise ValueError(f"Cannot create balanced assignment: total edges ({total_edges}) must be even")
    
    # Create balanced assignment using a circular graph approach
    # This ensures each agent appears exactly requests_per_agent times in request lists
    # and exactly requests_per_agent times in signing permission lists
    
    max_attempts = 100
    for _ in range(max_attempts):
        try:
            request_lists = {}
            
            # Start with empty assignments
            for agent_id in agent_ids:
                request_lists[agent_id] = []
            
            # Create a shuffled order for more randomness
            shuffled_agents = agent_ids.copy()
            random.shuffle(shuffled_agents)
            
            # Use circular assignment with random offsets
            for agent_id in shuffled_agents:
                available_agents = [aid for aid in agent_ids if aid != agent_id]
                
                # Try to create balanced assignment for this agent
                attempts_for_agent = 0
                while len(request_lists[agent_id]) < requests_per_agent and attempts_for_agent < 50:
                    attempts_for_agent += 1
                    
                    # Calculate how many times each agent has been requested so far
                    request_counts = {aid: 0 for aid in agent_ids}
                    for req_list in request_lists.values():
                        for requested_agent in req_list:
                            request_counts[requested_agent] += 1
                    
                    # Find agents who can still accept more requests
                    available_for_request = [
                        aid for aid in available_agents 
                        if aid not in request_lists[agent_id] and request_counts[aid] < requests_per_agent
                    ]
                    
                    if not available_for_request:
                        break
                    
                    # Select agent to request from (prefer those with fewer current requests)
                    available_for_request.sort(key=lambda x: request_counts[x])
                    selected_agent = random.choice(available_for_request[:max(1, len(available_for_request)//2)])
                    request_lists[agent_id].append(selected_agent)
            
            # Validate that assignment is balanced
            if validate_balanced_assignment(request_lists, requests_per_agent):
                signing_permissions = generate_signing_permission_lists_from_balanced(request_lists)
                return request_lists, signing_permissions
                
        except Exception as e:
            # Log the exception for debugging but continue trying
            continue
    
    # If we couldn't create a balanced assignment, fall back to simpler algorithm
    print(f"⚠️ Falling back to simpler assignment algorithm...")
    
    return generate_circular_balanced_assignment(agent_ids, requests_per_agent)


def generate_circular_balanced_assignment(agent_ids: List[str], requests_per_agent: int = 2) -> tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """Generate balanced assignment using simple circular algorithm.
    
    This is a fallback method that uses a deterministic circular pattern
    to ensure perfect balance, though with less randomness.
    """
    num_agents = len(agent_ids)
    request_lists = {}
    
    for i, agent_id in enumerate(agent_ids):
        request_list = []
        for j in range(requests_per_agent):
            # Use circular indexing with offset to create balanced assignment
            target_index = (i + j + 1) % num_agents
            target_agent = agent_ids[target_index]
            if target_agent != agent_id:  # Don't request from self
                request_list.append(target_agent)
        
        # If we didn't get enough unique agents (shouldn't happen with proper requests_per_agent)
        while len(request_list) < requests_per_agent:
            for candidate in agent_ids:
                if candidate != agent_id and candidate not in request_list:
                    request_list.append(candidate)
                    break
            break  # Safety break
        
        request_lists[agent_id] = request_list[:requests_per_agent]
    
    signing_permissions = generate_signing_permission_lists_from_balanced(request_lists)
    return request_lists, signing_permissions


def validate_balanced_assignment(request_lists: Dict[str, List[str]], expected_count: int) -> bool:
    """Validate that an assignment is perfectly balanced.
    
    Each agent should appear exactly expected_count times across all request lists,
    and each agent should have exactly expected_count items in their request list.
    """
    agent_ids = list(request_lists.keys())
    
    # Check that each agent requests from exactly expected_count agents
    for agent_id, req_list in request_lists.items():
        if len(req_list) != expected_count:
                return False
    
    # Check that each agent is requested by exactly expected_count agents
    request_counts = {agent_id: 0 for agent_id in agent_ids}
    for req_list in request_lists.values():
        for requested_agent in req_list:
            request_counts[requested_agent] += 1
    
    for agent_id, count in request_counts.items():
        if count != expected_count:
            return False
    
    return True


def generate_signing_permission_lists_from_balanced(request_lists: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Generate signing permission lists from balanced request lists.
    
    Since the request lists are balanced, the resulting signing permissions will also be balanced.
    """
    signing_permissions = {agent_id: [] for agent_id in request_lists.keys()}
    
    for requesting_agent, requested_agents in request_lists.items():
        for requested_agent in requested_agents:
            if requesting_agent not in signing_permissions[requested_agent]:
                signing_permissions[requested_agent].append(requesting_agent)
    
    return signing_permissions




def _self_test():
    """Self-test function to validate assignment generation works correctly"""
    # Test with 4 agents, 2 requests each
    test_agents = ['alice', 'bob', 'charlie', 'diana']
    requests_per_agent = 2
    
    try:
        request_lists, signing_permissions = generate_balanced_assignment_lists(test_agents, requests_per_agent)
        
        # Validate the assignment
        is_valid = validate_balanced_assignment(request_lists, requests_per_agent)
        
        if is_valid:
            # Check that each agent appears exactly requests_per_agent times in signing permissions
            signing_counts = {agent_id: 0 for agent_id in test_agents}
            for agent_list in signing_permissions.values():
                for agent_id in agent_list:
                    signing_counts[agent_id] += 1
            
            all_balanced = all(count == requests_per_agent for count in signing_counts.values())
            if not all_balanced:
                print(f"❌ Signing permissions not balanced: {signing_counts}")
                
        else:
            print("❌ Assignment validation failed")
            
    except Exception as e:
        print(f"❌ Self-test failed with exception: {e}")


if __name__ == "__main__":
    _self_test()