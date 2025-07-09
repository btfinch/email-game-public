"""Data models for the email game system"""

from typing import Dict, Any, List
from datetime import datetime
from .config import ROUND_DURATION_SEC


class RoundResult:
    """Results from a single round"""
    def __init__(self, round_number: int, agent_ids: List[str], 
                 request_lists: Dict[str, List[str]], 
                 signing_permissions: Dict[str, List[str]],
                 agent_messages: Dict[str, str]):
        self.round_number = round_number
        self.agent_ids = agent_ids
        self.request_lists = request_lists
        self.signing_permissions = signing_permissions
        self.agent_messages = agent_messages
        self.agent_scores = {}
        self.agent_performance = {}
        self.total_messages = 0
        self.conversations = {}
        self.round_duration = ROUND_DURATION_SEC
        self.start_time = None
        self.end_time = None


class SessionResult:
    """Results from a complete multi-round session"""
    def __init__(self, session_id: str, agent_configs: List[Dict[str, str]]):
        self.session_id = session_id
        self.agent_configs = agent_configs
        self.agent_ids = [agent["id"] for agent in agent_configs]
        self.rounds: List[RoundResult] = []
        self.cumulative_scores = {agent_id: 0 for agent_id in self.agent_ids}
        self.start_time = datetime.now()
        self.end_time = None
        
    def add_round_result(self, round_result: RoundResult):
        """Add a round result and update cumulative scores"""
        self.rounds.append(round_result)
        for agent_id, score in round_result.agent_scores.items():
            self.cumulative_scores[agent_id] += score
    
    def get_performance_trends(self) -> Dict[str, List[int]]:
        """Get score trends for each agent across rounds"""
        trends = {agent_id: [] for agent_id in self.agent_ids}
        for round_result in self.rounds:
            for agent_id in self.agent_ids:
                score = round_result.agent_scores.get(agent_id, 0)
                trends[agent_id].append(score)
        return trends
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for JSON serialization"""
        return {
            "session_id": self.session_id,
            "agent_configs": self.agent_configs,
            "agent_ids": self.agent_ids,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_rounds": len(self.rounds),
            "cumulative_scores": self.cumulative_scores,
            "performance_trends": self.get_performance_trends(),
            "rounds": [
                {
                    "round_number": r.round_number,
                    "agent_ids": r.agent_ids,
                    "request_lists": r.request_lists,
                    "signing_permissions": r.signing_permissions,
                    "agent_messages": r.agent_messages,
                    "agent_scores": r.agent_scores,
                    "agent_performance": r.agent_performance,
                    "total_messages": r.total_messages,
                    "conversations": {
                        (f"{pair[0]}↔{pair[1]}" if isinstance(pair, tuple) else str(pair)): msgs
                        for pair, msgs in r.conversations.items()
                    },
                    "round_duration": r.round_duration,
                    "start_time": r.start_time.isoformat() if r.start_time else None,
                    "end_time": r.end_time.isoformat() if r.end_time else None
                }
                for r in self.rounds
            ]
        }