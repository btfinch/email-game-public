"""Session persistence functions for the email game system"""

import json
from pathlib import Path
from .models import SessionResult
from .config import PROJECT_ROOT


async def save_session_results(session_result: SessionResult) -> str:
    """Save session results to JSON file"""
    
    # Create session results directory if it doesn't exist
    results_dir = PROJECT_ROOT / "session_results"
    results_dir.mkdir(exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = session_result.start_time.strftime("%Y%m%d_%H%M%S")
    filename = f"session_{session_result.session_id}_{timestamp}.json"
    filepath = results_dir / filename
    
    # Debug output
    print(f"🐛 DEBUG: PROJECT_ROOT = {PROJECT_ROOT}")
    print(f"🐛 DEBUG: results_dir = {results_dir}")
    print(f"🐛 DEBUG: results_dir.exists() = {results_dir.exists()}")
    print(f"🐛 DEBUG: filepath = {filepath}")
    print(f"🐛 DEBUG: Current working directory = {Path.cwd()}")
    
    # Save to JSON
    with open(filepath, 'w') as f:
        json.dump(session_result.to_dict(), f, indent=2)
    
    print(f"💾 Session saved: {filepath}")
    print(f"🐛 DEBUG: File exists after save = {filepath.exists()}")
    
    return str(filepath)