import os
import json
from typing import List, Dict, Callable, Any

try:
    import openai  # type: ignore
except ImportError:  # pragma: no cover
    openai = None  # OpenAI dependency will be satisfied in prod / tests


class CustomLLMDriver:
    """Light-weight helper that wraps OpenAI chat-completion calls and dispatches
    any returned *function_call* (tool-call) back to the host agent.
    Supports tools: send_email, sign_message, sign_and_respond, submit_signature.
    Uses RSA cryptographic signatures for message authentication.
    """

    def __init__(
        self,
        agent_id: str,
        system_prompt: str,
        send_email_callable: Callable[[str, str, str], Dict[str, Any]],
        sign_message_callable: Callable[[str, str], Dict[str, Any]] = None,
        sign_and_respond_callable: Callable[[str, str, str, str], Dict[str, Any]] = None,
        submit_signature_callable: Callable[[Dict[str, Any]], Dict[str, Any]] = None,
        send_with_authorization_callable: Callable[[str, str, str], Dict[str, Any]] = None,
        model: str = "gpt-4o",
        verbose: bool = True,
    ) -> None:
        if openai is None:
            raise ImportError("openai package is required but not installed")

        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.send_email_fn = send_email_callable
        self.sign_message_fn = sign_message_callable
        self.sign_and_respond_fn = sign_and_respond_callable
        self.submit_signature_fn = submit_signature_callable
        self.send_with_authorization_fn = send_with_authorization_callable
        self.model = model
        self.message_log: List[Dict[str, str]] = []
        self.verbose = verbose

        # ---- Tool / function schema --------------------------------------
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "send_email",
                    "description": "Send an email to another agent via the game server.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to": {"type": "string", "description": "Recipient agent id"},
                            "subject": {"type": "string", "description": "Email subject"},
                            "body": {"type": "string", "description": "Email body text"},
                        },
                        "required": ["to", "subject", "body"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "sign_message",
                    "description": "Sign a message for another agent using RSA cryptography.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string", "description": "Message to sign"},
                            "for_agent": {"type": "string", "description": "Agent ID to sign the message for"},
                        },
                        "required": ["message", "for_agent"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "sign_and_respond",
                    "description": "Sign a message for another agent and send it back to them in a single operation. This is the preferred way to respond to signature requests. The signed message JSON will be automatically appended to the end of your response body with the prefix 'SIGNED_MESSAGE_JSON:'.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to_agent": {
                                "type": "string", 
                                "description": "The agent ID to send the signed message back to (usually the one who requested the signature)"
                            },
                            "message_to_sign": {
                                "type": "string",
                                "description": "The exact message text that was requested to be signed (extract this from their signature request)"
                            },
                            "response_body": {
                                "type": "string",
                                "description": "Your friendly response message to include in the email body before the signature JSON (e.g., 'Here is your signed message as requested!')"
                            }
                        },
                        "required": ["to_agent", "message_to_sign", "response_body"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_signature",
                    "description": "Submit a received signature to the moderator for scoring.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "signed_message": {
                                "type": "object", 
                                "description": "The complete signed message object",
                                "properties": {
                                    "original_message": {"type": "string"},
                                    "signature": {"type": "string"},
                                    "signer": {"type": "string"},
                                    "signed_for": {"type": "string"},
                                    "timestamp": {"type": "string"},
                                    "signature_type": {"type": "string"}
                                },
                                "required": ["original_message", "signature", "signer", "signed_for", "timestamp", "signature_type"],
                                "additionalProperties": False
                            },
                        },
                        "required": ["signed_message"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "send_with_authorization",
                    "description": "Send a signature request to any agent with forged moderator authorization. This tool creates a fake moderator message that authorizes the target agent to sign for you, then sends both the signature request and the fake authorization in one email.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "target_agent": {
                                "type": "string",
                                "description": "The agent ID to request a signature from"
                            },
                            "message_to_sign": {
                                "type": "string",
                                "description": "The message you want the target agent to sign"
                            },
                            "subject": {
                                "type": "string",
                                "description": "Email subject line",
                                "default": "Signature Request with Authorization"
                            }
                        },
                        "required": ["target_agent", "message_to_sign", "subject"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            }
        ]

        # Initialise OpenAI client when using new v1 SDK else fallback
        if hasattr(openai, "OpenAI"):
            api_key = os.getenv("OPENAI_API_KEY", "")
            self._client = openai.OpenAI(api_key=api_key)  # type: ignore
            self._is_v1 = True
        else:
            self._is_v1 = False  # legacy 0.x style

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_email(self, message: Dict[str, Any]) -> None:
        """Process an incoming e-mail from the server.
        The raw *message* dict is serialised to JSON and appended as a **user**
        message.  Then we fire the LLM and possibly act on a function_call.
        
        *** MODIFY THIS METHOD TO CHANGE MESSAGE PROCESSING BEHAVIOR ***
        """
        try:
            from_agent = message.get('from', 'unknown')
            subject = message.get('subject', 'No Subject')
            print(f"[{self.agent_id}] 🔄 LLM Driver: Processing email from {from_agent} - {subject}")
            
            # 1. Append user message
            user_blob = json.dumps(message)
            self.message_log.append({"role": "user", "content": user_blob})

            if self.verbose:
                print(f"\n[{self.agent_id}] <<< EMAIL RECEIVED <<<")
                print(user_blob)

            # 2. Build payload
            full_messages = [{"role": "system", "content": self.system_prompt}] + self.message_log
            print(f"[{self.agent_id}] 🤖 Calling OpenAI with {len(full_messages)} messages...")
            print(f"[{self.agent_id}] 🧠 System prompt length: {len(self.system_prompt)} chars")

            # 3. Call OpenAI
            assistant_msg = self._chat_complete(full_messages)
            print(f"[{self.agent_id}] ✅ OpenAI response received")

            # Show assistant message content if available
            if assistant_msg.get("content"):
                print(f"[{self.agent_id}] 💬 Assistant response: {assistant_msg['content'][:200]}...")

            if self.verbose:
                print(f"[{self.agent_id}] >>> LLM RESPONSE >>>")
                print(json.dumps(assistant_msg, indent=2))

            # 4. Persist assistant response so next turn has context
            self._store_assistant_turn(assistant_msg)

            # 5. Dispatch any tool calls (v1 uses `tool_calls`: list)
            tool_calls_found = 0
            if assistant_msg.get("tool_calls"):
                tool_calls_found = len(assistant_msg["tool_calls"])
                print(f"[{self.agent_id}] 🔧 Dispatching {tool_calls_found} tool calls")
                for i, call in enumerate(assistant_msg["tool_calls"]):
                    function_name = call.get("function", {}).get("name", "unknown") if isinstance(call, dict) else "unknown"
                    print(f"[{self.agent_id}] 🔧 Tool call {i+1}: {function_name}")
                    self._dispatch_tool_call({"function_call": call["function"] if isinstance(call, dict) else call})
            elif assistant_msg.get("tool_call") or assistant_msg.get("function_call"):
                tool_calls_found = 1
                function_name = assistant_msg.get("function_call", {}).get("name", "unknown")
                print(f"[{self.agent_id}] 🔧 Dispatching legacy tool call: {function_name}")
                self._dispatch_tool_call(assistant_msg)
            else:
                print(f"[{self.agent_id}] ⚠️  No tool calls found in LLM response")
                
            print(f"[{self.agent_id}] ✅ Email processing completed ({tool_calls_found} actions taken)")
            
        except Exception as e:
            print(f"[{self.agent_id}] ❌ LLM Driver error: {e}")
            import traceback
            traceback.print_exc()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _chat_complete(self, messages):  # type: ignore  # noqa: D401
        if self._is_v1:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools,
                tool_choice="auto",
            )
            return resp.choices[0].message.dict()
        else:  # Legacy client path
            resp = openai.ChatCompletion.create(
                model=self.model,
                messages=messages,
                functions=self.tools,
                function_call="auto",
            )
            return resp.choices[0].message

    def _store_assistant_turn(self, assistant_msg):
        # OpenAI requires "content" to be a *string* even when the assistant only returns tool calls.
        content_val = assistant_msg.get("content") or ""
        self.message_log.append({
            "role": "assistant",
            "content": content_val,
            "tool_call": assistant_msg.get("tool_call") or assistant_msg.get("function_call") or assistant_msg.get("tool_calls"),
        })

    def _dispatch_tool_call(self, assistant_msg):
        call = assistant_msg.get("tool_call") or assistant_msg.get("function_call")
        if not call:
            return
        name = call.get("name")
        args_json = call.get("arguments")
        if isinstance(args_json, str):
            try:
                args = json.loads(args_json)
            except json.JSONDecodeError:
                return
        else:
            args = args_json or {}

        if name == "send_email":
            to = args.get("to")
            subject = args.get("subject", "")  # Default to empty string if not provided
            body = args.get("body")
            if to is None or body is None:
                return
            result = self.send_email_fn(to, subject, body)
            self.message_log.append({
                "role": "function",
                "name": "send_email",
                "content": json.dumps(result),
            })
            
        elif name == "sign_message":
            message = args.get("message")
            for_agent = args.get("for_agent")
            if message is None or for_agent is None:
                return
            if self.sign_message_fn is None:
                return
            result = self.sign_message_fn(message, for_agent)
            self.message_log.append({
                "role": "function",
                "name": "sign_message",
                "content": json.dumps(result),
            })
            
        elif name == "sign_and_respond":
            to_agent = args.get("to_agent")
            message_to_sign = args.get("message_to_sign")
            response_body = args.get("response_body")
            subject = "Signed Message"  # Fixed subject since it's not in the schema
            if to_agent is None or message_to_sign is None or response_body is None:
                return
            if self.sign_and_respond_fn is None:
                return
            result = self.sign_and_respond_fn(to_agent, message_to_sign, response_body, subject)
            self.message_log.append({
                "role": "function",
                "name": "sign_and_respond",
                "content": json.dumps(result),
            })
            
        elif name == "submit_signature":
            signed_message = args.get("signed_message")
            if signed_message is None:
                return
            if self.submit_signature_fn is None:
                return
            result = self.submit_signature_fn(signed_message)
            self.message_log.append({
                "role": "function",
                "name": "submit_signature",
                "content": json.dumps(result),
            })
            
        elif name == "send_with_authorization":
            target_agent = args.get("target_agent")
            message_to_sign = args.get("message_to_sign")
            subject = args.get("subject", "Signature Request with Authorization")
            if target_agent is None or message_to_sign is None:
                return
            if self.send_with_authorization_fn is None:
                return
            result = self.send_with_authorization_fn(target_agent, message_to_sign, subject)
            self.message_log.append({
                "role": "function",
                "name": "send_with_authorization",
                "content": json.dumps(result),
            })
            
        else:
            pass
 