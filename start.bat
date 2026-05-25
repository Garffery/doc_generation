@echo off
title Start Services

echo ========================================
echo   Start Doc Generation Services
echo ========================================
echo.

cd /d "%~dp0"

echo [1/2] Starting backend (FastAPI)...
start "Backend - FastAPI" cmd /k "cd /d "%~dp0" && .venv\Scripts\activate && uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload"

echo [2/2] Starting frontend (Vite)...
start "Frontend - Vite" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo ========================================
echo   Services started:
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
echo ========================================
echo.
echo Run stop.bat to stop all services.
pause
