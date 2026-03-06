@echo off
setlocal
cd /d "%~dp0"

echo Starting Backend (Django)...
start "Backend" cmd /k "cd /d ""%~dp0backend"" && python manage.py runserver"

timeout /t 3 /nobreak >nul

echo Starting Frontend (Next.js)...
start "Frontend" cmd /k "cd /d ""%~dp0frontend"" && npm run dev"

echo.
echo Backend:  http://127.0.0.1:8000/
echo Frontend: http://localhost:3000/
echo.
echo Two windows opened. Close each window to stop that server.
endlocal
