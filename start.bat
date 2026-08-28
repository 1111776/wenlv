@echo off
title WenLv Travel Planner - One Click Start
cd /d "%~dp0"

echo.
echo ================================================
echo   WenLv Multi-Agent Travel Planner
echo ================================================
echo.

where docker >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Docker not found. Please install Docker Desktop.
    echo.
    pause
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running. Start Docker Desktop first.
    echo.
    pause
    exit /b 1
)

echo [1/3] Starting containers...
echo       First run needs build, about 2-5 min.
echo.
docker compose up -d
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start. See error above.
    echo.
    pause
    exit /b 1
)

echo.
echo [2/3] Waiting 15 seconds for services...
timeout /t 15 /nobreak >nul

echo.
echo [3/3] Opening browser...
start "" http://localhost:8080

echo.
echo ================================================
echo   STARTED! Visit:
echo     Frontend   http://localhost:8080
echo     API Docs   http://localhost:8001/docs
echo     Grafana    http://localhost:3002  (admin/admin)
echo.
echo   Demo Accounts:
echo     Advisor    advisor_demo / wenlv123
echo     Reviewer   supervisor_demo / wenlv123
echo ================================================
echo.
echo You can close this window. Services keep running.
echo.
pause
