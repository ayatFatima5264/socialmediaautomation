@echo off
title AutoSocial AI Launcher
cd /d "%~dp0"

echo ==================================================
echo    AutoSocial AI - launching backend + frontend
echo ==================================================
echo.

REM --- Backend (FastAPI + PostgreSQL) on http://localhost:8000 ---
start "AutoSocial AI - Backend" cmd /k "venv\Scripts\python.exe -m uvicorn app.main:app --reload"

REM --- Frontend (Vite + React) on http://localhost:5173 ---
start "AutoSocial AI - Frontend" cmd /k "cd frontend && npm run dev"

echo Waiting for the servers to warm up...
timeout /t 6 /nobreak >nul

REM --- Open the app in the default browser ---
start "" http://localhost:5173

echo.
echo   Frontend : http://localhost:5173
echo   Backend  : http://localhost:8000/docs
echo.
echo Two server windows have opened. Keep them open while you work.
echo To stop everything: run stop.bat (or just close both windows).
echo.
echo You can close THIS launcher window now.
pause
