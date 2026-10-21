@echo off
REM ==============================================================================
REM Rakhshak Disaster Intelligence & Copernicus Sentinel-1 Platform
REM Launches FastAPI Backend (Port 8000) & Vite Frontend (Port 5173) Concurrently
REM ==============================================================================

echo ======================================================================
echo   Starting Disaster Intelligence & Copernicus Platform...
echo   Backend:  http://127.0.0.1:8000 (API & Docs: /docs)
echo   Frontend: http://localhost:5173
echo ======================================================================

set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

REM Start FastAPI Backend in a separate window via run_server.py
start "Rakhshak Backend Server" cmd /k "py run_server.py"

REM Start Vite Frontend Dev Server
cd /d "%PROJECT_ROOT%frontend"
call npm run dev -- --port 5173 --host

pause
