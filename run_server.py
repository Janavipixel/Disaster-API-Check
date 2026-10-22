"""
run_server.py: Root launcher for the Disaster Intelligence Platform FastAPI Server.
Eliminates CLI directory quoting issues across Windows PowerShell and cmd.exe.
"""

import os
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
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    reload_env = os.environ.get("RELOAD")
    # Default reload to True on local dev unless in production/Docker container
    reload = reload_env.lower() == "true" if reload_env is not None else (os.environ.get("ENVIRONMENT") != "production")

    uvicorn.run(
        "src.server:app",
        host=host,
        port=port,
        app_dir=str(DISASTER_API_DIR),
        reload=reload,
    )
