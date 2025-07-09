"""
Configuration management for The Email Game.
Handles server URLs, agent IDs, and other settings across different environments.
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any


class ConfigManager:
    """Manages configuration for The Email Game agents and CLI tools."""
    
    def __init__(self):
        self.config_paths = [
            Path.home() / ".inbox_arena" / "config.json",  # Global config
            Path("./agent_config.json"),                   # Project config
            Path("./.env")                                  # Environment file
        ]
    
    def get_server_url(self) -> Optional[str]:
        """Get server URL with priority: env > local config > global config."""
        # Check environment variable first
        env_url = os.getenv("INBOX_ARENA_SERVER")
        if env_url:
            return env_url
        
        # Check config files
        for config_path in self.config_paths[:-1]:  # Skip .env
            if config_path.exists():
                try:
                    with open(config_path) as f:
                        config = json.load(f)
                        if 'server_url' in config:
                            return config['server_url']
                except Exception:
                    continue
        
        # Check for production server in environment
        if os.getenv("INBOX_ARENA_PROD"):
            return "https://inbox-arena-owk4jthsnq-uc.a.run.app"
        
        return None
    
    def get_agent_id(self) -> Optional[str]:
        """Get default agent ID from config."""
        # Check environment variable first
        env_id = os.getenv("INBOX_ARENA_AGENT_ID")
        if env_id:
            return env_id
        
        # Check config files
        for config_path in self.config_paths[:-1]:  # Skip .env
            if config_path.exists():
                try:
                    with open(config_path) as f:
                        config = json.load(f)
                        if 'agent_id' in config:
                            return config['agent_id']
                except Exception:
                    continue
        
        return None
    
    def save_config(self, config: Dict[str, Any], path: Optional[Path] = None) -> None:
        """Save configuration to specified path or default local config."""
        if path is None:
            path = Path("./agent_config.json")
        
        # Create directory if needed
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing config if it exists
        existing_config = {}
        if path.exists():
            try:
                with open(path) as f:
                    existing_config = json.load(f)
            except Exception:
                pass
        
        # Merge configurations
        existing_config.update(config)
        
        # Save updated config
        with open(path, 'w') as f:
            json.dump(existing_config, f, indent=2)
    
    def load_all_configs(self) -> Dict[str, Dict[str, Any]]:
        """Load all available configurations for debugging."""
        configs = {}
        
        # Environment variables
        configs['environment'] = {
            'INBOX_ARENA_SERVER': os.getenv('INBOX_ARENA_SERVER'),
            'INBOX_ARENA_AGENT_ID': os.getenv('INBOX_ARENA_AGENT_ID'),
            'OPENAI_API_KEY': '***' if os.getenv('OPENAI_API_KEY') else None,
        }
        
        # Config files
        for config_path in self.config_paths[:-1]:
            if config_path.exists():
                try:
                    with open(config_path) as f:
                        configs[str(config_path)] = json.load(f)
                except Exception as e:
                    configs[str(config_path)] = {'error': str(e)}
        
        return configs