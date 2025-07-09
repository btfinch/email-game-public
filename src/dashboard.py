"""
Basic Visualization Dashboard - Phase 1
Web interface showing all messages and agent status with auto-refresh.
"""

import requests
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn


class Dashboard:
    """Dashboard for visualizing The Email Game"""
    
    def __init__(self, 
                 email_server_url: str = "http://localhost:8000",
                 moderator_url: str = "http://localhost:8001",
                 dev_mode: bool = False):
        self.email_server_url = email_server_url
        self.moderator_url = moderator_url
        self.dev_mode = dev_mode
    
    def get_all_messages(self):
        """Get all messages from the email server"""
        try:
            response = requests.get(f"{self.email_server_url}/get_all_messages")
            if response.status_code == 200:
                data = response.json()
                if data["success"]:
                    return data["messages"]
            return []
        except Exception as e:
            print(f"Error getting messages: {e}")
            return []
    
    def get_agents_status(self):
        """Get all agents and their status from the moderator"""
        if self.moderator_url is None:
            return []  # Return empty list if moderator is disabled
        try:
            response = requests.get(f"{self.moderator_url}/agents")
            if response.status_code == 200:
                data = response.json()
                if data["success"]:
                    return data["agents"]
            return []
        except Exception as e:
            print(f"Error getting agents: {e}")
            return []
    
    def get_game_status(self):
        """Get current game status from the moderator"""
        if self.moderator_url is None:
            return {"current_round": 0, "round_active": False, "pending_instructions": 0}  # Return default status
        try:
            response = requests.get(f"{self.moderator_url}/game_status")
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            print(f"Error getting game status: {e}")
            return {}
    
    def get_enhanced_queue_status(self):
        """Get queue status with connection information."""
        try:
            response = requests.get(f"{self.email_server_url}/queue_status", timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"Error getting queue status: {e}")
        
        return {
            "queue_length": 0, 
            "agents_waiting": [], 
            "connected_agents": [],
            "game_in_progress": False
        }
    
    def get_recent_games(self):
        """Get recent game results for dashboard."""
        try:
            response = requests.get(f"{self.email_server_url}/session_results", timeout=5)
            if response.status_code == 200:
                results = response.json()
                if results.get('success') and results.get('files'):
                    # Get latest 5 games
                    games = results['files'][:5]
                    # Fetch actual game data for each
                    game_data = []
                    for game in games:
                        try:
                            game_response = requests.get(f"{self.email_server_url}/session_results/{game['filename']}", timeout=5)
                            if game_response.status_code == 200:
                                game_result = game_response.json()
                                if game_result.get('success') and game_result.get('data'):
                                    game_info = {
                                        'filename': game['filename'],
                                        'modified': game['modified'],
                                        'data': game_result['data']
                                    }
                                    game_data.append(game_info)
                        except Exception as e:
                            print(f"Error fetching game data for {game['filename']}: {e}")
                            # Fall back to just filename
                            game_data.append(game)
                    return game_data
        except Exception as e:
            print(f"Error getting recent games: {e}")
        
        return []
    
    def render_messages(self):
        """Render messages as HTML (for testing)"""
        messages = self.get_all_messages()
        html = "<h2>Message Log</h2>\n"
        
        if not messages:
            html += "<p>No messages yet.</p>"
            return html
        
        html += f"<p>Total messages: {len(messages)}</p>\n"
        html += "<div class='messages'>\n"
        
        # Sort messages by timestamp (newest first)
        sorted_messages = sorted(messages, key=lambda x: x.get('timestamp', ''), reverse=True)
        
        for msg in sorted_messages:
            timestamp = msg.get('timestamp', 'Unknown')
            if timestamp != 'Unknown':
                try:
                    # Format timestamp nicely
                    dt = datetime.fromisoformat(timestamp)
                    timestamp = dt.strftime('%H:%M:%S')
                except:
                    pass
            
            html += f"""
            <div class='message'>
                <strong>{timestamp}</strong> - 
                From: <span class='from'>{msg.get('from', 'Unknown')}</span> → 
                To: <span class='to'>{msg.get('to', 'Unknown')}</span><br>
                <strong>Subject:</strong> {msg.get('subject', 'No subject')}<br>
                <strong>Body:</strong> {msg.get('body', 'No body')}<br>
                <strong>Status:</strong> <span class='status-{msg.get("status", "unknown")}'>{msg.get('status', 'Unknown')}</span>
            </div>
            """
        
        html += "</div>\n"
        return html
    
    def render_agent_status(self):
        """Render agent status as HTML (for testing)"""
        agents = self.get_agents_status()
        game_status = self.get_game_status()
        
        html = "<h2>Agent Status</h2>\n"
        
        if not agents:
            html += "<p>No agents registered.</p>"
            return html
        
        html += f"<p>Total agents: {len(agents)}</p>\n"
        html += f"<p>Current round: {game_status.get('current_round', 0)}</p>\n"
        html += f"<p>Round active: {game_status.get('round_active', False)}</p>\n"
        html += f"<p>Pending instructions: {game_status.get('pending_instructions', 0)}</p>\n"
        
        html += "<div class='agents'>\n"
        
        for agent in agents:
            agent_id = agent.get('agent_id', 'Unknown')
            username = agent.get('username', 'Unknown')
            score = agent.get('score', 0)
            status = agent.get('status', 'unknown')
            
            html += f"""
            <div class='agent'>
                <strong>{agent_id}</strong> ({username})<br>
                Status: <span class='status-{status}'>{status}</span><br>
                Score: <span class='score'>{score}</span>
            </div>
            """
        
        html += "</div>\n"
        return html
    
    def get_displayed_messages(self):
        """Get messages for testing (returns list length)"""
        return self.get_all_messages()


