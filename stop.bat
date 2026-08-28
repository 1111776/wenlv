@echo off
title WenLv Travel Planner - Stop
cd /d "%~dp0"

echo.
echo ================================================
echo   WenLv Multi-Agent Travel Planner - Stop
echo ================================================
echo.

docker compose down

echo.
echo Stopped. Data kept in Docker volumes.
echo.
pause
