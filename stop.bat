@echo off
title Stop Services

echo ========================================
echo   Stop Doc Generation Services
echo ========================================
echo.

echo [1/2] Stopping backend (uvicorn port 8000)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo [2/2] Stopping frontend (vite port 5173)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo.
echo ========================================
echo   All services stopped.
echo ========================================
pause
