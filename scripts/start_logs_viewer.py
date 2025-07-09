#!/usr/bin/env python3
"""
Start The Email Game Logs Viewer

This script starts the logs viewer web interface for browsing game session logs.
Runs on port 8003 to avoid conflicts with the email server (8000) and dashboard (8002).
"""

import sys
from pathlib import Path

# Add src directory to path so we can import the logs viewer
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root / "src"))

from logs_viewer import create_logs_viewer_app
import uvicorn

if __name__ == "__main__":
    print("=" * 60)
    print("🏟️  INBOX ARENA LOGS VIEWER")
    print("=" * 60)
    print()
    print("Starting logs viewer...")
    print("📋 View all game sessions: http://localhost:8003")
    print()
    print("Note: This runs on port 8003 to avoid conflicts with:")
    print("  📧 Email Server: http://localhost:8000")
    print("  📊 Dashboard: http://localhost:8002")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    
    try:
        app = create_logs_viewer_app()
        uvicorn.run(app, host="127.0.0.1", port=8003)
    except KeyboardInterrupt:
        print("\n🛑 Logs viewer stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting logs viewer: {e}")
        sys.exit(1)