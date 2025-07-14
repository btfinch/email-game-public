#!/usr/bin/env python3
"""
Debug script to test transcript saving logic and identify path issues.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def test_transcript_saving():
    """Test the transcript saving logic with debug output."""
    print("🧪 Testing transcript saving logic")
    print("=" * 50)
    
    # Test 1: Check current working directory
    print(f"📁 Current working directory: {Path.cwd()}")
    print(f"📁 Script location: {Path(__file__).resolve()}")
    print(f"📁 Computed PROJECT_ROOT: {PROJECT_ROOT}")
    
    # Test 2: Replicate the BaseAgent path logic
    print("\n🔍 Testing BaseAgent path logic:")
    
    # This mimics how BaseAgent calculates the path
    base_agent_file = PROJECT_ROOT / "src" / "base_agent.py"
    print(f"📄 BaseAgent file path: {base_agent_file}")
    print(f"📄 BaseAgent file exists: {base_agent_file.exists()}")
    
    if base_agent_file.exists():
        # This is exactly what BaseAgent does: parents[1] from base_agent.py
        project_root_from_base_agent = base_agent_file.resolve().parents[1]
        print(f"📁 Project root from BaseAgent logic: {project_root_from_base_agent}")
        transcript_dir_from_base_agent = project_root_from_base_agent / "transcripts"
        print(f"📁 Transcript dir from BaseAgent logic: {transcript_dir_from_base_agent}")
    
    # Test 3: Try to create transcript directory and file
    print("\n💾 Testing transcript creation:")
    
    # Use the same logic as BaseAgent
    try:
        if base_agent_file.exists():
            project_root = base_agent_file.resolve().parents[1]
        else:
            project_root = PROJECT_ROOT
            
        transcript_dir = project_root / "transcripts"
        print(f"📁 Target transcript directory: {transcript_dir}")
        print(f"📁 Absolute path: {transcript_dir.resolve()}")
        
        # Create directory
        transcript_dir.mkdir(exist_ok=True)
        print(f"✅ Directory created/exists: {transcript_dir.exists()}")
        
        # Create test file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"debug_test_{timestamp}.json"
        filepath = transcript_dir / filename
        
        test_data = {
            "agent_id": "debug_agent",
            "username": "Debug Test",
            "timestamp": datetime.now().isoformat(),
            "test_message": "This is a debug transcript test",
            "script_location": str(Path(__file__).resolve()),
            "working_directory": str(Path.cwd()),
            "computed_project_root": str(PROJECT_ROOT),
            "computed_transcript_dir": str(transcript_dir)
        }
        
        print(f"💾 Attempting to save to: {filepath}")
        print(f"💾 Absolute file path: {filepath.resolve()}")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(test_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Test file saved successfully!")
        print(f"📄 File exists: {filepath.exists()}")
        print(f"📄 File size: {filepath.stat().st_size} bytes")
        
        # List all files in transcript directory
        print(f"\n📋 Files in transcript directory:")
        if transcript_dir.exists():
            files = list(transcript_dir.glob("*.json"))
            print(f"   Found {len(files)} JSON files:")
            for f in files:
                stat = f.stat()
                print(f"   • {f.name} ({stat.st_size} bytes, modified: {datetime.fromtimestamp(stat.st_mtime)})")
        else:
            print("   Directory doesn't exist!")
        
        return filepath
        
    except Exception as e:
        print(f"❌ Error during transcript test: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_permissions():
    """Test file system permissions."""
    print("\n🔐 Testing file system permissions:")
    
    test_locations = [
        PROJECT_ROOT,
        PROJECT_ROOT / "transcripts",
        Path.cwd(),
        Path("/tmp")  # Known writable location
    ]
    
    for location in test_locations:
        try:
            if location.exists():
                # Test write permission
                test_file = location / "permission_test.tmp"
                with open(test_file, 'w') as f:
                    f.write("test")
                test_file.unlink()  # Delete test file
                print(f"✅ {location}: Writable")
            else:
                print(f"❌ {location}: Doesn't exist")
        except Exception as e:
            print(f"❌ {location}: Not writable ({e})")

def check_environment():
    """Check environment and system info."""
    print("\n🖥️  Environment information:")
    print(f"🐍 Python executable: {sys.executable}")
    print(f"👤 User: {Path.home()}")
    
    # Check for any environment variables that might affect paths
    import os
    relevant_vars = ['HOME', 'USER', 'PWD', 'TMPDIR']
    for var in relevant_vars:
        value = os.environ.get(var, 'Not set')
        print(f"🔧 {var}: {value}")

def main():
    """Run all debug tests."""
    check_environment()
    test_permissions()
    test_file = test_transcript_saving()
    
    if test_file:
        print(f"\n🎉 Debug test completed successfully!")
        print(f"📄 Test file created at: {test_file}")
        print(f"\n💡 If this worked but agent transcripts don't appear,")
        print(f"   the issue is likely in the BaseAgent save_transcript() method")
        print(f"   or the silent exception handling.")
    else:
        print(f"\n❌ Debug test failed - there's a fundamental issue with file creation")

if __name__ == "__main__":
    main()