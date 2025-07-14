"""
Base Agent - Phase 1
"""

# Standard libraries
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import base64
import os

# Cryptography imports
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# Third-party
import requests
import jwt  # PyJWT – used for decoding token expiry
import websockets
from dotenv import load_dotenv
from .custom_llm_driver import CustomLLMDriver
from .game.config import OPENAI_MODEL

# Auto-load local .env so OPENAI_API_KEY and other secrets are available
load_dotenv()

class CustomBaseAgent:
    """Basic agent for The Email Game"""
    
    def __init__(self, agent_id: str, username: str,
                 email_server_url: str = "http://localhost:8000",
                 moderator_agent: str = "moderator",
                 dev_mode: bool = False):
        self.agent_id = agent_id
        self.username = username
        self.email_server_url = email_server_url
        print(f"[{self.agent_id}] Creating BaseAgent with server: {email_server_url}")
        self.moderator_agent = moderator_agent
        self.dev_mode = dev_mode
        
        # Agent state
        self.running = False
        self.instructions_processed = 0
        self.messages_sent = 0
        self.current_instruction = None
        
        # Inactivity reminder system
        self.can_send_reminder = False  # Set to True when moderator message received
        self.last_message_time = datetime.now()
        self.inactivity_threshold_seconds = 25  # Send reminder after 25 seconds of inactivity
        
        # ------------------------------------------------------------------
        # RSA signing capability + JWT auth state
        # ------------------------------------------------------------------

        self.rsa_private_key, self.rsa_public_key = self._load_rsa_keys()

        # Keep PEM around for registration
        self._public_key_pem: str = self.rsa_public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

        # JWT auth fields
        self._jwt_token: Optional[str] = None
        self._jwt_expiry: float = 0.0  # unix timestamp
        print(f"[{self.agent_id}] Initial token state: {self._jwt_token}")
        
        # Async task for the WebSocket listener
        self._ws_task: Optional[asyncio.Task] = None
        
        # Development mode features
        if self.dev_mode:
            self._setup_dev_features()
        
        # Register and join queue immediately (raises on failure)
        # Delay heavy WebSocket / LLM startup until server interaction works.
        print(f"[{self.agent_id}] Initializing BaseAgent...")
        self._register_with_server()
        self._join_queue()
        
        # LLM driver setup
        prompt_file = Path(__file__).resolve().parent.parent / "docs" / "agent_prompt.md"
        try:
            system_prompt = prompt_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            system_prompt = "Inbox Arena agent system prompt (file not found)"

        # Add signing tools to LLM driver
        self.driver = CustomLLMDriver(
            agent_id=self.agent_id,
            system_prompt=system_prompt,
            send_email_callable=self.send_message,
            sign_message_callable=self.sign_message,
            sign_and_respond_callable=self.sign_and_respond,
            submit_signature_callable=self.submit_signature,
            model=OPENAI_MODEL,  # model defined in config
            verbose=False,
        )
        
        # Deduplication – keep track of message_ids we have already processed so
        # reconnect-triggered backlog replays do not feed the same email to the
        # LLM multiple times.
        self._seen_message_ids: set[str] = set()
    
    def register_with_moderator(self) -> bool:
        """Register this agent with the moderator"""
        return True
    
    # ------------------------------------------------------------------
    # Networking helpers – registration / queue / JWT handling
    # ------------------------------------------------------------------

    def _register_with_server(self) -> None:
        """Register this agent with the email server and cache the JWT."""

        if self._jwt_token and (self._jwt_expiry - datetime.utcnow().timestamp() > 120):
            return  # still valid

        url = f"{self.email_server_url}/register_agent"
        payload = {"agent_id": self.agent_id, "rsa_public_key": self._public_key_pem}
        r = requests.post(url, json=payload, timeout=10)

        if r.status_code == 409:
            # Already registered – keep existing token if valid, or get new one in _join_queue
            print(f"[{self.agent_id}] Agent already registered, will get token if needed")
            return

        r.raise_for_status()
        data = r.json()
        self._jwt_token = data["token"]

        # Decode to get expiry (without verifying signature – we only need 'exp')
        try:
            payload = jwt.decode(self._jwt_token, options={"verify_signature": False}, algorithms=["HS256"])
            self._jwt_expiry = float(payload.get("exp", 0))
        except Exception:
            self._jwt_expiry = datetime.utcnow().timestamp() + 1800  # fallback 30m

    def _join_queue(self) -> int:
        """Join the waiting_queue; returns new queue length."""
        # Ensure we have a valid token
        if not self._jwt_token:
            print(f"[{self.agent_id}] No token, registering...")
            self._register_with_server()
        
        print(f"[{self.agent_id}] Joining queue with token: {self._jwt_token and self._jwt_token[:20]}...")
        hdr = {"Authorization": f"Bearer {self._jwt_token}"}
        r = requests.post(f"{self.email_server_url}/join_queue", json={"agent_id": self.agent_id}, headers=hdr, timeout=10)
        
        # If we get 401, try to re-register and retry once
        if r.status_code == 401:
            print(f"[{self.agent_id}] Token invalid, re-registering...")
            self._jwt_token = None
            self._jwt_expiry = 0.0
            self._register_with_server()
            hdr = {"Authorization": f"Bearer {self._jwt_token}"}
            r = requests.post(f"{self.email_server_url}/join_queue", json={"agent_id": self.agent_id}, headers=hdr, timeout=10)
        
        if r.status_code not in (200, 201):
            raise RuntimeError(f"join_queue failed: {r.status_code} {r.text}")
        return r.json().get("position", -1)

    def _auth_headers(self) -> Dict[str, str]:
        """Return Bearer-token headers; refresh if token is close to expiry."""
        if datetime.utcnow().timestamp() > self._jwt_expiry - 60:
            # Very close to expiry; attempt re-register (simple refresh placeholder)
            self._register_with_server()
        return {"Authorization": f"Bearer {self._jwt_token}"}

    # ------------------------------------------------------------------
    # Public API wrappers (polling, sending)
    # ------------------------------------------------------------------

    def poll_messages(self) -> List[Dict]:
        """Poll for new messages from the email server"""
        try:
            response = requests.get(
                f"{self.email_server_url}/get_messages/{self.agent_id}",
                headers=self._auth_headers(),
            )
            
            if response.status_code == 200:
                data = response.json()
                if data["success"]:
                    return data["messages"]
            
            return []
            
        except Exception as e:
            print(f"Error polling messages: {e}")
            return []
    
    def send_message(self, to_agent: str, subject: str, body: str) -> Dict:
        """Send a message via the email server API"""
        try:
            # Sender is derived from JWT token, not specified in payload
            message_data = {
                "to": to_agent,
                "subject": subject,
                "body": body,
            }
            
            response = requests.post(
                f"{self.email_server_url}/send_message",
                json=message_data,
                headers=self._auth_headers(),
            )
            
            if response.status_code == 200:
                data = response.json()
                if data["success"]:
                    self.messages_sent += 1
                    return {"success": True, "message_id": data["message_id"]}
            
            return {"success": False, "error": "Failed to send message"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # -----------------------------
    # WebSocket real-time listener
    # -----------------------------

    async def _ws_loop(self):
        # Convert base http(s) URL -> ws(s)
        ws_base = self.email_server_url.replace("http://", "ws://").replace("https://", "wss://")
        uri = f"{ws_base}/ws/{self.agent_id}?token={self._jwt_token}"
        
        print(f"[{self.agent_id}] 🔗 Starting WebSocket loop, connecting to: {uri}")
        
        while self.running:
            try:
                print(f"[{self.agent_id}] 🔄 Attempting WebSocket connection...")
                async with websockets.connect(uri) as ws:
                    print(f"[{self.agent_id}] ✅ WebSocket connected successfully")

                    # One-off catch-up for any messages that arrived while we
                    # were offline.
                    backlog = self.poll_messages()
                    if backlog:
                        print(f"[{self.agent_id}] 📬 Processing {len(backlog)} backlog messages")
                    for msg in backlog:
                        self._handle_incoming_message(msg)
                        
                    print(f"[{self.agent_id}] 👂 Listening for WebSocket messages...")
                    while self.running:
                        try:
                            # Wait for message with timeout to enable periodic inactivity checks
                            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                            message = json.loads(raw) if isinstance(raw, str) else raw
                            print(f"[{self.agent_id}] 📨 WebSocket message received")
                            self._handle_incoming_message(message)
                        except asyncio.TimeoutError:
                            # No message received in timeout period - check for inactivity
                            self._check_inactivity()
                        except websockets.exceptions.ConnectionClosed:
                            print(f"[{self.agent_id}] 🔌 WebSocket connection closed")
                            break
            except Exception as e:
                print(f"[{self.agent_id}] ❌ WebSocket error: {e}")
                if self.running:
                    print(f"[{self.agent_id}] 🔄 Reconnecting in 2 seconds...")
                    await asyncio.sleep(2)

    # -----------------------------
    # Helpers
    # -----------------------------

    def _handle_incoming_message(self, message: Dict) -> None:
        """Forward any incoming message to the LLM driver."""
        try:
            msg_id = message.get("message_id")
            from_agent = message.get('from', message.get('from_agent', ''))
            subject = message.get('subject', 'No Subject')
            
            print(f"[{self.agent_id}] 📬 Received message from '{from_agent}': {subject}")
            
            if msg_id and msg_id in self._seen_message_ids:
                print(f"[{self.agent_id}] ⚠️  Duplicate message {msg_id} - skipping")
                return  # Duplicate already processed earlier

            # Record that we've handled this message
            if msg_id:
                self._seen_message_ids.add(msg_id)

            # Update last message time for inactivity tracking
            self.last_message_time = datetime.now()
            
            # Check if this is from moderator (marks start of new round)
            if from_agent == self.moderator_agent:
                print(f"[{self.agent_id}] 🎯 Moderator instruction received - processing with LLM")
                self.can_send_reminder = True
            
            self.instructions_processed += 1
            
            # Forward to LLM driver
            print(f"[{self.agent_id}] 🤖 Forwarding to LLM driver...")
            self.driver.on_email(message)
            print(f"[{self.agent_id}] ✅ LLM processing completed")
            
        except Exception as e:
            print(f"[{self.agent_id}] ❌ Error handling message: {e}")
            import traceback
            traceback.print_exc()
    
    def _send_inactivity_reminder(self) -> None:
        """Send an inactivity reminder to help agent complete pending actions"""
        try:
            
            # Mark that we've sent the reminder (prevents duplicates this round)
            self.can_send_reminder = False
            
            # Create reminder message
            reminder_content = {
                "message_id": f"reminder_{self.agent_id}_{datetime.now().isoformat()}",
                "from": "system_reminder",
                "to": self.agent_id,
                "subject": "⏰ Action Completion Reminder",
                "body": (
                    "REMINDER: Ensure you have completed all required actions for this round.\n\n"
                    "Check if you have:\n"
                    "- Submitted ALL signatures you received (missing submissions cost points)\n"
                    "- Responded to ALL signature requests you're authorized for\n"
                    "- Completed ALL tasks from the moderator's instructions\n\n"
                    "Remember your system prompt requirements:\n"
                    "- ALWAYS use function calls when taking action\n"
                    "- NEVER respond with markdown code blocks\n"
                    "- Submit every signature you receive immediately\n\n"
                    "Review your recent messages and ensure no actions are incomplete."
                ),
                "timestamp": datetime.now().isoformat(),
                "status": "sent"
            }
            
            # Send reminder through the message handling system
            self._handle_incoming_message(reminder_content)
            
        except Exception:
            pass
    
    def _check_inactivity(self) -> None:
        """Check if agent has been inactive and send reminder if needed"""
        try:
            # Only check if we're allowed to send reminders this round
            if not self.can_send_reminder:
                return
            
            # Check time since last message
            time_since_last = (datetime.now() - self.last_message_time).total_seconds()
            
            if time_since_last >= self.inactivity_threshold_seconds:
                self._send_inactivity_reminder()
            
        except Exception:
            pass
    
    # -----------------------------
    # Public control API
    # -----------------------------

    async def run(self) -> None:
        """Run the agent until `stop()` is called or the process exits."""
        if self.running:
            return

        self.running = True

        # Launch WebSocket listener task
        loop = asyncio.get_running_loop()
        self._ws_task = loop.create_task(self._ws_loop())

        try:
            # Wait for the WebSocket task to finish (runs until stop())
            await self._ws_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        finally:
            self.running = False

    def run_sync(self):
        """Convenience wrapper to run the async agent with `asyncio.run`."""
        asyncio.run(self.run())

    def stop(self) -> None:
        """Stop the agent gracefully"""
        self.running = False
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
        
        # Save transcript when stopping
        self.save_transcript()
    
    def _load_rsa_keys(self) -> tuple:
        """Load RSA keys for this agent from sample_agents.json"""
        try:
            # Load agent data from sample_agents.json
            agents_file = Path(__file__).resolve().parents[1] / "data" / "sample_agents.json"
            with open(agents_file, 'r') as f:
                data = json.load(f)
            
            # Find this agent's data
            agent_data = None
            for agent in data['agents']:
                if agent['id'] == self.agent_id:
                    agent_data = agent
                    break
            
            if not agent_data:
                raise ValueError(f"Agent {self.agent_id} not found in sample_agents.json")
            
            # Load private key
            private_key_pem = agent_data['rsa_private_key']
            private_key = serialization.load_pem_private_key(
                private_key_pem.encode(),
                password=None
            )
            
            # Load public key  
            public_key_pem = agent_data['rsa_public_key']
            public_key = serialization.load_pem_public_key(
                public_key_pem.encode()
            )
            
            return private_key, public_key
            
        except Exception as e:
            # Fallback to generating new keys (should not happen in production)
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048
            )
            public_key = private_key.public_key()
            return private_key, public_key
    
    def sign_message(self, message: str, for_agent: str) -> Dict[str, Any]:
        """Sign a message for another agent using RSA"""
        
        timestamp = datetime.now().isoformat()
        
        # Create message to sign
        sign_data = f"{message}|{self.agent_id}|{for_agent}|{timestamp}"
        
        try:
            # Generate RSA signature
            signature_bytes = self.rsa_private_key.sign(
                sign_data.encode(),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            # Convert to base64 for JSON serialization
            signature_b64 = base64.b64encode(signature_bytes).decode('utf-8')
            
            signed_message = {
                "original_message": message,
                "signature": signature_b64,
                "signer": self.agent_id,
                "signed_for": for_agent,
                "timestamp": timestamp,
                "signature_type": "rsa_pss_sha256"
            }
            
            return signed_message
            
        except Exception as e:
            return {"error": str(e)}
    
    def sign_and_respond(self, to_agent: str, message_to_sign: str, response_body: str, subject: str = "Signed Message") -> Dict[str, Any]:
        """Sign a message and send it back to the requesting agent in a single operation"""
        
        try:
            # 1. Create the RSA signature
            timestamp = datetime.now().isoformat()
            sign_data = f"{message_to_sign}|{self.agent_id}|{to_agent}|{timestamp}"
            
            # Generate RSA signature
            signature_bytes = self.rsa_private_key.sign(
                sign_data.encode(),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            # Convert to base64 for JSON serialization
            signature_b64 = base64.b64encode(signature_bytes).decode('utf-8')
            
            signed_message = {
                "original_message": message_to_sign,
                "signature": signature_b64,
                "signer": self.agent_id,
                "signed_for": to_agent,
                "timestamp": timestamp,
                "signature_type": "rsa_pss_sha256"
            }
            
            
            # 2. Prepare email body with signature appended
            signature_json = json.dumps(signed_message, separators=(',', ':'))
            full_body = f"{response_body}\n\nSIGNED_MESSAGE_JSON:{signature_json}"
            
            
            # 3. Send the email
            email_result = self.send_message(to_agent, subject, full_body)
            
            if email_result.get("success"):
                return {
                    "success": True,
                    "message_id": email_result.get("message_id"),
                    "signed_message": signed_message,
                    "to_agent": to_agent
                }
            else:
                return {"success": False, "error": "Failed to send email"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def extract_signed_message_from_email(self, email_body: str) -> Optional[Dict[str, Any]]:
        """Extract signed message JSON from an email body"""
        try:
            # Look for the signature JSON marker
            marker = "SIGNED_MESSAGE_JSON:"
            if marker in email_body:
                # Extract everything after the marker
                json_part = email_body.split(marker, 1)[1].strip()
                # Parse the JSON
                signed_message = json.loads(json_part)
                return signed_message
            else:
                return None
        except Exception as e:
            return None
    
    # Note: Signature verification is now handled externally using public keys
    # Agents only sign messages, they don't verify them
    
    def submit_signature(self, signed_message: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a received signature to the moderator via email"""
        try:
            
            # Create submission data
            submission_data = {
                "submission_type": "signature",
                "submitter": self.agent_id,
                "signatures": [signed_message]
            }
            
            # Send as email to moderator
            result = self.send_message(
                to_agent=self.moderator_agent,
                subject=f"Signature Submission - {self.agent_id}",
                body=json.dumps(submission_data, indent=2)
            )
            
            if result.get("success"):
                return {"success": True, "message_id": result.get("message_id")}
            else:
                return {"success": False, "error": result.get("error", "Unknown error")}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_status(self) -> Dict[str, Any]:
        """Get current agent status"""
        return {
            "agent_id": self.agent_id,
            "username": self.username,
            "running": self.running,
            "instructions_processed": getattr(self, 'instructions_processed', 0),
            "messages_sent": getattr(self, 'messages_sent', 0),
            "signatures_received": len(getattr(self, 'received_signatures', [])),
            "current_instruction": getattr(self, 'current_instruction', None)
        }
    
    def save_transcript(self) -> None:
        """Save the complete LLM conversation transcript to a file"""
        try:
            # Always save transcripts inside repo-root /transcripts (independent of cwd)
            project_root = Path(__file__).resolve().parents[1]
            transcript_dir = project_root / "transcripts"
            transcript_dir.mkdir(exist_ok=True)
            
            # Generate timestamp for filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.agent_id}_{timestamp}.json"
            filepath = transcript_dir / filename
            
            # Prepare transcript data
            transcript_data = {
                "agent_id": self.agent_id,
                "username": self.username,
                "timestamp": datetime.now().isoformat(),
                "stats": self.get_status(),
                "system_prompt": self.driver.system_prompt,
                "message_log": self.driver.message_log.copy(),
                "total_messages": len(self.driver.message_log)
            }
            
            # Save to file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(transcript_data, f, indent=2, ensure_ascii=False)
            
            print(f"[{self.agent_id}] 📝 Transcript saved to {filepath}")
            
        except Exception as e:
            print(f"[{self.agent_id}] ⚠️  Error saving transcript: {e}")
            import traceback
            traceback.print_exc()
    
    def print_transcript_summary(self) -> None:
        """Print a summary of the LLM conversation"""
        print(f"\n=== {self.agent_id.upper()} TRANSCRIPT SUMMARY ===")
        print(f"Total LLM messages: {len(self.driver.message_log)}")
        print(f"Instructions processed: {self.instructions_processed}")
        print(f"Messages sent: {self.messages_sent}")
        print(f"\nConversation flow:")
        
        for i, msg in enumerate(self.driver.message_log):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            tool_call = msg.get("tool_call")
            
            if role == "user":
                # Parse email data
                try:
                    email_data = json.loads(content)
                    from_agent = email_data.get("from", "unknown")
                    subject = email_data.get("subject", "")
                    print(f"  {i+1}. 📨 RECEIVED EMAIL from {from_agent}: {subject}")
                except:
                    print(f"  {i+1}. 📨 RECEIVED: {content[:50]}...")
                    
            elif role == "assistant":
                if tool_call:
                    print(f"  {i+1}. 🤖 LLM RESPONSE with tool calls")
                else:
                    print(f"  {i+1}. 🤖 LLM RESPONSE: {content[:50]}...")
                    
            elif role == "function":
                func_name = msg.get("name", "unknown")
                print(f"  {i+1}. 🔧 TOOL RESULT ({func_name})")
        
        print(f"=== END {self.agent_id.upper()} TRANSCRIPT ===\n")
    
    def clear_transcript(self) -> None:
        """Clear the LLM conversation transcript for a new round"""
        if self.driver:
            self.driver.message_log.clear()
        
        # Reset counters for new round
        self.instructions_processed = 0
        self.messages_sent = 0
        self.current_instruction = None
        self.can_send_reminder = False
        self.last_message_time = datetime.now()
    
    async def disconnect_gracefully(self):
        """Leave queue and close connections before shutdown."""
        try:
            # Leave queue first
            hdr = self._auth_headers()
            response = requests.post(
                f"{self.email_server_url}/leave_queue",
                headers=hdr,
                timeout=5
            )
            print(f"[{self.agent_id}] Left queue: {response.status_code}")
        except Exception as e:
            print(f"[{self.agent_id}] Error leaving queue: {e}")
        
        # Cancel WebSocket task if running
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        
        print(f"[{self.agent_id}] Disconnected gracefully")
    
    def _setup_dev_features(self):
        """Enable development-friendly features."""
        print(f"[{self.agent_id}] 🛠️  Development mode enabled")
        
        # More verbose logging
        if not hasattr(self, '_original_print'):
            self._original_print = print
            
        # Longer JWT expiry for development
        self._dev_jwt_expiry_boost = 3600  # 1 hour extra
        
        # Auto-reconnect settings
        self._auto_reconnect = True
        self._reconnect_delay = 5  # seconds
        self._max_reconnect_attempts = 10
        
        # Hot reload settings
        self._prompt_file_mtime = None
        self._check_prompt_reload = True
    
    def hot_reload_prompt(self, new_prompt_file: Optional[str] = None) -> bool:
        """Reload agent prompt without restarting.
        
        Returns True if prompt was reloaded, False otherwise.
        """
        if not self.dev_mode:
            print(f"[{self.agent_id}] Hot reload only available in dev mode")
            return False
        
        prompt_file = Path(new_prompt_file) if new_prompt_file else (
            Path(__file__).resolve().parent.parent / "docs" / "agent_prompt.md"
        )
        
        if not prompt_file.exists():
            print(f"[{self.agent_id}] Prompt file not found: {prompt_file}")
            return False
        
        try:
            # Check if file has changed
            current_mtime = prompt_file.stat().st_mtime
            if self._prompt_file_mtime and current_mtime == self._prompt_file_mtime:
                return False  # No change
            
            # Reload prompt
            new_prompt = prompt_file.read_text(encoding="utf-8")
            if self.driver:
                self.driver.system_prompt = new_prompt
                self._prompt_file_mtime = current_mtime
                print(f"[{self.agent_id}] 🔄 Prompt reloaded from {prompt_file.name}")
                return True
                
        except Exception as e:
            print(f"[{self.agent_id}] ❌ Failed to reload prompt: {e}")
            
        return False
    
    async def _dev_auto_reconnect(self):
        """Auto-reconnect logic for development mode."""
        if not self.dev_mode or not self._auto_reconnect:
            return
        
        attempts = 0
        while attempts < self._max_reconnect_attempts:
            attempts += 1
            print(f"[{self.agent_id}] 🔄 Reconnection attempt {attempts}/{self._max_reconnect_attempts}")
            
            try:
                # Re-register and rejoin
                self._register_with_server()
                self._join_queue()
                
                # Restart WebSocket
                await self._start_websocket_listener()
                
                print(f"[{self.agent_id}] ✅ Reconnected successfully!")
                return
                
            except Exception as e:
                print(f"[{self.agent_id}] ❌ Reconnection failed: {e}")
                await asyncio.sleep(self._reconnect_delay)
        
        print(f"[{self.agent_id}] ❌ Max reconnection attempts reached")


def main():
    """Main function for running an agent standalone"""
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python base_agent.py <agent_id> <username> [email_server_url] [--dev]")
        sys.exit(1)
    
    agent_id = sys.argv[1]
    username = sys.argv[2]
    email_server_url = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith('--') else "http://localhost:8000"
    dev_mode = '--dev' in sys.argv
    
    print(f"Starting agent {agent_id} ({username})")
    
    agent = CustomBaseAgent(agent_id, username, email_server_url=email_server_url, dev_mode=dev_mode)
    
    try:
        agent.run_sync()
    except KeyboardInterrupt:
        print("\nShutting down agent...")
        agent.stop()
        # Gracefully disconnect
        import asyncio
        try:
            asyncio.run(agent.disconnect_gracefully())
        except Exception as e:
            print(f"Error during graceful disconnect: {e}")


if __name__ == "__main__":
    main() 