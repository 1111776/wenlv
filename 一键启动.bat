@echo off
title 山海行 - 文旅多Agent行程规划系统 一键启动
cd /d "%~dp0"

echo.
echo  ============================================
echo    山海行 - 文旅多Agent行程规划系统
echo    一键启动
echo  ============================================
echo.

where docker >nul 2>nul
if errorlevel 1 (
    echo  [错误] 未检测到 Docker，请先安装 Docker Desktop
    echo.
    pause
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo  [错误] Docker 未运行，请先启动 Docker Desktop
    echo.
    pause
    exit /b 1
)

echo  [1/3] 正在启动服务容器...
echo        首次启动需构建镜像，约 2-5 分钟，请耐心等待
echo.
docker compose up -d
if errorlevel 1 (
    echo.
    echo  [错误] 启动失败，请查看上方错误信息
    echo.
    pause
    exit /b 1
)

echo.
echo  [2/3] 等待服务就绪（约 15 秒）...
timeout /t 15 /nobreak >nul

echo.
echo  [3/3] 打开浏览器...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" http://localhost:8080

echo.
echo  ============================================
echo    启动完成！访问地址：
echo      前端看板  http://localhost:8080
echo      后端API   http://localhost:8001/docs
echo      Grafana   http://localhost:3002 (admin/admin)
echo.
echo    演示账号（密码都是 wenlv123）：
echo      旅行顾问  advisor_demo
echo      主管审核  supervisor_demo
echo      游客      （可自行注册，选择游客身份）
echo  ============================================
echo.
echo  提示：本窗口可关闭，服务在后台继续运行
echo.
pause
