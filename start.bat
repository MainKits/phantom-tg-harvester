@echo off
title Phantom TG Harvester
color 0A
echo.
echo  ========================================
echo   Phantom TG Harvester - Starting...
echo  ========================================
echo.

:: Start backend
echo [1/2] Starting Python backend on port 8000...
start "Phantom Backend" cmd /k "cd /d %~dp0 && python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"

:: Wait for backend to initialize
timeout /t 3 /nobreak > nul

:: Start frontend
echo [2/2] Starting frontend on port 5173...
start "Phantom Frontend" cmd /k "cd /d %~dp0\frontend && npm run dev"

:: Wait and open browser
timeout /t 4 /nobreak > nul
echo.
echo  ========================================
echo   App is running!
echo   Frontend: http://localhost:5173
echo   Backend:  http://localhost:8000
echo  ========================================
echo.
echo  Press any key to open in browser...
pause > nul
start http://localhost:5173
