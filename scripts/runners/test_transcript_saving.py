#!/usr/bin/env python3
"""
Test script to verify that runner.py now saves agent transcripts.
"""

import subprocess
import sys
import time
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def count_transcripts():
    """Count transcript files in the transcripts directory."""
    transcript_dir = PROJECT_ROOT / "transcripts"
    if not transcript_dir.exists():
        return 0
    return len(list(transcript_dir.glob("*.json")))

def get_latest_transcripts(count=4):
    """Get the N most recent transcript files."""
    transcript_dir = PROJECT_ROOT / "transcripts"
    if not transcript_dir.exists():
        return []
    
    files = list(transcript_dir.glob("*.json"))
    # Sort by modification time (newest first)
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files[:count]

def main():
    print("🧪 Testing transcript saving with modified runner.py")
    print("=" * 50)
    
    # Record initial transcript count
    initial_count = count_transcripts()
    print(f"📝 Initial transcript count: {initial_count}")
    
    # Run the runner with --local flag (shorter test)
    print("\n🚀 Starting runner.py with --local flag...")
    print("   (This will start 4 agents and run a game)")
    print("   Press Ctrl+C after ~30 seconds to test graceful shutdown\n")
    
    runner_path = PROJECT_ROOT / "scripts" / "runners" / "runner.py"
    
    try:
        # Start the runner
        process = subprocess.Popen([
            sys.executable, str(runner_path), "--local"
        ], cwd=PROJECT_ROOT)
        
        # Let it run for a bit
        print("⏳ Letting agents connect and start game...")
        time.sleep(30)
        
        print("\n🛑 Sending interrupt to test graceful shutdown...")
        process.terminate()
        
        # Wait for graceful shutdown
        print("⏳ Waiting for graceful shutdown and transcript saving...")
        try:
            process.wait(timeout=10)
            print("✅ Runner stopped gracefully")
        except subprocess.TimeoutExpired:
            print("⚠️  Runner didn't stop in time, force killing...")
            process.kill()
            process.wait()
    
    except KeyboardInterrupt:
        print("\n⏹️  Test interrupted by user")
        if 'process' in locals():
            process.terminate()
            process.wait()
    
    # Check transcript count
    print("\n📊 Checking results...")
    time.sleep(2)  # Give a moment for files to be written
    
    final_count = count_transcripts()
    new_transcripts = final_count - initial_count
    
    print(f"📝 Final transcript count: {final_count}")
    print(f"✨ New transcripts created: {new_transcripts}")
    
    if new_transcripts > 0:
        print("\n🎉 Success! Agent transcripts were saved!")
        print("\n📄 Latest transcript files:")
        
        latest_files = get_latest_transcripts(new_transcripts)
        for f in latest_files:
            # Try to read and show basic info
            try:
                with open(f, 'r') as file:
                    data = json.load(file)
                    agent_id = data.get('agent_id', 'unknown')
                    msg_count = data.get('total_messages', 0)
                    print(f"   • {f.name} - Agent: {agent_id}, Messages: {msg_count}")
            except:
                print(f"   • {f.name}")
    else:
        print("\n⚠️  No new transcripts were created")
        print("   This might mean the agents didn't have time to connect")
        print("   or there was an issue with the graceful shutdown")
    
    print("\n💡 You can check the transcripts directory at:")
    print(f"   {PROJECT_ROOT / 'transcripts'}")

if __name__ == "__main__":
    main()