@echo off
chcp 65001 >nul
echo Starting Zensers...

:: Start backend
echo Starting backend...
start /B cmd /C "python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000"

:: Wait for backend
timeout /t 5 /nobreak >nul

:: Start frontend
echo Starting frontend...
cd web
start /B cmd /C "npm run dev"

echo.
echo Zensers is starting...
echo Backend: http://localhost:8000
echo Frontend: http://localhost:3000
echo.
echo Press Ctrl+C to stop all services.

:: Wait
pause
