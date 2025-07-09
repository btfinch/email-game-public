"""Session persistence functions for the email game system"""

import json
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
    
    # Save to JSON
    with open(filepath, 'w') as f:
        json.dump(session_result.to_dict(), f, indent=2)
    
    print(f"💾 Session saved: {filepath}")
    return str(filepath)