@echo off
echo Stopping AutoSocial AI servers...

REM Kill the named server windows and their child processes (uvicorn / node).
taskkill /FI "WINDOWTITLE eq AutoSocial AI - Backend*"  /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq AutoSocial AI - Frontend*" /T /F >nul 2>&1

REM Fallback: free the ports if anything is still listening.
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

echo Done. Backend (8000) and frontend (5173) stopped.
timeout /t 2 /nobreak >nul
