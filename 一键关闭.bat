@echo off
chcp 65001 >nul
title 文旅行程规划系统 - 一键关闭
cd /d "%~dp0"

echo.
echo  ============================================
echo    文旅行程规划系统 - 一键关闭
echo  ============================================
echo.

docker compose down

echo.
echo  服务已全部停止。
echo  数据保留在 Docker 卷中，下次启动不会丢失。
echo.
pause
