"""
Email Simulation Server - Phase 1
Provides REST API for agent communication with message storage and delivery tracking.
Enhanced with request queuing for handling concurrent moderator messages.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import asyncio
import os
import jwt  # PyJWT – added in requirements.txt
import json
from concurrent.futures import ThreadPoolExecutor
from src.game.config import NUM_AGENTS
from src.game.service import start_session

# ---------------------------------------------------------------------------
# External dependencies for upcoming deployment steps
# ---------------------------------------------------------------------------

# Redis dependency removed - using in-memory storage instead

JWT_SECRET = os.getenv("JWT_SECRET", "inbox-arena-secret")

# Security validation helpers
def _validate_recipient(to_agent: str) -> bool:
    """Validate that the recipient agent exists and is valid."""
    if not to_agent or not isinstance(to_agent, str):
        return False
    
    # Allow moderator as a special recipient
    if to_agent == "moderator":
        return True
    
    # Basic validation: alphanumeric and underscore only, reasonable length
    if not to_agent.replace("_", "").isalnum() or len(to_agent) > 50:
        return False
    
    # TODO: Could add Redis lookup to verify agent is registered
    # For now, accept any valid-format agent ID
    return True

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _require_token(request: Request, *, allow_header: bool = True) -> str:
    """FastAPI dependency that returns the *agent_id* from a valid Bearer JWT.

    Raises 401 if no token supplied or invalid, 403 if expired.
    """
    token: str | None = None

    # Prefer Authorization header ("Bearer <token>")
    if allow_header:
        auth = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()

    # Fallback: token in query param
    if token is None:
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        agent_id = payload.get("sub")
        if not agent_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=403, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Stash for downstream handlers
    request.state.agent_id = agent_id
    return agent_id

class Message(BaseModel):
    """Message model for email simulation"""
    from_agent: str
    to_agent: str
    subject: str
    body: str
    timestamp: Optional[str] = None
    message_id: Optional[str] = None
    status: str = "sent"  # sent, delivered, read


class SendMessageRequest(BaseModel):
    """Request model for sending messages - sender derived from JWT token"""
    to: str
    subject: str
    body: str


class BatchSendRequest(BaseModel):
    """Request model for sending multiple messages at once"""
    messages: List[SendMessageRequest]


class EmailServer:
    """Core email server for message storage and routing with request queuing"""
    
    def __init__(self):
        self.messages: List[Dict] = []
        self.message_status: Dict[str, str] = {}
        # Request queue for handling bursts
        self.message_queue: asyncio.Queue = None  # Will be created when needed
        self.queue_processor_task: Optional[asyncio.Task] = None
        self._queue_started = False

        # In-memory storage (replaces Redis)
        self.registered_agents: Dict[str, Dict[str, str]] = {}
        self.waiting_queue: List[str] = []
        self.current_game_in_progress: bool = False
        self._queue_lock = asyncio.Lock()
    
    def _ensure_queue_started(self):
        """Ensure the queue processor is started (lazy initialization)"""
        if not self._queue_started:
            try:
                if self.message_queue is None:
                    self.message_queue = asyncio.Queue()
                self.queue_processor_task = asyncio.create_task(self._process_message_queue())
                self._queue_started = True
            except RuntimeError:
                # No event loop running yet, will try again later
                pass
    
    async def _process_message_queue(self):
        """Background task that processes queued messages one by one"""
        while True:
            try:
                # Get next message from queue (blocks if empty)
                message_data, result_future = await self.message_queue.get()
                print(f"📦 Queue processor: Processing message from {message_data['from_agent']} to {message_data['to']}")
                
                # Process the message
                try:
                    message_id = self._store_message_sync(message_data)
                    result_future.set_result(message_id)
                    print(f"✅ Queue processor: Message {message_id} stored and notified")
                except Exception as e:
                    print(f"❌ Queue processor error storing message: {e}")
                    result_future.set_exception(e)
                
                # Small delay to prevent overwhelming WebSocket delivery
                await asyncio.sleep(0.01)  # 10ms between messages
                
            except Exception as e:
                print(f"Queue processor error: {e}")
                await asyncio.sleep(0.1)
    
    async def store_message_queued(self, message_data: Dict) -> str:
        """Store a message via the queue (non-blocking for concurrent requests)"""
        self._ensure_queue_started()
        if not self._queue_started:
            # Fallback to sync if queue not available
            return self._store_message_sync(message_data)
            
        result_future = asyncio.Future()
        await self.message_queue.put((message_data, result_future))
        return await result_future
    
    def _store_message_sync(self, message_data: Dict) -> str:
        """Synchronous message storage (used by queue processor)"""
        message_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        message = {
            "message_id": message_id,
            "from": message_data["from_agent"],
            "to": message_data["to"],
            "subject": message_data["subject"],
            "body": message_data["body"],
            "timestamp": timestamp,
            "status": "sent"
        }
        
        self.messages.append(message)
        self.message_status[message_id] = "sent"
        
        # After storing, attempt real-time delivery via WebSocket
        try:
            # Get the current event loop and schedule the WebSocket notification
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(manager.send_json(message_data["to"], message))
            else:
                print(f"⚠️  No active event loop for WebSocket notification to {message_data['to']}")
        except Exception as e:
            print(f"⚠️  WebSocket notification failed: {e}")
        
        return message_id
    
    def store_message(self, message_data: Dict) -> str:
        """Store a message and return its ID (legacy sync method)"""
        return self._store_message_sync(message_data)
    
    def get_messages_for_agent(self, agent_id: str) -> List[Dict]:
        """Get all messages for a specific agent"""
        return [msg for msg in self.messages if msg["to"] == agent_id]
    
    def get_all_messages(self) -> List[Dict]:
        """Get all messages (for debugging/visualization)"""
        return self.messages.copy()
    
    def clear_all_messages(self) -> None:
        """Clear all messages (useful for starting new rounds)"""
        self.messages.clear()
        self.message_status.clear()
        print("📧 All messages cleared from email server")
    
    def clear_all_state(self) -> None:
        """Clear all server state (useful for testing)"""
        self.messages.clear()
        self.message_status.clear()
        self.registered_agents.clear()
        self.waiting_queue.clear()
        self.current_game_in_progress = False
        print("🧹 All server state cleared")
    
    def get_message_status(self, message_id: str) -> str:
        """Get the delivery status of a message"""
        return self.message_status.get(message_id, "unknown")
    
    def mark_delivered(self, message_id: str) -> bool:
        """Mark a message as delivered"""
        if message_id in self.message_status:
            self.message_status[message_id] = "delivered"
            # Update message in messages list
            for msg in self.messages:
                if msg["message_id"] == message_id:
                    msg["status"] = "delivered"
                    break
            return True
        return False
    
    def mark_read(self, message_id: str) -> bool:
        """Mark a message as read"""
        if message_id in self.message_status:
            self.message_status[message_id] = "read"
            # Update message in messages list
            for msg in self.messages:
                if msg["message_id"] == message_id:
                    msg["status"] = "read"
                    break
            return True
        return False
    
    # ------------------------------------------------------------------
    # In-memory storage helpers (replaces Redis)
    # ------------------------------------------------------------------

    # ----------------------------
    # Queue helpers
    # ----------------------------

    async def join_queue(self, agent_id: str) -> int:
        """Push *agent_id* to the waiting_queue if not already present.

        Returns the new queue length.  Raises ValueError if the ID is already
        queued.
        """
        async with self._queue_lock:
            # Check for duplicates
            if agent_id in self.waiting_queue:
                raise ValueError("Agent already queued")

            # Add to queue
            self.waiting_queue.append(agent_id)
            queue_len = len(self.waiting_queue)
            
            print(f"📝 Agent {agent_id} joined queue (position {queue_len})")
            
            # Auto-start game if we have enough players
            if queue_len >= NUM_AGENTS and not self.current_game_in_progress:
                selected_agents = self.waiting_queue[:NUM_AGENTS]
                self.waiting_queue = self.waiting_queue[NUM_AGENTS:]
                self.current_game_in_progress = True
                
                print(f"🎯 Starting game with {NUM_AGENTS} agents: {selected_agents}")
                
                # Start game in background
                asyncio.create_task(_start_game_session(selected_agents))
            
            return queue_len

    async def leave_queue(self, agent_id: str) -> bool:
        """Remove agent from waiting_queue if present.
        
        Returns True if agent was removed, False if not in queue.
        """
        async with self._queue_lock:
            if agent_id in self.waiting_queue:
                self.waiting_queue.remove(agent_id)
                print(f"📤 Agent {agent_id} left queue (remaining: {len(self.waiting_queue)})")
                return True
            return False


# Global email server instance
email_server = EmailServer()

# FastAPI app
app = FastAPI(title="Inbox Arena Email Server", version="1.0.0")

# Templates for dashboard
templates = Jinja2Templates(directory="templates")

# Create static files directory (if needed)
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except:
    # Directory doesn't exist yet, that's fine
    pass

# ---------------------------------------------------------------------------
# Agent registration (Step 0-b of deployment plan)
# ---------------------------------------------------------------------------


class RegisterAgentRequest(BaseModel):
    agent_id: str
    rsa_public_key: str


@app.post("/register_agent", status_code=201)
async def register_agent(request: RegisterAgentRequest):
    """Register a remote agent and return a short-lived JWT."""

    print(f"🔐 Registration request for {request.agent_id}")
    print(f"📋 Currently registered agents: {list(email_server.registered_agents.keys())}")

    # Check if agent already registered (in-memory)
    if request.agent_id in email_server.registered_agents:
        print(f"❌ Agent {request.agent_id} already registered")
        raise HTTPException(status_code=409, detail="Agent ID already registered")

    # Store agent data in memory
    email_server.registered_agents[request.agent_id] = {
        "rsa_public_key": request.rsa_public_key
    }
    print(f"✅ Agent {request.agent_id} registered successfully")

    # Generate JWT – 30-minute expiry
    payload = {
        "sub": request.agent_id,
        "exp": datetime.utcnow().timestamp() + 1800,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    return {"success": True, "token": token}


@app.get("/")
async def root():
    """Root endpoint - simple dashboard info"""
    return {
        "service": "Inbox Arena Email Server",
        "status": "running",
        "registered_agents": len(email_server.registered_agents),
        "waiting_queue": len(email_server.waiting_queue),
        "game_in_progress": email_server.current_game_in_progress,
        "api_docs": "/docs"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message_count": len(email_server.messages)}


@app.post("/clear_state")
async def clear_state():
    """Clear all server state (for testing)"""
    email_server.clear_all_state()
    return {"success": True, "message": "Server state cleared"}


@app.get("/session_results")
async def get_session_results():
    """Get list of available session result files"""
    try:
        results_dir = Path(__file__).resolve().parent.parent / "session_results"
        if not results_dir.exists():
            return {"success": True, "files": []}
        
        session_files = list(results_dir.glob("session_arena_*.json"))
        file_info = []
        
        for file_path in session_files:
            file_info.append({
                "filename": file_path.name,
                "size": file_path.stat().st_size,
                "modified": file_path.stat().st_mtime
            })
        
        # Sort by modification time (newest first)
        file_info.sort(key=lambda x: x["modified"], reverse=True)
        
        return {"success": True, "files": file_info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get session results: {str(e)}")


@app.get("/session_results/{filename}")
async def get_session_result(filename: str):
    """Get a specific session result file"""
    try:
        results_dir = Path(__file__).resolve().parent.parent / "session_results"
        file_path = results_dir / filename
        
        # Security check - ensure filename is safe
        if not filename.endswith('.json') or '..' in filename or '/' in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Session result not found")
        
        with open(file_path, 'r') as f:
            session_data = json.load(f)
        
        return {"success": True, "data": session_data}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read session result: {str(e)}")


@app.post("/send_message")
async def send_message(request: SendMessageRequest, token_agent: str = Depends(_require_token)):
    """Send a message from one agent to another"""
    # Validate recipient
    if not _validate_recipient(request.to):
        raise HTTPException(status_code=400, detail=f"Invalid recipient: {request.to}")
    
    try:
        # Sender is derived from JWT token, not client payload
        message_data = {
            "from_agent": token_agent,
            "to": request.to,
            "subject": request.subject,
            "body": request.body
        }
        
        message_id = email_server.store_message(message_data)
        
        return {
            "success": True,
            "message_id": message_id,
            "status": "sent"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")


@app.post("/send_message_queued")
async def send_message_queued(request: SendMessageRequest, token_agent: str = Depends(_require_token)):
    """Send a message via the queue (better for concurrent requests)"""
    # Validate recipient
    if not _validate_recipient(request.to):
        raise HTTPException(status_code=400, detail=f"Invalid recipient: {request.to}")
    
    try:
        # Sender is derived from JWT token, not client payload
        message_data = {
            "from_agent": token_agent,
            "to": request.to,
            "subject": request.subject,
            "body": request.body
        }
        
        message_id = await email_server.store_message_queued(message_data)
        
        return {
            "success": True,
            "message_id": message_id,
            "status": "queued"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue message: {str(e)}")


@app.post("/send_batch")
async def send_batch_messages(
    request: BatchSendRequest,
    token_agent: str = Depends(_require_token),
):
    """Send multiple messages at once (optimized for moderator instructions)"""
    try:
        results = []
        
        # Validate all recipients first
        for msg_request in request.messages:
            if not _validate_recipient(msg_request.to):
                raise HTTPException(status_code=400, detail=f"Invalid recipient in batch: {msg_request.to}")
        
        # Queue all messages concurrently
        tasks = []
        for msg_request in request.messages:
            # Sender is derived from JWT token, not client payload
            message_data = {
                "from_agent": token_agent,
                "to": msg_request.to,
                "subject": msg_request.subject,
                "body": msg_request.body
            }
            task = email_server.store_message_queued(message_data)
            tasks.append(task)
        
        # Wait for all messages to be processed
        message_ids = await asyncio.gather(*tasks)
        
        for i, message_id in enumerate(message_ids):
            results.append({
                "to": request.messages[i].to,
                "message_id": message_id,
                "status": "queued"
            })
        
        return {
            "success": True,
            "messages_sent": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send batch: {str(e)}")


@app.get("/get_messages/{agent_id}")
async def get_messages(agent_id: str):
    """Get all messages for a specific agent"""
    try:
        messages = email_server.get_messages_for_agent(agent_id)
        
        # Mark messages as delivered when retrieved
        for msg in messages:
            if msg["status"] == "sent":
                email_server.mark_delivered(msg["message_id"])
        
        return {
            "success": True,
            "agent_id": agent_id,
            "messages": messages,
            "count": len(messages)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get messages: {str(e)}")


@app.get("/get_all_messages")
async def get_all_messages():
    """Get all messages in the system (for debugging/visualization)"""
    try:
        messages = email_server.get_all_messages()
        return {
            "success": True,
            "messages": messages,
            "count": len(messages)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get all messages: {str(e)}")


@app.put("/mark_read/{message_id}")
async def mark_message_read(message_id: str):
    """Mark a message as read"""
    try:
        success = email_server.mark_read(message_id)
        if success:
            return {
                "success": True,
                "message_id": message_id,
                "status": "read"
            }
        else:
            raise HTTPException(status_code=404, detail="Message not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to mark message as read: {str(e)}")


@app.get("/message_status/{message_id}")
async def get_message_status(message_id: str):
    """Get the status of a specific message"""
    try:
        status = email_server.get_message_status(message_id)
        if status == "unknown":
            raise HTTPException(status_code=404, detail="Message not found")
        
        return {
            "success": True,
            "message_id": message_id,
            "status": status
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get message status: {str(e)}")


@app.get("/get_sent/{agent_id}")
async def get_sent_messages(agent_id: str):
    """Get all messages that a specific agent has sent (their outbox)."""
    try:
        sent_messages = [msg for msg in email_server.messages if msg["from"] == agent_id]
        # No status mutation for sent mail – outbox should reflect original state
        return {
            "success": True,
            "agent_id": agent_id,
            "messages": sent_messages,
            "count": len(sent_messages)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get sent messages: {str(e)}")


@app.get("/get_conversation/{agent_id}")
async def get_conversation(agent_id: str):
    """Get **all** messages involving the agent (sent or received) ordered by timestamp."""
    try:
        # Filter messages where the agent is either sender or recipient
        related = [msg for msg in email_server.messages if msg["from"] == agent_id or msg["to"] == agent_id]

        # Sort by timestamp (ISO strings sort lexicographically in the same order as datetimes)
        related.sort(key=lambda m: m["timestamp"])

        # Mark incoming *unseen* messages as delivered (same rule as inbox endpoint)
        for msg in related:
            if msg["to"] == agent_id and msg["status"] == "sent":
                email_server.mark_delivered(msg["message_id"])

        return {
            "success": True,
            "agent_id": agent_id,
            "messages": related,
            "count": len(related)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get conversation: {str(e)}")


# ---------------------------------------------------------------------------
# Queue endpoint – Step 0-c
# ---------------------------------------------------------------------------


class JoinQueueRequest(BaseModel):
    agent_id: str


@app.post("/join_queue")
async def join_queue(
    payload: JoinQueueRequest,
    token_agent: str = Depends(_require_token),
):
    """Add agent to waiting_queue and return current length."""

    if token_agent != payload.agent_id:
        raise HTTPException(status_code=403, detail="Token/agent mismatch")

    try:
        new_len = await email_server.join_queue(payload.agent_id)
    except ValueError:
        raise HTTPException(status_code=409, detail="Agent already queued")

    return {"success": True, "position": new_len}


@app.post("/leave_queue")
async def leave_queue_endpoint(
    token_agent: str = Depends(_require_token),
):
    """Remove agent from waiting queue."""
    removed = await email_server.leave_queue(token_agent)
    return {"success": True, "removed": removed}


# Queue status endpoint will be added after ConnectionManager is instantiated


# ----------------------------
# WebSocket connection manager
# ----------------------------


class ConnectionManager:
    """Keeps track of active WebSocket connections per agent and allows sending push notifications."""

    def __init__(self):
        # agent_id -> set[WebSocket]
        self.active: Dict[str, set] = {}

    async def connect(self, agent_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active.setdefault(agent_id, set()).add(websocket)
        print(f"🔗 WebSocket connected for agent {agent_id} (total: {len(self.active.get(agent_id, set()))} connections)")

    def disconnect(self, agent_id: str, websocket: WebSocket):
        if agent_id in self.active and websocket in self.active[agent_id]:
            self.active[agent_id].remove(websocket)
            if not self.active[agent_id]:
                # clean empty entry
                self.active.pop(agent_id, None)

    async def send_json(self, agent_id: str, payload: Dict):
        """Send payload to all websockets listening for *agent_id*."""
        if agent_id not in self.active:
            print(f"⚠️  No WebSocket connections for agent {agent_id}")
            return
        
        print(f"📡 Sending WebSocket message to {agent_id} ({len(self.active[agent_id])} connections)")
        dead_connections = []
        sent_count = 0
        
        for ws in list(self.active[agent_id]):
            try:
                await ws.send_json(payload)
                sent_count += 1
            except Exception as e:
                print(f"⚠️  WebSocket send failed: {e}")
                dead_connections.append(ws)
                
        for ws in dead_connections:
            self.disconnect(agent_id, ws)
            
        print(f"✅ WebSocket message sent to {sent_count} connections for {agent_id}")


# Instantiate global connection manager
manager = ConnectionManager()


@app.get("/queue_status")
async def get_queue_status():
    """Get current queue status and connected agents."""
    connected_agents = list(manager.active.keys())
    queue_agents = email_server.waiting_queue.copy()
    
    return {
        "queue_length": len(queue_agents),
        "agents_waiting": queue_agents,
        "connected_agents": connected_agents,
        "game_in_progress": email_server.current_game_in_progress
    }


@app.websocket("/ws/{agent_id}")
async def websocket_endpoint(websocket: WebSocket, agent_id: str):
    """WebSocket endpoint that streams new messages to *agent_id* in real-time."""
    # Expect JWT via query param ?token=... (simpler for browser/agent clients)
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)  # unauthorized
        return

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        sub = payload.get("sub")
        if sub != agent_id:
            await websocket.close(code=4403)  # forbidden
            return
    except jwt.InvalidTokenError:
        await websocket.close(code=4401)
        return

    await manager.connect(agent_id, websocket)
    try:
        while True:
            # Keep the connection alive – we don't expect the agent to send data.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(agent_id, websocket)
        # Remove from queue when disconnecting
        # Note: No JWT needed here - we already authenticated this WebSocket connection
        # and trust the agent_id from the authenticated session
        await email_server.leave_queue(agent_id)
        print(f"🔌 Agent {agent_id} disconnected and removed from queue")


# ---------------------------------------------------------------------------
# Queue-monitor worker – auto-launch games when queue is full (Section 1-a)
# ---------------------------------------------------------------------------

# Use a dedicated, low-priority thread pool so heavy game logic doesn't block
# the FastAPI event loop.
_game_executor: ThreadPoolExecutor | None = None


async def _start_game_session(agent_ids: List[str]):
    """Start a game session with the given agent IDs."""
    global _game_executor
    if _game_executor is None:
        _game_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="game_runner")

    # Persist roster for observability
    try:
        with open("current_game.json", "w", encoding="utf-8") as fh:
            json.dump({
                "agents": agent_ids,
                "started_at": datetime.utcnow().isoformat()
            }, fh, indent=2)
    except Exception:  # pragma: no cover – non-fatal
        pass

    # Start game in background thread
    loop = asyncio.get_running_loop()
    loop.run_in_executor(_game_executor, start_session, agent_ids)
    
    print(f"🎮 Game session started with agents: {agent_ids}")


# No startup hooks needed - games start directly from queue


# ---------------------------------------------------------------------------
# Dashboard Routes (integrated from dashboard.py)
# ---------------------------------------------------------------------------

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_home(request: Request, agent: str = None, agent1: str = None, agent2: str = None):
    """Main dashboard page with optional agent filtering or dual-agent comparison"""
    try:
        # Get messages from our email server
        messages = [
            {
                'timestamp': msg.get('timestamp', 'Unknown'),
                'from': msg.get('from', 'Unknown'),
                'to': msg.get('to', 'Unknown'),
                'subject': msg.get('subject', 'No subject'),
                'body': msg.get('body', 'No body'),
                'status': msg.get('status', 'unknown')
            }
            for msg in email_server.messages
        ]
        
        # Format timestamps
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
            'agents': [],  # No moderator in unified architecture
            'game_status': {"current_round": 0, "round_active": False, "pending_instructions": 0},
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
            <h2>Messages ({len(email_server.messages)})</h2>
            <div class="messages">
        """
        
        # Add messages to fallback HTML
        for msg in sorted(email_server.messages, key=lambda x: x.get('timestamp', ''), reverse=True):
            timestamp = msg.get('timestamp', 'Unknown')
            if timestamp != 'Unknown':
                try:
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
        
        html += """
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html)


@app.get("/dashboard/api/queue")
async def dashboard_queue_status():
    """API endpoint for dashboard queue status."""
    return {
        "queue_length": len(email_server.waiting_queue), 
        "agents_waiting": email_server.waiting_queue.copy(), 
        "connected_agents": list(email_server.registered_agents.keys()),
        "game_in_progress": email_server.current_game_in_progress
    }


@app.get("/dashboard/api/recent_games")
async def dashboard_recent_games():
    """API endpoint for recent game results."""
    try:
        # Get session results from our session_results endpoint
        session_results = await get_session_results()
        if session_results.get('success') and session_results.get('files'):
            # Return latest 5 games
            return {"games": session_results['files'][:5]}
    except Exception as e:
        print(f"Error getting recent games: {e}")
    
    return {"games": []}


if __name__ == "__main__":
    print("Starting Inbox Arena Email Server...")
    print("API documentation available at: http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000) 