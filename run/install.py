import os
import platform
import subprocess
import sys

def install_ffmpeg():
    system = platform.system()
    try:
        if system == "Linux":
            print("Installing ffmpeg on Linux...")
            subprocess.run(["sudo", "apt", "update"], check=True)
            subprocess.run(["sudo", "apt", "install", "-y", "ffmpeg"], check=True)
        elif system == "Darwin":  # MacOS
            print("Installing ffmpeg on MacOS...")
            subprocess.run(["brew", "install", "ffmpeg"], check=True)
        elif system == "Windows":
            print("Please install ffmpeg manually on Windows.")
            print("Visit https://ffmpeg.org/download.html and follow the instructions.")
        else:
            print(f"Unsupported operating system: {system}")
    except Exception as e:
        print(f"Error installing ffmpeg: {e}")

def install_tkinter():
    system = platform.system()
    try:
        if system == "Linux":
            print("Installing tkinter on Linux...")
            subprocess.run(["sudo", "apt", "update"], check=True)
            subprocess.run(["sudo", "apt", "install", "-y", "python3-tk"], check=True)
        elif system == "Darwin":  # MacOS
            print("Ensuring tkinter is available on MacOS...")
            # tkinter is usually pre-installed with Python on MacOS
            print("If tkinter is not available, install Python from https://www.python.org/downloads/")
        elif system == "Windows":
            print("tkinter is included with Python on Windows.")
            print("If tkinter is missing, reinstall Python from https://www.python.org.")
        else:
            print(f"Unsupported operating system: {system}")
    except Exception as e:
        print(f"Error installing tkinter: {e}")

def install_dependencies():
    print("Installing dependencies...")
    install_ffmpeg()
    install_tkinter()
    print("Dependency installation complete!")

if __name__ == "__main__":
    install_dependencies()