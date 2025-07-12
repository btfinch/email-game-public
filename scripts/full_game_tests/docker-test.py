#!/usr/bin/env python3
"""
Stage 2: Docker Locally - Complete Test Script

This script handles the full Docker workflow:
1. Starts containers
2. Waits for services to be ready
3. Runs the game test
4. Cleans up containers
"""

import asyncio
import subprocess
import sys
import time
import socket
import signal
import psutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def check_port_in_use(port: int) -> bool:
    """Check if a port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        result = sock.connect_ex(('localhost', port))
        return result == 0


def find_processes_on_port(port: int) -> list:
    """Find processes using a specific port."""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            for conn in proc.connections():
                if conn.laddr.port == port:
                    processes.append(proc)
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return processes


def kill_processes_on_ports(ports: list) -> bool:
    """Kill processes running on specified ports."""
    killed_any = False
    
    for port in ports:
        if check_port_in_use(port):
            print(f"⚠️  Port {port} is in use")
            processes = find_processes_on_port(port)
            
            for proc in processes:
                try:
                    cmdline = ' '.join(proc.cmdline()) if proc.cmdline() else proc.name()
                    print(f"  🔍 Found process: PID {proc.pid} - {cmdline}")
                    
                    # Be extra careful - only kill processes that look like our services
                    if any(keyword in cmdline.lower() for keyword in [
                        'email_server', 'dashboard', 'uvicorn', 'python -m src', 
                        'run_full_game_test', 'fastapi'
                    ]):
                        print(f"  💀 Killing process PID {proc.pid}")
                        proc.terminate()
                        
                        # Wait up to 5 seconds for graceful shutdown
                        try:
                            proc.wait(timeout=5)
                        except psutil.TimeoutExpired:
                            print(f"  💥 Force killing PID {proc.pid}")
                            proc.kill()
                        
                        killed_any = True
                    else:
                        print(f"  ⚠️  Skipping unknown process: {cmdline}")
                        print(f"      To free port {port}, manually kill PID {proc.pid}")
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    print(f"  ❌ Could not kill process: {e}")
    
    if killed_any:
        print("⏳ Waiting for ports to be freed...")
        time.sleep(3)
    
    return killed_any


def check_docker_available() -> bool:
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(['docker', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            print("❌ Docker not found. Please install Docker.")
            return False
            
        result = subprocess.run(['docker', 'info'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            print("❌ Docker daemon not running. Please start Docker.")
            return False
            
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("❌ Docker not available or not responding.")
        return False


def run_command(cmd: str, description: str = None) -> int:
    """Run a shell command and return exit code."""
    if description:
        print(f"🔧 {description}")
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ Command failed: {cmd}")
        print(f"Error: {result.stderr}")
        return result.returncode
    
    if result.stdout:
        print(result.stdout.strip())
    
    return 0


async def main():
    """Run Stage 2 Docker test with full orchestration."""
    print("🐳 Stage 2: Docker Locally - Full Test")
    print("=" * 50)
    
    # Ports we need for the test
    required_ports = [8000, 8002]
    
    try:
        # 0. Prerequisites check
        print("\n🔍 Checking prerequisites...")
        
        if not check_docker_available():
            return 1
        
        # 1. Check for port conflicts and clean up if needed
        print("\n🔍 Checking for port conflicts...")
        any_killed = kill_processes_on_ports(required_ports)
        
        # Double-check ports are free
        for port in required_ports:
            if check_port_in_use(port):
                print(f"❌ Port {port} is still in use. Please free it manually.")
                return 1
        
        if any_killed:
            print("✅ Ports cleared, ready for Docker containers")
        else:
            print("✅ All required ports are available")
        
        # 2. Stop any existing containers (in case previous run failed)
        print("\n🧹 Cleaning up any existing containers...")
        run_command("docker compose down", "Stopping existing containers")
        
        # 3. Build and start containers
        print("\n📦 Building and starting Docker containers...")
        if run_command("docker compose up -d --build", "Starting containers") != 0:
            return 1
        
        # 2. Wait a moment for containers to initialize
        print("⏳ Waiting for containers to initialize...")
        time.sleep(5)
        
        # 3. Run the actual game test
        print("\n🎮 Running game test against containerized services...")
        result = subprocess.run([
            sys.executable, "scripts/test_docker_full.py"
        ], cwd=PROJECT_ROOT)
        
        if result.returncode == 0:
            print("\n🎉 Stage 2 Docker test completed successfully!")
            print("✅ Key validations:")
            print("   • Containers started without Redis dependency")
            print("   • Agents connected to containerized services")
            print("   • Full game completed with proper networking")
            print("   • Port forwarding working correctly")
        else:
            print("\n❌ Stage 2 test failed")
            return result.returncode
            
    except KeyboardInterrupt:
        print("\n⏹️ Test interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        return 1
    finally:
        # 4. Always clean up containers
        print("\n🧹 Cleaning up containers...")
        run_command("docker compose down", "Stopping containers")
        
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))