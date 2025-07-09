"""RSA signature verification and scoring functions for the email game system"""

from typing import Dict, Any, List
import json
import base64
import httpx
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

from .config import PROJECT_ROOT


def load_agent_public_key(agent_id: str):
    """Load an agent's RSA public key from sample_agents.json"""
    try:
        agents_file = PROJECT_ROOT / "data" / "sample_agents.json"
        with open(agents_file, 'r') as f:
            data = json.load(f)
        
        # Find agent data
        for agent in data['agents']:
            if agent['id'] == agent_id:
                public_key_pem = agent['rsa_public_key']
                return serialization.load_pem_public_key(public_key_pem.encode())
        
        raise ValueError(f"Agent {agent_id} not found in sample_agents.json")
        
    except Exception as e:
        return None


def verify_rsa_signature(signed_message: Dict[str, Any], public_key) -> bool:
    """Verify an RSA signature from an agent"""
    try:
        message = signed_message["original_message"]
        signature_b64 = signed_message["signature"]
        signer = signed_message["signer"]
        signed_for = signed_message["signed_for"]
        timestamp = signed_message["timestamp"]
        signature_type = signed_message.get("signature_type", "unknown")
        
        # Check signature type
        if signature_type != "rsa_pss_sha256":
                return False
        
        # Recreate the signed data (same format as BaseAgent)
        sign_data = f"{message}|{signer}|{signed_for}|{timestamp}"
        
        # Decode signature from base64
        signature_bytes = base64.b64decode(signature_b64)
        
        # Verify RSA signature using RSA-PSS with SHA256
        public_key.verify(
            signature_bytes,
            sign_data.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return True
        
    except Exception as e:
        return False


async def process_submission_emails(agent_ids: List[str], request_lists: Dict[str, List[str]], signing_permissions: Dict[str, List[str]], agent_messages: Dict[str, str]) -> Dict[str, int]:
    """
    Process signature submissions from moderator email inbox with comprehensive validation.
    Returns dict of agent_id -> total_points
    """
    try:
        # Get all messages sent to moderator
        async with httpx.AsyncClient() as client:
            response = await client.get("http://127.0.0.1:8000/get_messages/moderator")
            
        if response.status_code != 200:
            print(f"[scoring] Failed to get moderator messages: {response.status_code}")
            return {}
            
        data = response.json()
        if not data.get("success"):
            print(f"[scoring] Failed to get moderator messages: {data}")
            return {}
            
        messages = data.get("messages", [])
        
        # ------------------------------------------------------------
        # Debug aid: show a snapshot of the first few moderator emails
        # so we can understand what the scorer is evaluating.
        # ------------------------------------------------------------
        sample_preview = messages[:5]
        if sample_preview:
            print("[scoring] Preview of moderator inbox messages (first 5):")
            for msg in sample_preview:
                sub = msg.get("subject", "<no-subject>")
                frm = msg.get("from", "<unknown>")
                ts  = msg.get("timestamp", "")
                print(f"  • {ts} | from {frm} | \"{sub}\"")
        else:
            print("[scoring] Moderator inbox is empty at scoring time.")
        
        # Detect submission emails more leniently (case-insensitive, any subject containing 'submission')
        submission_messages = [
            msg for msg in messages
            if "submission" in msg.get("subject", "").lower()
        ]
        
        print(f"[scoring] Found {len(submission_messages)} candidate submission emails out of {len(messages)} moderator messages.")
        
        # Load agent RSA public keys
        agent_public_keys = {}
        for agent_id in agent_ids:
            public_key = load_agent_public_key(agent_id)
            if public_key:
                agent_public_keys[agent_id] = public_key
            else:
                print(f"[scoring] Failed to load public key for {agent_id}")
        
        # Track scores and detailed results
        agent_scores = {agent_id: 0 for agent_id in agent_ids}
        
        # Track detailed performance for each agent
        agent_performance = {}
        for agent_id in agent_ids:
            agent_performance[agent_id] = {
                'supposed_to_request_from': request_lists.get(agent_id, []),
                'successfully_submitted_for': [],
                'authorized_to_sign_for': signing_permissions.get(agent_id, []),
                'successfully_signed_for': [],
                'submission_points': 0,
                'signing_points': 0,
                'unauthorized_signing_penalties': 0
            }
        
        processed_count = 0
        valid_submissions = 0
        
        # Track processed submissions to prevent duplicates
        processed_submissions = set()  # Will store (submitter, signer) tuples - I think we should modify this to store round number as well
        
        
        for msg in submission_messages:
            try:
                # Parse JSON submission data from email body
                submission_data = json.loads(msg["body"])
                
                # Step 1: Check if this is a submission message
                if submission_data.get("submission_type") != "signature":
                    print("[scoring] Email skipped – submission_type not 'signature'.")
                    continue
                    
                submitter = submission_data.get("submitter")
                signatures = submission_data.get("signatures", [])
                
                # Step 2: Verify submitter is valid agent
                if submitter not in agent_ids:
                    print(f"[scoring] Invalid submitter {submitter} – not in agent list.")
                    continue
                
                for signed_message in signatures:
                    processed_count += 1
                    signer = signed_message.get("signer")
                    original_message = signed_message.get("original_message", "")
                    signed_for = signed_message.get("signed_for", "")
                    
                    
                    # Step 3: Verify signer is valid agent
                    if signer not in agent_ids:
                        print(f"[scoring] Invalid signer {signer} – not in agent list.")
                        continue
                    
                    # Step 4: Verify submitter == signed_for (submitter should be requesting signature for themselves)
                    if submitter != signed_for:
                        print(f"[scoring] submitter {submitter} does not match signed_for {signed_for} – skipping.")
                        continue
                    
                    # Step 4.5: Check for duplicate submissions (prevent double-claiming)
                    submission_key = (submitter, signer)
                    if submission_key in processed_submissions:
                        print(f"[scoring] Duplicate submission ignored: {submitter}->{signer}")
                        continue
                    
                    # Step 5: Verify signed message matches the *current round's* assignment.
                    # ---------------------------------------------------------------------
                    # agent_messages only contains messages allocated for THIS round. In
                    # runtime.py we now guarantee that each agent receives a message they
                    # have never been assigned before in the session. Therefore, any
                    # attempt to resubmit a signature earned in a previous round will fail
                    # this equality check and be ignored, preventing duplicate scoring
                    # across rounds.
                    expected_message = agent_messages.get(submitter, "")
                    if original_message != expected_message:
                        print(f"[scoring] Message mismatch for {submitter}->{signer}: expected '{expected_message[:40]}...', got '{original_message[:40]}...' ")
                        continue
                    
                    # Step 6: Cryptographically verify RSA signature
                    signer_public_key = agent_public_keys.get(signer)
                    if not signer_public_key:
                        print(f"[scoring] Missing public key for signer {signer} – skipping.")
                        continue
                    
                    if not verify_rsa_signature(signed_message, signer_public_key):
                        print(f"[scoring] Signature verification FAILED for signer {signer} (submitter {submitter}).")
                        continue
                    
                    # Step 7: Check if signer was authorized to sign for submitter
                    was_authorized = submitter in signing_permissions.get(signer, [])
                    
                    # All validation passed!
                    valid_submissions += 1
                    
                    # Mark this submission as processed (prevent duplicates)
                    processed_submissions.add(submission_key)
                    
                    
                    # Award points to submitter
                    agent_scores[submitter] += 1
                    agent_performance[submitter]['submission_points'] += 1
                    agent_performance[submitter]['successfully_submitted_for'].append(signer)
                    
                    # Award/penalize signer based on authorization
                    if was_authorized:
                        agent_scores[signer] += 1
                        agent_performance[signer]['signing_points'] += 1
                        agent_performance[signer]['successfully_signed_for'].append(submitter)
                    else:
                        agent_scores[signer] -= 1
                        agent_performance[signer]['unauthorized_signing_penalties'] += 1
                        
            except (json.JSONDecodeError, KeyError) as e:
                continue
        
        
        # Store performance data for detailed reporting
        return agent_scores, agent_performance
        
    except Exception as e:
        print(f"❌ Error processing submissions: {e}")
        return {}, {}