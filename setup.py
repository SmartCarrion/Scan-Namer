#!/usr/bin/env python3
# setup.py - Quick setup helper for Scan Namer Agent

import os
import sys
import subprocess
from pathlib import Path

def check_python_version():
    """Check if Python version is 3.8+"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("ERROR: Python 3.8 or higher is required.")
        print(f"Current version: {sys.version}")
        return False
    return True

def create_virtual_env():
    """Create a virtual environment if it doesn't exist"""
    venv_path = Path("venv")
    if venv_path.exists():
        print("Virtual environment already exists.")
        return True
    
    print("Creating virtual environment...")
    try:
        subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
        print("Virtual environment created successfully.")
        
        # Verify the virtual environment was created properly
        if verify_venv():
            return True
        else:
            print("WARNING: Virtual environment may not have been created correctly.")
            print("Will attempt to continue anyway...")
            return True
    except subprocess.CalledProcessError as e:
        print(f"Error creating virtual environment: {e}")
        print("\nAlternative setup:")
        print("1. Create virtual environment manually: python -m venv venv")
        print("2. Activate it:")
        if os.name == "nt":  # Windows
            print("   venv\\Scripts\\activate")
        else:  # Unix/MacOS
            print("   source venv/bin/activate")
        print("3. Install dependencies: pip install -r requirements.txt")
        return False

def verify_venv():
    """Verify that the virtual environment was created correctly"""
    if os.name == "nt":  # Windows
        activate_script = Path("venv/Scripts/activate")
        python_exe = Path("venv/Scripts/python.exe")
    else:  # Unix/MacOS
        activate_script = Path("venv/bin/activate")
        python_exe = Path("venv/bin/python")
    
    if not activate_script.exists() or not python_exe.exists():
        return False
    
    return True

def install_requirements():
    """Install required packages from requirements.txt"""
    print("Installing dependencies...")
    
    # Fix: Use correct pip path based on OS and check for existence
    if os.name == "nt":  # Windows
        pip_paths = ["venv\\Scripts\\pip.exe", "venv\\Scripts\\pip"]
    else:  # Unix/macOS
        pip_paths = ["venv/bin/pip"]
    
    # Find the first pip path that exists
    pip_cmd = None
    for path in pip_paths:
        if Path(path).exists():
            pip_cmd = path
            break
    
    if not pip_cmd:
        print("ERROR: Could not find pip in the virtual environment.")
        print("Try activating the environment manually and running: pip install -r requirements.txt")
        return False
    
    try:
        subprocess.run([pip_cmd, "install", "-r", "requirements.txt"], check=True)
        print("Dependencies installed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error installing dependencies: {e}")
        return False

def setup_env_file():
    """Create .env file if it doesn't exist"""
    env_file = Path(".env")
    env_example = Path(".env.example")
    
    if env_file.exists():
        print(".env file already exists.")
        return
    
    if env_example.exists():
        print("Creating .env file from .env.example...")
        env_file.write_text(env_example.read_text())
    else:
        print("Creating default .env file...")
        default_env = (
            "OPENAI_API_KEY=\n"
            "SCAN_FOLDER_PATH=C:/Users/imccl/OneDrive - Think On Labs LLC/Office Lens/\n"
            "CHECK_INTERVAL=60\n"
            "CONTINUOUS_MONITORING=False\n"
        )
        env_file.write_text(default_env)
    
    print(".env file created. Please edit it with your actual values.")

def main():
    """Main setup function"""
    print("=== Scan Namer Agent Setup ===")
    
    if not check_python_version():
        return
    
    # Try automated setup
    venv_created = create_virtual_env()
    deps_installed = False
    
    if venv_created:
        deps_installed = install_requirements()
    
    # Set up .env file regardless of other steps
    setup_env_file()
    
    # Provide appropriate completion message
    if venv_created and deps_installed:
        print("\nAutomated setup complete!")
    else:
        print("\nSome automated setup steps failed.")
        print("Please follow these manual steps to complete setup:")
        
        if not venv_created:
            print("\n1. Create a virtual environment:")
            print(f"   {sys.executable} -m venv venv")
        
        print("\n2. Activate the virtual environment:")
        if os.name == "nt":  # Windows
            print("   venv\\Scripts\\activate")
        else:  # Unix/MacOS
            print("   source venv/bin/activate")
        
        if not deps_installed:
            print("\n3. Install dependencies:")
            print("   pip install -r requirements.txt")
    
    print("\nNext steps:")
    print("1. Edit the .env file with your OpenAI API key and correct folder path")
    print("2. Run the agent:")
    print("   python scan_agent.py")

if __name__ == "__main__":
    main() 