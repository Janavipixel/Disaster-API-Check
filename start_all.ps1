# ==============================================================================
# Rakhshak Disaster Intelligence & Copernicus Sentinel-1 Platform
# PowerShell Launcher for FastAPI Backend & Vite Frontend
# ==============================================================================

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  Starting Disaster Intelligence & Copernicus Sentinel-1 Platform..." -ForegroundColor Cyan
Write-Host "  Backend:  http://127.0.0.1:8000 (API & Docs at /docs)" -ForegroundColor Green
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Launch Backend Process via run_server.py
Start-Process "py" -ArgumentList "run_server.py" -WorkingDirectory $ScriptDir

# Launch Frontend in current window
Set-Location (Join-Path $ScriptDir "frontend")
npm run dev -- --port 5173 --host
