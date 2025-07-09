#!/usr/bin/env python3
"""
Simple test script to verify OpenAI API key is working.
Loads from .env file and makes a minimal API call.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import openai

# Load environment variables
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

def test_openai_key():
    """Test if OpenAI API key works with a simple call."""
    
    # Check if key exists
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ No OPENAI_API_KEY found in .env file")
        return False
    
    # Mask key for display
    masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
    print(f"🔑 Testing API key: {masked_key}")
    
    try:
        # Initialize client
        client = openai.OpenAI(api_key=api_key)
        
        # Make minimal API call
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say 'API test successful'"}],
            max_tokens=10
        )
        
        result = response.choices[0].message.content.strip()
        print(f"✅ API call successful: {result}")
        return True
        
    except openai.AuthenticationError as e:
        print(f"❌ Authentication failed: {e}")
        print("   Check your API key at: https://platform.openai.com/account/api-keys")
        return False
    except openai.RateLimitError as e:
        print(f"⚠️  Rate limit exceeded: {e}")
        print("   Your key works but you've hit rate limits")
        return True  # Key is valid
    except Exception as e:
        print(f"❌ API call failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 OpenAI API Key Test")
    print("=" * 30)
    
    success = test_openai_key()
    sys.exit(0 if success else 1) 