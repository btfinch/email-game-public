"""
Logs Viewer - Web interface for viewing game session logs
Runs on port 8003 to avoid conflicts with email server (8000) and dashboard (8002)
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn


class LogsViewer:
    """Logs viewer for game session results"""
    
    def __init__(self, session_results_dir: str = None, transcripts_dir: str = None):
        if session_results_dir is None:
            # Default to session_results directory in project root
            project_root = Path(__file__).resolve().parents[1]
            self.session_results_dir = project_root / "session_results"
        else:
            self.session_results_dir = Path(session_results_dir)
        
        if transcripts_dir is None:
            # Default to transcripts directory in project root
            project_root = Path(__file__).resolve().parents[1]
            self.transcripts_dir = project_root / "transcripts"
        else:
            self.transcripts_dir = Path(transcripts_dir)
        
        self.app = FastAPI(title="Inbox Arena Logs Viewer", version="1.0.0")
        self.setup_routes()
    
    def setup_routes(self):
        """Set up FastAPI routes"""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def index(request: Request):
            """Main page showing list of all game sessions"""
            try:
                sessions = self.get_session_list()
                return self.render_session_list(sessions)
            except Exception as e:
                return f"<html><body><h1>Error loading sessions</h1><p>{str(e)}</p></body></html>"
        
        @self.app.get("/api/sessions")
        async def get_sessions():
            """API endpoint to get list of sessions"""
            try:
                return {"sessions": self.get_session_list()}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/session/{session_id}", response_class=HTMLResponse)
        async def view_session(request: Request, session_id: str, agent1: str = None, agent2: str = None):
            """View detailed logs for a specific session with optional dual-agent comparison"""
            try:
                session_data = self.load_session(session_id)
                if not session_data:
                    return f"<html><body><h1>Session not found</h1><p>Session {session_id} could not be loaded.</p></body></html>"
                
                return self.render_session_detail(session_data, agent1, agent2)
            except Exception as e:
                return f"<html><body><h1>Error loading session</h1><p>{str(e)}</p></body></html>"
        
        @self.app.get("/api/session/{session_id}")
        async def get_session_data(session_id: str):
            """API endpoint to get session data"""
            try:
                session_data = self.load_session(session_id)
                if not session_data:
                    raise HTTPException(status_code=404, detail="Session not found")
                return session_data
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
    
    def get_session_list(self) -> List[Dict[str, Any]]:
        """Get list of all available sessions"""
        sessions = []
        
        if not self.session_results_dir.exists():
            return sessions
        
        for session_file in self.session_results_dir.glob("session_arena_*.json"):
            try:
                # Try to load the file
                with open(session_file, 'r') as f:
                    content = f.read()
                
                # Skip empty files
                if not content.strip():
                    continue
                
                session_data = json.loads(content)
                
                # Validate that we have the minimum required fields
                if not isinstance(session_data, dict):
                    continue
                
                # Extract basic info for the list
                session_info = {
                    "file_name": session_file.name,
                    "session_id": session_data.get("session_id", session_file.stem),
                    "start_time": session_data.get("start_time", "unknown"),
                    "end_time": session_data.get("end_time", "unknown"),
                    "total_rounds": session_data.get("total_rounds", 0),
                    "agent_count": len(session_data.get("agent_ids", [])),
                    "agents": session_data.get("agent_ids", []),
                    "cumulative_scores": session_data.get("cumulative_scores", {})
                }
                
                sessions.append(session_info)
                
            except json.JSONDecodeError as e:
                # Skip malformed JSON files silently
                continue
            except Exception as e:
                # Skip other problematic files
                continue
        
        # Sort by start time (newest first)
        sessions.sort(key=lambda x: x.get("start_time", ""), reverse=True)
        return sessions
    
    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load full session data by session ID"""
        for session_file in self.session_results_dir.glob("session_arena_*.json"):
            try:
                with open(session_file, 'r') as f:
                    content = f.read()
                
                # Skip empty files
                if not content.strip():
                    continue
                
                session_data = json.loads(content)
                
                # Check if this is the session we're looking for
                if (session_data.get("session_id") == session_id or 
                    session_file.stem == session_id or
                    session_file.name.replace('.json', '') == session_id):
                    return session_data
                    
            except json.JSONDecodeError:
                # Skip malformed JSON files silently
                continue
            except Exception:
                # Skip other problematic files
                continue
        
        return None
    
    def load_agent_transcript(self, agent_id: str, session_timestamp: str) -> Optional[Dict[str, Any]]:
        """Load transcript data for a specific agent and session"""
        if not self.transcripts_dir.exists():
            return None
        
        # Look for transcript files matching agent_id and timestamp pattern
        pattern = f"{agent_id}_{session_timestamp}*.json"
        transcript_files = list(self.transcripts_dir.glob(pattern))
        
        if not transcript_files:
            # Try without timestamp pattern - look for any transcript for this agent
            pattern = f"{agent_id}_*.json"
            transcript_files = list(self.transcripts_dir.glob(pattern))
            
        if not transcript_files:
            return None
        
        # Use the most recent transcript file
        transcript_file = max(transcript_files, key=lambda f: f.stat().st_mtime)
        
        try:
            with open(transcript_file, 'r') as f:
                return json.loads(f.read())
        except (json.JSONDecodeError, Exception):
            return None
    
    def extract_transcript_sequence(self, transcript_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract the full sequence from transcript message log in original order"""
        sequence = []
        
        if not transcript_data or "message_log" not in transcript_data:
            return sequence
        
        for i, entry in enumerate(transcript_data["message_log"]):
            role = entry.get("role")
            
            if role == "user":
                # This is an incoming message (email)
                content = entry.get("content", "")
                try:
                    # Try to parse as JSON message
                    message_data = json.loads(content)
                    sequence.append({
                        "type": "incoming_message",
                        "data": message_data,
                        "sequence_number": i
                    })
                except json.JSONDecodeError:
                    # Not a JSON message, treat as text
                    sequence.append({
                        "type": "text_input",
                        "content": content,
                        "sequence_number": i
                    })
            
            elif role == "assistant":
                # This is agent's thought/response
                content = entry.get("content", "").strip()
                tool_calls = entry.get("tool_call", [])
                
                sequence.append({
                    "type": "agent_thought",
                    "content": content,
                    "tool_calls": tool_calls,
                    "sequence_number": i
                })
            
            elif role == "function":
                # This is a function result
                function_name = entry.get("name", "unknown")
                content = entry.get("content", "")
                
                sequence.append({
                    "type": "function_result", 
                    "function_name": function_name,
                    "content": content,
                    "sequence_number": i
                })
        
        return sequence
    
    def render_session_list(self, sessions: List[Dict[str, Any]]) -> str:
        """Render HTML for session list"""
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Inbox Arena - Game Sessions</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
                .header { background-color: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
                .session-card { 
                    background: white; 
                    border-radius: 8px; 
                    padding: 20px; 
                    margin-bottom: 15px; 
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    border-left: 4px solid #3498db;
                }
                .session-card:hover { 
                    background-color: #f8f9fa; 
                    transform: translateY(-2px);
                    transition: all 0.2s ease;
                }
                .session-title { 
                    font-size: 18px; 
                    font-weight: bold; 
                    color: #2c3e50; 
                    margin-bottom: 10px;
                }
                .session-info { 
                    display: grid; 
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
                    gap: 10px; 
                    margin-bottom: 15px;
                }
                .info-item { 
                    background-color: #ecf0f1; 
                    padding: 8px 12px; 
                    border-radius: 4px;
                    font-size: 14px;
                }
                .agents-list { 
                    margin-top: 10px;
                }
                .agent-chip { 
                    display: inline-block; 
                    background-color: #3498db; 
                    color: white; 
                    padding: 4px 8px; 
                    border-radius: 12px; 
                    font-size: 12px; 
                    margin-right: 5px; 
                    margin-bottom: 5px;
                }
                .scores { 
                    margin-top: 10px; 
                    font-size: 14px;
                }
                .score-item { 
                    display: inline-block; 
                    margin-right: 15px; 
                    font-weight: bold;
                }
                a { text-decoration: none; color: inherit; }
                .no-sessions {
                    text-align: center;
                    color: #7f8c8d;
                    font-style: italic;
                    padding: 40px;
                    background: white;
                    border-radius: 8px;
                    margin-top: 20px;
                }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🏟️ Inbox Arena - Game Sessions</h1>
                <p>View logs and details for all completed game sessions</p>
            </div>
        """
        
        if not sessions:
            html += """
            <div class="no-sessions">
                <h2>No game sessions found</h2>
                <p>Run some games to see session logs here!</p>
            </div>
            """
        else:
            for session in sessions:
                # Format timestamps
                start_time = self.format_timestamp(session.get("start_time", ""))
                end_time = self.format_timestamp(session.get("end_time", ""))
                duration = self.calculate_duration(session.get("start_time", ""), session.get("end_time", ""))
                
                # Create scores display
                scores_html = ""
                if session.get("cumulative_scores"):
                    scores_items = []
                    for agent, score in session["cumulative_scores"].items():
                        scores_items.append(f'<span class="score-item">{agent}: {score}</span>')
                    scores_html = '<div class="scores">Final Scores: ' + ' '.join(scores_items) + '</div>'
                
                # Create agents list
                agents_html = ""
                if session.get("agents"):
                    agent_chips = [f'<span class="agent-chip">{agent}</span>' for agent in session["agents"]]
                    agents_html = f'<div class="agents-list">{"".join(agent_chips)}</div>'
                
                html += f"""
                <a href="/session/{session['session_id']}">
                    <div class="session-card">
                        <div class="session-title">Session: {session['session_id']}</div>
                        <div class="session-info">
                            <div class="info-item"><strong>Start:</strong> {start_time}</div>
                            <div class="info-item"><strong>End:</strong> {end_time}</div>
                            <div class="info-item"><strong>Duration:</strong> {duration}</div>
                            <div class="info-item"><strong>Rounds:</strong> {session['total_rounds']}</div>
                            <div class="info-item"><strong>Agents:</strong> {session['agent_count']}</div>
                        </div>
                        {agents_html}
                        {scores_html}
                    </div>
                </a>
                """
        
        html += """
        </body>
        </html>
        """
        return html
    
    def render_session_detail(self, session_data: Dict[str, Any], agent1: str = None, agent2: str = None) -> str:
        """Render HTML for detailed session view with optional dual-agent comparison"""
        session_id = session_data.get("session_id", "unknown")
        is_dual_mode = bool(agent1 and agent2)
        
        # Get all available agents from the session
        all_agents = session_data.get("agent_ids", [])
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Inbox Arena - Session {session_id}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
                .header {{ background-color: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
                .back-btn {{ 
                    background-color: #3498db; 
                    color: white; 
                    padding: 8px 16px; 
                    border-radius: 4px; 
                    text-decoration: none; 
                    display: inline-block; 
                    margin-bottom: 10px;
                }}
                .back-btn:hover {{ background-color: #2980b9; }}
                .session-overview {{ 
                    background: white; 
                    padding: 20px; 
                    border-radius: 8px; 
                    margin-bottom: 20px; 
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .filter-section {{
                    background: white;
                    padding: 15px;
                    border-radius: 8px;
                    margin-bottom: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .filter-tabs {{
                    display: flex;
                    margin-bottom: 15px;
                    border-bottom: 2px solid #ddd;
                }}
                .filter-tab {{
                    padding: 10px 20px;
                    background: #f8f9fa;
                    border: none;
                    cursor: pointer;
                    border-bottom: 3px solid transparent;
                    margin-right: 2px;
                    font-size: 14px;
                    transition: all 0.3s;
                }}
                .filter-tab.active {{
                    background: white;
                    border-bottom-color: #3498db;
                    color: #3498db;
                    font-weight: bold;
                }}
                .filter-tab:hover {{
                    background: #e9ecef;
                }}
                .filter-content {{
                    display: none;
                }}
                .filter-content.active {{
                    display: block;
                }}
                .dual-agent-selector {{
                    display: grid;
                    grid-template-columns: 1fr auto 1fr auto;
                    gap: 10px;
                    align-items: center;
                    margin-top: 15px;
                }}
                .agent-select {{
                    padding: 8px 12px;
                    border: 2px solid #ddd;
                    border-radius: 6px;
                    font-size: 14px;
                    background: white;
                }}
                .compare-btn {{
                    padding: 10px 20px;
                    background: #28a745;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    cursor: pointer;
                    font-size: 14px;
                    text-decoration: none;
                    text-align: center;
                    transition: background 0.3s;
                }}
                .compare-btn:hover {{
                    background: #218838;
                }}
                .dual-view {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 20px;
                    margin-bottom: 20px;
                }}
                .agent-column {{
                    background: white;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    overflow: hidden;
                }}
                .agent-column-header {{
                    background: #3498db;
                    color: white;
                    padding: 15px;
                    font-weight: bold;
                    text-align: center;
                    font-size: 16px;
                }}
                .agent-column.agent2 .agent-column-header {{
                    background: #28a745;
                }}
                .agent-messages {{
                    max-height: 70vh;
                    overflow-y: auto;
                    padding: 0;
                }}
                .round-container {{ 
                    background: white; 
                    padding: 20px; 
                    border-radius: 8px; 
                    margin-bottom: 20px; 
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .round-title {{ 
                    font-size: 20px; 
                    font-weight: bold; 
                    color: #2c3e50; 
                    margin-bottom: 15px; 
                    border-bottom: 2px solid #3498db;
                    padding-bottom: 10px;
                }}
                .message {{ 
                    background-color: #f8f9fa; 
                    border-left: 4px solid #3498db; 
                    padding: 15px; 
                    margin-bottom: 15px; 
                    border-radius: 4px;
                }}
                .message.moderator {{ border-left-color: #e74c3c; background-color: #fff5f5; }}
                .message.system {{ border-left-color: #f39c12; }}
                .message.dual {{ 
                    border: none;
                    border-bottom: 1px solid #eee;
                    margin: 0;
                    background: white;
                    transition: background 0.2s;
                }}
                .message.dual:hover {{
                    background: #f8f9fa;
                }}
                .message.dual:last-child {{
                    border-bottom: none;
                }}
                .message-header {{ 
                    font-weight: bold; 
                    margin-bottom: 8px; 
                    color: #2c3e50;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }}
                .message-meta {{ 
                    font-size: 12px; 
                    color: #7f8c8d; 
                }}
                .message-body {{ 
                    white-space: pre-wrap; 
                    line-height: 1.4;
                    background: white;
                    padding: 10px;
                    border-radius: 4px;
                    margin-top: 8px;
                    font-size: 13px;
                    max-height: 200px;
                    overflow-y: auto;
                }}
                .scores-table {{ 
                    width: 100%; 
                    border-collapse: collapse; 
                    margin-top: 15px;
                }}
                .scores-table th, .scores-table td {{ 
                    border: 1px solid #ddd; 
                    padding: 8px; 
                    text-align: center;
                }}
                .scores-table th {{ 
                    background-color: #3498db; 
                    color: white;
                }}
                .performance-summary {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 15px;
                    margin-top: 15px;
                }}
                .agent-performance {{
                    background-color: #ecf0f1;
                    padding: 15px;
                    border-radius: 6px;
                }}
                .agent-name {{
                    font-weight: bold;
                    color: #2c3e50;
                    margin-bottom: 10px;
                    font-size: 16px;
                }}
                .perf-stat {{
                    margin-bottom: 5px;
                    font-size: 14px;
                }}
                .positive {{ color: #27ae60; }}
                .negative {{ color: #e74c3c; }}
                .neutral {{ color: #7f8c8d; }}
                .filter-buttons {{
                    display: flex;
                    gap: 10px;
                    flex-wrap: wrap;
                    margin-top: 10px;
                }}
                .filter-btn {{
                    padding: 8px 16px;
                    border: 2px solid #ddd;
                    background: white;
                    cursor: pointer;
                    border-radius: 20px;
                    text-decoration: none;
                    color: #333;
                    font-size: 14px;
                    transition: all 0.3s;
                }}
                .filter-btn:hover {{
                    background: #f0f0f0;
                }}
                .filter-btn.active {{
                    background: #3498db;
                    color: white;
                    border-color: #3498db;
                }}
                .dual-no-messages {{
                    text-align: center;
                    color: #666;
                    font-style: italic;
                    padding: 30px 15px;
                }}
                .message-count {{
                    font-size: 12px;
                    color: rgba(255,255,255,0.8);
                    margin-top: 5px;
                }}
                .message.thought {{
                    background: #f0f8ff;
                    border-left: 4px solid #9b59b6;
                }}
                .thought-content {{
                    background: #f8f9fa;
                    font-style: italic;
                    color: #2c3e50;
                }}
                .tool-calls {{
                    margin-top: 10px;
                    padding: 8px;
                    background: #fff3cd;
                    border-radius: 4px;
                    border-left: 3px solid #ffc107;
                }}
                .tool-call {{
                    margin-bottom: 8px;
                }}
                .tool-call:last-child {{
                    margin-bottom: 0;
                }}
                .tool-call-header {{
                    font-weight: bold;
                    color: #856404;
                    margin-bottom: 4px;
                }}
                .tool-call-args {{
                    font-family: monospace;
                    font-size: 12px;
                    background: white;
                    padding: 4px 8px;
                    border-radius: 3px;
                    color: #495057;
                    max-height: 100px;
                    overflow-y: auto;
                }}
                .message.incoming {{
                    background: #e8f5e8;
                    border-left: 4px solid #28a745;
                }}
                .message.function-result {{
                    background: #fff8e1;
                    border-left: 4px solid #ff9800;
                }}
                .function-result-content {{
                    font-family: monospace;
                    font-size: 12px;
                    background: #f8f9fa;
                    padding: 8px;
                    border-radius: 4px;
                    max-height: 150px;
                    overflow-y: auto;
                }}
                .message.text-input {{
                    background: #f0f0f0;
                    border-left: 4px solid #6c757d;
                }}
                .message.unknown {{
                    background: #ffe6e6;
                    border-left: 4px solid #dc3545;
                }}
                .transcript-selector {{
                    background: white;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    margin-bottom: 20px;
                    overflow: hidden;
                }}
                .transcript-buttons {{
                    display: flex;
                    background: #f8f9fa;
                    border-bottom: 2px solid #ddd;
                    flex-wrap: wrap;
                    gap: 2px;
                    padding: 5px;
                }}
                .transcript-btn {{
                    padding: 10px 20px;
                    background: white;
                    border: 2px solid #ddd;
                    cursor: pointer;
                    border-radius: 6px;
                    font-size: 14px;
                    transition: all 0.3s;
                    color: #333;
                }}
                .transcript-btn:hover {{
                    background: #e9ecef;
                    border-color: #6c757d;
                }}
                .transcript-btn.active {{
                    background: #007bff;
                    color: white;
                    border-color: #007bff;
                    font-weight: bold;
                }}
                .transcript-content {{
                    padding: 0;
                }}
                .transcript-agent {{
                    padding: 15px;
                }}
                .no-transcripts {{
                    text-align: center;
                    color: #666;
                    font-style: italic;
                    padding: 40px;
                    background: white;
                    border-radius: 8px;
                    margin: 20px 0;
                }}
            </style>
        </head>
        <body>
            <a href="/" class="back-btn">← Back to Sessions</a>
            
            <div class="header">
                <h1>🏟️ Session: {session_id}</h1>
                <p>{"Side-by-side agent comparison" if is_dual_mode else "Detailed logs and message history"}</p>
            </div>
        """
        
        if not is_dual_mode:
            # Add session overview
            html += self._render_session_overview(session_data)
            
            # Add single transcript viewer with agent selector
            session_timestamp = session_data.get("start_time", "").split("T")[0].replace("-", "")
            html += self._render_transcript_selector(session_data, session_timestamp)
        
        else:
            # Dual mode - show side-by-side comparison
            html += f"""
            <div style="text-align: center; margin-bottom: 20px;">
                <a href="/session/{session_id}" class="back-btn">← Back to Full Session View</a>
            </div>
            
            {self._render_dual_agent_view(session_data, agent1, agent2)}
            """
        
        html += f"""
            <script>
                function showTranscript(agentId) {{
                    // Hide all transcript content
                    document.querySelectorAll('.transcript-agent').forEach(content => {{
                        content.style.display = 'none';
                    }});
                    
                    // Remove active class from all buttons
                    document.querySelectorAll('.transcript-btn').forEach(btn => {{
                        btn.classList.remove('active');
                    }});
                    
                    // Show selected transcript
                    const selectedTranscript = document.getElementById('transcript-' + agentId);
                    if (selectedTranscript) {{
                        selectedTranscript.style.display = 'block';
                    }}
                    
                    // Add active class to clicked button
                    event.target.classList.add('active');
                }}
            </script>
        </body>
        </html>
        """
        return html
    
    def _render_session_overview(self, session_data: Dict[str, Any]) -> str:
        """Render session overview section with basic info and scores"""
        session_id = session_data.get("session_id", "unknown")
        start_time = self.format_timestamp(session_data.get("start_time", ""))
        end_time = self.format_timestamp(session_data.get("end_time", ""))
        duration = self.calculate_duration(session_data.get("start_time", ""), session_data.get("end_time", ""))
        total_rounds = session_data.get("total_rounds", 0)
        agents = session_data.get("agent_ids", [])
        cumulative_scores = session_data.get("cumulative_scores", {})
        
        html = f"""
        <div class="session-overview">
            <h2>📊 Session Overview</h2>
            <div class="session-info">
                <div class="info-item"><strong>Session ID:</strong> {session_id}</div>
                <div class="info-item"><strong>Start Time:</strong> {start_time}</div>
                <div class="info-item"><strong>End Time:</strong> {end_time}</div>
                <div class="info-item"><strong>Duration:</strong> {duration}</div>
                <div class="info-item"><strong>Total Rounds:</strong> {total_rounds}</div>
                <div class="info-item"><strong>Agents:</strong> {len(agents)}</div>
            </div>
        """
        
        # Add agents list with scores
        if agents:
            html += '<div class="agents-list">'
            for agent in agents:
                score = cumulative_scores.get(agent, 0)
                html += f'<span class="agent-chip">{agent}: {score} pts</span>'
            html += '</div>'
        
        # Add round statistics
        rounds_data = session_data.get("rounds", [])
        if rounds_data:
            html += """
            <h3>Round Statistics</h3>
            <table class="scores-table">
                <tr><th>Round</th><th>Agents</th><th>Performance Details</th></tr>
            """
            for round_data in rounds_data:
                round_num = round_data.get("round_number", "?")
                round_agents = len(round_data.get("agent_ids", []))
                
                # Get round scores if available
                round_scores = round_data.get("agent_scores", {})
                if round_scores:
                    scores_text = ", ".join([f"{agent}: {score}" for agent, score in round_scores.items()])
                else:
                    scores_text = "No scoring data"
                
                html += f"<tr><td>Round {round_num}</td><td>{round_agents} agents</td><td>{scores_text}</td></tr>"
            html += "</table>"
        
        # Add final scores table if available
        if cumulative_scores:
            html += """
            <h3>Final Scores</h3>
            <table class="scores-table">
                <tr><th>Agent</th><th>Total Score</th></tr>
            """
            # Sort agents by score (descending)
            sorted_agents = sorted(cumulative_scores.items(), key=lambda x: x[1], reverse=True)
            for agent, score in sorted_agents:
                html += f"<tr><td>{agent}</td><td>{score}</td></tr>"
            html += "</table>"
        
        html += "</div>"
        return html
    
    def _render_transcript_selector(self, session_data: Dict[str, Any], session_timestamp: str) -> str:
        """Render the transcript selector for the main session view"""
        agents = session_data.get("agent_ids", [])
        available_transcripts = []
        
        # Check which agents have transcript data
        for agent_id in agents:
            transcript_data = self.load_agent_transcript(agent_id, session_timestamp)
            if transcript_data:
                sequence = self.extract_transcript_sequence(transcript_data)
                if sequence:
                    available_transcripts.append((agent_id, sequence))
        
        if not available_transcripts:
            return '<div class="no-transcripts">📭 No transcript data available for this session</div>'
        
        html = """
        <div class="transcript-selector">
            <h3>Agent Transcript Data</h3>
            <div class="transcript-buttons">
        """
        
        # Add buttons for each agent
        for i, (agent_id, _) in enumerate(available_transcripts):
            active_class = "active" if i == 0 else ""
            html += f'<button class="transcript-btn {active_class}" onclick="showTranscript(\'{agent_id}\')">📋 {agent_id.title()}</button>'
        
        html += """
            </div>
            <div class="transcript-content">
        """
        
        # Add transcript content for each agent
        for i, (agent_id, sequence) in enumerate(available_transcripts):
            display_style = "block" if i == 0 else "none"
            html += f'<div id="transcript-{agent_id}" class="transcript-agent" style="display: {display_style};">'
            
            for item in sequence:
                html += self._render_sequence_item(item, agent_id)
            
            html += '</div>'
        
        html += """
            </div>
        </div>
        """
        return html
    
    def _render_dual_agent_view(self, session_data: Dict[str, Any], agent1: str, agent2: str) -> str:
        """Render side-by-side comparison view for two agents using transcript order"""
        # Load transcript data for both agents
        session_timestamp = session_data.get("start_time", "").split("T")[0].replace("-", "")
        agent1_transcript = self.load_agent_transcript(agent1, session_timestamp)
        agent2_transcript = self.load_agent_transcript(agent2, session_timestamp)
        
        # Extract sequences in original order from transcripts
        agent1_sequence = self.extract_transcript_sequence(agent1_transcript) if agent1_transcript else []
        agent2_sequence = self.extract_transcript_sequence(agent2_transcript) if agent2_transcript else []
        
        # Adjust headers
        if agent1 == agent2:
            header1_title = f"🤖 {agent1.title()} - Transcript View"
            header2_title = f"🤖 {agent2.title()} - Transcript View"
        else:
            header1_title = f"🤖 {agent1.title()} - Transcript View"
            header2_title = f"🤖 {agent2.title()} - Transcript View"
        
        html = f"""
        <div class="dual-view">
            <div class="agent-column agent1">
                <div class="agent-column-header">
                    {header1_title}
                    <div class="message-count">({len(agent1_messages)} messages)</div>
                </div>
                <div class="agent-messages">
        """
        
        # Render agent1 sequence in original order
        if agent1_sequence:
            for item in agent1_sequence:
                html += self._render_sequence_item(item, agent1)
        else:
            html += f'<div class="dual-no-messages">📭 No transcript data for {agent1.title()}</div>'
        
        html += f"""
                </div>
            </div>
            
            <div class="agent-column agent2">
                <div class="agent-column-header">
                    {header2_title}
                    <div class="message-count">({len(agent2_messages)} messages)</div>
                </div>
                <div class="agent-messages">
        """
        
        # Render agent2 sequence in original order
        if agent2_sequence:
            for item in agent2_sequence:
                html += self._render_sequence_item(item, agent2)
        else:
            html += f'<div class="dual-no-messages">📭 No transcript data for {agent2.title()}</div>'
        
        html += """
                </div>
            </div>
        </div>
        """
        
        return html
    
    def _render_sequence_item(self, item: Dict[str, Any], agent_name: str) -> str:
        """Render a single item from the transcript sequence"""
        item_type = item.get("type")
        sequence_num = item.get("sequence_number", 0)
        
        if item_type == "incoming_message":
            # This is an email received by the agent
            message_data = item.get("data", {})
            timestamp = self.format_timestamp(message_data.get("timestamp", ""))
            message_class = "dual incoming"
            if message_data.get("from") == "moderator":
                message_class += " moderator"
            
            return f'''
            <div class="message {message_class}">
                <div class="message-header">
                    <span>📨 <strong>Received Message</strong> (#{sequence_num})</span>
                    <span class="message-meta">{timestamp}</span>
                </div>
                <div><strong>From:</strong> {message_data.get("from", "unknown")} → <strong>To:</strong> {message_data.get("to", "unknown")}</div>
                <div><strong>Subject:</strong> {message_data.get("subject", "No Subject")}</div>
                <div class="message-body">{message_data.get("body", "")}</div>
            </div>
            '''
        
        elif item_type == "agent_thought":
            # This is the agent's reasoning/response
            content = item.get("content", "")
            tool_calls = item.get("tool_calls", [])
            
            return f'''
            <div class="message dual thought">
                <div class="message-header">
                    <span>💭 <strong>{agent_name.title()}'s Response</strong> (#{sequence_num})</span>
                    <span class="message-meta">Internal Processing</span>
                </div>
                <div class="message-body thought-content">{content}</div>
                {self._render_tool_calls(tool_calls)}
            </div>
            '''
        
        elif item_type == "function_result":
            # This is the result of a tool call
            function_name = item.get("function_name", "unknown")
            content = item.get("content", "")
            
            return f'''
            <div class="message dual function-result">
                <div class="message-header">
                    <span>⚙️ <strong>Function Result: {function_name}</strong> (#{sequence_num})</span>
                    <span class="message-meta">System Response</span>
                </div>
                <div class="message-body function-result-content">{content}</div>
            </div>
            '''
        
        elif item_type == "text_input":
            # Non-JSON text input
            content = item.get("content", "")
            
            return f'''
            <div class="message dual text-input">
                <div class="message-header">
                    <span>📝 <strong>Text Input</strong> (#{sequence_num})</span>
                    <span class="message-meta">Input</span>
                </div>
                <div class="message-body">{content}</div>
            </div>
            '''
        
        else:
            return f'''
            <div class="message dual unknown">
                <div class="message-header">
                    <span>❓ <strong>Unknown Item</strong> (#{sequence_num})</span>
                    <span class="message-meta">Unknown Type: {item_type}</span>
                </div>
                <div class="message-body">{str(item)}</div>
            </div>
            '''
    
    def _render_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> str:
        """Render tool calls from transcript data"""
        if not tool_calls:
            return ""
        
        html = '<div class="tool-calls">'
        for tool_call in tool_calls:
            function_name = tool_call.get("function", {}).get("name", "unknown")
            arguments = tool_call.get("function", {}).get("arguments", "{}")
            
            html += f'''
            <div class="tool-call">
                <div class="tool-call-header">🔧 Tool Call: <strong>{function_name}</strong></div>
                <div class="tool-call-args">{arguments}</div>
            </div>
            '''
        html += '</div>'
        return html
    
    def format_timestamp(self, timestamp_str: str) -> str:
        """Format ISO timestamp to readable format"""
        if not timestamp_str or timestamp_str == "unknown":
            return "Unknown"
        
        try:
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            return timestamp_str
    
    def calculate_duration(self, start_time: str, end_time: str) -> str:
        """Calculate duration between start and end times"""
        if not start_time or not end_time or start_time == "unknown" or end_time == "unknown":
            return "Unknown"
        
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            duration = end_dt - start_dt
            
            total_seconds = int(duration.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            
            if hours > 0:
                return f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                return f"{minutes}m {seconds}s"
            else:
                return f"{seconds}s"
        except:
            return "Unknown"


def create_logs_viewer_app(session_results_dir: str = None) -> FastAPI:
    """Create and return the logs viewer FastAPI app"""
    viewer = LogsViewer(session_results_dir)
    return viewer.app


if __name__ == "__main__":
    print("Starting Inbox Arena Logs Viewer...")
    print("Available at: http://localhost:8003")
    print("Note: This runs on port 8003 to avoid conflicts with:")
    print("  - Email Server: http://localhost:8000")
    print("  - Dashboard: http://localhost:8002")
    
    app = create_logs_viewer_app()
    uvicorn.run(app, host="127.0.0.1", port=8003)