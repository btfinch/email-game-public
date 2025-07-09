#!/usr/bin/env python3
"""
The Email Game Developer CLI
A command-line interface for developers to easily interact with The Email Game.
"""

import click
import asyncio
import os
import sys
import json
import requests
import subprocess
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config_manager import ConfigManager


@click.group()
@click.pass_context
def cli(ctx):
    """The Email Game developer tools for building and testing agents."""
    ctx.ensure_object(dict)
    ctx.obj['config'] = ConfigManager()


@cli.command()
@click.option('--agent-id', '-a', default=None, help='Agent ID (defaults to config or generates one)')
@click.option('--username', '-u', default=None, help='Agent username (defaults to agent ID)')
@click.option('--server', '-s', default=None, help='Server URL (defaults to config)')
@click.pass_context
def join(ctx, agent_id, username, server):
    """Join the live game queue with your agent."""
    config = ctx.obj['config']
    
    # Resolve parameters with defaults
    server_url = server or config.get_server_url()
    if not server_url:
        click.echo("❌ No server URL provided. Use --server or run 'arena config'")
        return
    
    if not agent_id:
        agent_id = config.get_agent_id() or f"dev_{int(time.time())}"
        click.echo(f"📝 Using agent ID: {agent_id}")
    
    username = username or agent_id.title()
    
    click.echo(f"🤖 Joining queue as {agent_id} ({username})...")
    click.echo(f"🌐 Server: {server_url}")
    
    # Check OpenAI key
    if not os.getenv('OPENAI_API_KEY'):
        click.echo("❌ OPENAI_API_KEY not set!")
        return
    
    # Start the agent
    try:
        subprocess.run([
            sys.executable, "-m", "src.base_agent",
            agent_id, username, server_url
        ], cwd=PROJECT_ROOT)
    except KeyboardInterrupt:
        click.echo("\n⏹️  Agent disconnected")


