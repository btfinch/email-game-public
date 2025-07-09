#!/usr/bin/env python3
"""
Example script showing how to use both original BaseAgent and CustomBaseAgent
"""

import sys
from pathlib import Path

# Add src to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from base_agent import BaseAgent
from custom_base_agent import CustomBaseAgent

def main():
    print("🧪 Testing Original vs Custom Agent")
    print("=" * 50)
    
    # You can create both types of agents
    # Original agent (unchanged behavior)
    print("📦 Creating original BaseAgent...")
    original_agent = BaseAgent(
        agent_id="original_test", 
        username="OriginalAgent",
        email_server_url="http://localhost:8000"
    )
    
    # Custom agent (with your modifications)
    print("🔧 Creating CustomBaseAgent...")
    custom_agent = CustomBaseAgent(
        agent_id="custom_test",
        username="CustomAgent", 
        email_server_url="http://localhost:8000"
    )
    
    print("\n✅ Both agents created successfully!")
    print("\n📝 To modify message processing:")
    print("   Edit: src/custom_llm_driver.py")
    print("   Function: CustomLLMDriver.on_email()")
    print("\n🚀 To run agents:")
    print("   Original: python -m src.base_agent test1 TestAgent1")
    print("   Custom:   python -m src.custom_base_agent test2 TestAgent2")

if __name__ == "__main__":
    main() 