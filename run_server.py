"""
run_server.py: Root launcher for the Disaster Intelligence Platform FastAPI Server.
Eliminates CLI directory quoting issues across Windows PowerShell and cmd.exe.
"""

from pathlib import Path
import sys
import uvicorn

ROOT_DIR = Path(__file__).resolve().parent
DISASTER_API_DIR = ROOT_DIR / "Disaster API"
FETCHENGINE_DIR = ROOT_DIR / "fetchengine"

# Add directories to sys.path
for path in [ROOT_DIR, DISASTER_API_DIR, FETCHENGINE_DIR]:
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

if __name__ == "__main__":
    uvicorn.run(
        "src.server:app",
        host="127.0.0.1",
        port=8000,
        app_dir=str(DISASTER_API_DIR),
        reload=True,
    )