# Global dashboard instance - disable moderator URL since we use unified architecture
dashboard = Dashboard(moderator_url=None)

# FastAPI app
app = FastAPI(title="Inbox Arena Dashboard", version="1.0.0")

# Templates
templates = Jinja2Templates(directory="templates")

# Create static files directory (if needed)
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except:
    # Directory doesn't exist yet, that's fine
    pass


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "dashboard"}


@app.get("/api/queue")
async def queue_status():
    """API endpoint for current queue status."""
    return dashboard.get_enhanced_queue_status()


@app.get("/api/recent_games")
async def recent_games():
    """API endpoint for recent game results."""
    return {"games": dashboard.get_recent_games()}


@app.post("/api/dev/clear_server")
async def dev_clear_server():
    """Development helper to clear server state."""
    if not dashboard.dev_mode:
        return {"error": "Development mode not enabled"}
    
    try:
        import requests
        response = requests.post(f"{dashboard.email_server_url}/clear_state", timeout=5)
        return {"success": response.status_code == 200, "status_code": response.status_code}
    except Exception as e:
        return {"error": str(e)}


@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request, agent: str = None, agent1: str = None, agent2: str = None):
    """Main dashboard page with optional agent filtering or dual-agent comparison"""
    try:
        messages = dashboard.get_all_messages()
        agents = dashboard.get_agents_status()
        game_status = dashboard.get_game_status()
        
        # Format messages for display
        formatted_messages = []
        for msg in sorted(messages, key=lambda x: x.get('timestamp', ''), reverse=True):
            timestamp = msg.get('timestamp', 'Unknown')
            if timestamp != 'Unknown':
                try:
                    dt = datetime.fromisoformat(timestamp)
                    timestamp = dt.strftime('%H:%M:%S')
                except:
                    pass
            
            formatted_messages.append({
                'timestamp': timestamp,
                'from': msg.get('from', 'Unknown'),
                'to': msg.get('to', 'Unknown'),
                'subject': msg.get('subject', 'No subject'),
                'body': msg.get('body', 'No body'),
                'status': msg.get('status', 'unknown')
            })
        
        # Detect all available agents from messages
        available_agents = set()
        for msg in formatted_messages:
            if msg['from'] != 'Unknown':
                available_agents.add(msg['from'])
            if msg['to'] != 'Unknown':
                available_agents.add(msg['to'])
        
        # Sort agents alphabetically 
        available_agents = sorted(available_agents)
        
        # Handle different filtering modes
        filtered_messages = formatted_messages
        agent1_messages = []
        agent2_messages = []
        is_dual_mode = False
        
        if agent1 and agent2:
            # Dual-agent comparison mode
            is_dual_mode = True
            agent1_messages = [
                msg for msg in formatted_messages 
                if msg['from'] == agent1 or msg['to'] == agent1
            ]
            agent2_messages = [
                msg for msg in formatted_messages 
                if msg['from'] == agent2 or msg['to'] == agent2
            ]
            # Don't filter the main message list in dual mode
            filtered_messages = formatted_messages
        elif agent:
            # Single agent filtering mode
            filtered_messages = [
                msg for msg in formatted_messages 
                if msg['from'] == agent or msg['to'] == agent
            ]
        
        # Create context for template
        context = {
            'request': request,
            'messages': formatted_messages,
            'filtered_messages': filtered_messages,
            'agents': agents,
            'game_status': game_status,
            'available_agents': available_agents,
            'selected_agent': agent,
            'current_time': datetime.now().strftime('%H:%M:%S'),
            'is_dual_mode': is_dual_mode,
            'agent1': agent1,
            'agent2': agent2,
            'agent1_messages': agent1_messages,
            'agent2_messages': agent2_messages
        }
        
        return templates.TemplateResponse("dashboard.html", context)
    
    except Exception as e:
        # Fallback to simple HTML if template fails
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Inbox Arena Dashboard</title>
            <meta http-equiv="refresh" content="5">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .message {{ border: 1px solid #ccc; margin: 10px 0; padding: 10px; background: #f9f9f9; }}
                .agent {{ border: 1px solid #ddd; margin: 5px 0; padding: 8px; background: #f5f5f5; }}
                .status-sent {{ color: blue; }}
                .status-delivered {{ color: green; }}
                .status-read {{ color: purple; }}
                .status-active {{ color: green; font-weight: bold; }}
                .from {{ color: #d00; font-weight: bold; }}
                .to {{ color: #00d; font-weight: bold; }}
                .score {{ font-weight: bold; color: #060; }}
                h1 {{ color: #333; }}
                h2 {{ color: #666; border-bottom: 2px solid #ddd; }}
                .error {{ color: red; font-style: italic; }}
            </style>
        </head>
        <body>
            <h1>Inbox Arena Dashboard</h1>
            <p class="error">Template error: {str(e)}</p>
            <p>Updated: {datetime.now().strftime('%H:%M:%S')}</p>
            {dashboard.render_agent_status()}
            {dashboard.render_messages()}
        </body>
        </html>
        """
        return HTMLResponse(content=html)


@app.get("/api/messages")
async def get_messages_api():
    """API endpoint to get messages as JSON"""
    messages = dashboard.get_all_messages()
    return {"success": True, "messages": messages, "count": len(messages)}


@app.get("/api/agents")
async def get_agents_api():
    """API endpoint to get agents as JSON"""
    agents = dashboard.get_agents_status()
    return {"success": True, "agents": agents, "count": len(agents)}


@app.get("/api/status")
async def get_status_api():
    """API endpoint to get game status as JSON"""
    game_status = dashboard.get_game_status()
    return game_status


if __name__ == "__main__":
    import sys
    
    # Check for dev mode flag
    dev_mode = "--dev" in sys.argv
    
    if dev_mode:
        print("Starting Inbox Arena Dashboard (Development Mode)...")
        dashboard.dev_mode = True
        print("🛠️  Development features enabled:")
        print("   • /api/dev/clear_server endpoint")
        print("   • Enhanced error reporting")
    else:
        print("Starting Inbox Arena Dashboard...")
    
    print("Dashboard available at: http://localhost:8002")
    print("API endpoints:")
    print("   • /api/queue - Queue status")
    print("   • /api/recent_games - Recent game results")
    if dev_mode:
        print("   • /api/dev/clear_server - Clear server state (dev only)")
    
    uvicorn.run(app, host="0.0.0.0", port=8002) 