@cli.command()
@click.option('--server', '-s', default=None, help='Server URL')
@click.option('--watch', '-w', is_flag=True, help='Watch queue status continuously')
@click.pass_context
def status(ctx, server, watch):
    """Show current queue status and game progress."""
    config = ctx.obj['config']
    server_url = server or config.get_server_url()
    
    if not server_url:
        click.echo("❌ No server URL provided. Use --server or run 'arena config'")
        return
    
    def show_status():
        try:
            response = requests.get(f"{server_url}/queue_status", timeout=5)
            if response.status_code == 200:
                data = response.json()
                
                click.clear()
                click.echo("📊 Inbox Arena Queue Status")
                click.echo("=" * 40)
                click.echo(f"🌐 Server: {server_url}")
                click.echo(f"⏰ Time: {datetime.now().strftime('%H:%M:%S')}")
                click.echo()
                
                if data['game_in_progress']:
                    click.echo("🎮 Game Status: IN PROGRESS")
                else:
                    click.echo("🎮 Game Status: Waiting for players")
                
                click.echo(f"👥 Queue Length: {data['queue_length']}/4")
                
                if data['agents_waiting']:
                    click.echo("📋 Agents in Queue:")
                    for agent in data['agents_waiting']:
                        click.echo(f"   • {agent}")
                
                if data['connected_agents']:
                    click.echo(f"\n🔗 Connected Agents: {len(data['connected_agents'])}")
                    for agent in data['connected_agents']:
                        click.echo(f"   • {agent}")
                
                # Check for recent games
                try:
                    results_response = requests.get(f"{server_url}/session_results", timeout=5)
                    if results_response.status_code == 200:
                        results = results_response.json()
                        if results.get('files'):
                            click.echo("\n📜 Recent Games:")
                            for i, file_info in enumerate(results['files'][:3]):
                                timestamp = datetime.fromtimestamp(file_info['modified'])
                                click.echo(f"   • {timestamp.strftime('%H:%M')} - {file_info['filename']}")
                except:
                    pass
                    
            else:
                click.echo(f"❌ Failed to get status: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            click.echo("❌ Cannot connect to server")
        except Exception as e:
            click.echo(f"❌ Error: {e}")
    
    if watch:
        click.echo("👀 Watching queue status (Ctrl+C to stop)...")
        try:
            while True:
                show_status()
                time.sleep(2)
        except KeyboardInterrupt:
            click.echo("\n⏹️  Stopped watching")
    else:
        show_status()


@cli.command()
@click.option('--against', default='base', help='Opponents: base, smart, or mixed')
@click.option('--rounds', default=3, help='Number of rounds to play')
@click.option('--agent-path', default=None, help='Path to custom agent module')
@click.pass_context
def local_game(ctx, against, rounds, agent_path):
    """Start a local game against base agents."""
    click.echo("🎮 Starting local game...")
    click.echo(f"🤖 Opponents: {against} agents")
    click.echo(f"🏁 Rounds: {rounds}")
    
    if agent_path:
        click.echo(f"📂 Using custom agent: {agent_path}")
    
    # Start local server
    click.echo("\n⚡ Starting local email server...")
    server_process = subprocess.Popen([
        sys.executable, "-m", "src.email_server"
    ], cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait for server to start
    time.sleep(3)
    
    try:
        # Start base agents
        agent_processes = []
        base_agents = ['alice', 'bob', 'charlie']
        
        click.echo("🤖 Starting base agents...")
        for agent_id in base_agents:
            process = subprocess.Popen([
                sys.executable, "-m", "src.base_agent",
                agent_id, agent_id.title()
            ], cwd=PROJECT_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            agent_processes.append(process)
            click.echo(f"   • Started {agent_id}")
            time.sleep(1)
        
        # Start player agent
        if agent_path:
            click.echo(f"\n🎯 Starting your agent from {agent_path}...")
            # TODO: Import and run custom agent
        else:
            click.echo("\n🎯 Starting your agent...")
            player_process = subprocess.Popen([
                sys.executable, "-m", "src.base_agent",
                "player", "Player"
            ], cwd=PROJECT_ROOT)
            
            try:
                player_process.wait()
            except KeyboardInterrupt:
                player_process.terminate()
        
    finally:
        # Cleanup
        click.echo("\n🧹 Cleaning up...")
        for process in agent_processes:
            process.terminate()
        server_process.terminate()
        
        # Wait for processes to end
        time.sleep(1)
        click.echo("✅ Local game ended")


@cli.command()
@click.option('--server', prompt='Server URL', help='Inbox Arena server URL')
@click.option('--agent-id', prompt='Default agent ID', default=lambda: f"dev_{os.getenv('USER', 'agent')}", help='Your default agent ID')
@click.option('--global', 'is_global', is_flag=True, help='Save to global config')
@click.pass_context
def config(ctx, server, agent_id, is_global):
    """Configure server URL and default settings."""
    config_manager = ctx.obj['config']
    
    config_data = {
        'server_url': server.rstrip('/'),
        'agent_id': agent_id,
        'configured_at': datetime.now().isoformat()
    }
    
    if is_global:
        config_path = Path.home() / '.inbox_arena' / 'config.json'
    else:
        config_path = Path('./agent_config.json')
    
    config_manager.save_config(config_data, config_path)
    
    click.echo("✅ Configuration saved!")
    click.echo(f"📝 Server: {config_data['server_url']}")
    click.echo(f"🤖 Agent ID: {config_data['agent_id']}")
    click.echo(f"💾 Saved to: {config_path}")


@cli.command()
@click.option('--file', '-f', default=None, help='Session result file to analyze')
@click.option('--latest', is_flag=True, help='Analyze the latest game')
@click.pass_context
def analyze(ctx, file, latest):
    """Analyze game results and performance."""
    config = ctx.obj['config']
    server_url = config.get_server_url()
    
    if not server_url and not file:
        click.echo("❌ No server URL provided. Use --server or provide --file")
        return
    
    session_data = None
    
    if file:
        # Load from local file
        file_path = Path(file)
        if not file_path.exists():
            click.echo(f"❌ File not found: {file}")
            return
        with open(file_path) as f:
            session_data = json.load(f)
    elif latest or server_url:
        # Fetch from server
        try:
            response = requests.get(f"{server_url}/session_results", timeout=5)
            if response.status_code == 200:
                results = response.json()
                if results.get('files'):
                    latest_file = results['files'][0]
                    
                    # Fetch the actual data
                    data_response = requests.get(
                        f"{server_url}/session_results/{latest_file['filename']}", 
                        timeout=5
                    )
                    if data_response.status_code == 200:
                        session_data = data_response.json()['data']
                    else:
                        click.echo("❌ Failed to fetch session data")
                        return
                else:
                    click.echo("❌ No game results found on server")
                    return
        except Exception as e:
            click.echo(f"❌ Error fetching results: {e}")
            return
    
    if not session_data:
        click.echo("❌ No session data to analyze")
        return
    
    # Analyze the session
    click.echo("\n📊 Game Analysis")
    click.echo("=" * 50)
    click.echo(f"🎮 Session ID: {session_data.get('session_id', 'Unknown')}")
    click.echo(f"🏁 Total Rounds: {session_data.get('total_rounds', 0)}")
    
    if 'cumulative_scores' in session_data:
        click.echo("\n🏆 Final Scores:")
        scores = session_data['cumulative_scores']
        sorted_agents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        for rank, (agent_id, score) in enumerate(sorted_agents, 1):
            medal = ['🥇', '🥈', '🥉'][rank-1] if rank <= 3 else f'{rank}.'
            click.echo(f"   {medal} {agent_id}: {score} points")
    
    if 'performance_trends' in session_data:
        click.echo("\n📈 Performance Trends:")
        trends = session_data['performance_trends']
        
        for agent_id, scores in trends.items():
            trend = "📈" if scores[-1] > scores[0] else "📉" if scores[-1] < scores[0] else "➡️"
            click.echo(f"   {agent_id}: {' → '.join(map(str, scores))} {trend}")
    
    # Detailed round analysis
    if 'rounds' in session_data and session_data['rounds']:
        click.echo("\n🎯 Round Details:")
        for round_data in session_data['rounds']:
            round_num = round_data.get('round_number', '?')
            total_messages = round_data.get('total_messages', 0)
            click.echo(f"\n   Round {round_num}: {total_messages} messages")
            
            if 'agent_scores' in round_data:
                for agent, score in round_data['agent_scores'].items():
                    click.echo(f"      • {agent}: {score} points")


@cli.command()
@click.pass_context
def version(ctx):
    """Show version information."""
    click.echo("Inbox Arena CLI v0.1.0")
    click.echo("Python " + sys.version.split()[0])
    click.echo(f"Project root: {PROJECT_ROOT}")


if __name__ == '__main__':
    cli()