@echo off
title Start Services

echo ========================================
echo   Start Doc Generation Services
echo ========================================
echo.

cd /d "%~dp0"

echo [1/3] Starting backend (FastAPI)...
start "Backend - FastAPI" cmd /k "cd /d "%~dp0" && .venv\Scripts\activate && uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload"

echo [2/3] Starting ARQ Worker...
start "ARQ Worker" cmd /k "cd /d "%~dp0" && .venv\Scripts\activate && python -m arq doc_generation.worker.WorkerSettings"

echo [3/3] Starting frontend (Vite)...
start "Frontend - Vite" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo ========================================
echo   Services started:
echo   Backend:  http://localhost:8000
echo   ARQ Worker: listening on Redis
echo   Frontend: http://localhost:5173
echo ========================================
echo.
echo Run stop.bat to stop all services.
pause
