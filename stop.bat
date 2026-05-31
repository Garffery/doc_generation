@echo off
title Stop Services

echo ========================================
echo   Stop Doc Generation Services
echo ========================================
echo.

echo [1/3] Stopping backend (uvicorn port 8000)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo [2/3] Stopping ARQ Worker...
for /f "tokens=2" %%a in ('tasklist /fi "WINDOWTITLE eq ARQ Worker*" /fo list ^| findstr "PID:"') do (
    taskkill /f /pid %%a >nul 2>&1
)
REM Fallback: kill by process name matching arq
for /f "tokens=2 delims=," %%a in ('wmic process where "commandline like '%%arq%%doc_generation.worker%%'" get processid /format:csv 2^>nul ^| findstr /r "[0-9]"') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo [3/3] Stopping frontend (vite port 5173)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo.
echo ========================================
echo   All services stopped.
echo ========================================
pause
