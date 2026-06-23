@echo off
echo Stopping Social SaaS servers...

REM Kill the named server windows and their child processes (uvicorn / node).
taskkill /FI "WINDOWTITLE eq Social SaaS - Backend*"  /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Social SaaS - Frontend*" /T /F >nul 2>&1

REM Fallback: free the ports if anything is still listening.
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

echo Done. Backend (8000) and frontend (5173) stopped.
timeout /t 2 /nobreak >nul
