# =============================================================================
# 文旅多 Agent 行程规划系统 — 一键启动脚本（Windows PowerShell）
# =============================================================================
# 用法：
#   .\start.ps1              # 构建并启动全部服务（前端 + 后端 + Redis + Postgres + 监控）
#   .\start.ps1 -NoBuild     # 跳过重新构建镜像（代码未变时快速启动）
#   .\start.ps1 -Stop        # 停止并移除所有容器
#   .\start.ps1 -Logs        # 查看服务日志
#
# 启动后访问：
#   前端看板   http://localhost:3000
#   后端 API   http://localhost:8000/docs  （OpenAPI 文档）
#   Prometheus http://localhost:9090
#   Grafana    http://localhost:3001  （账号 admin / 密码 admin）
# =============================================================================

param(
    [switch]$NoBuild,   # 跳过镜像构建
    [switch]$Stop,      # 停止服务
    [switch]$Logs       # 查看日志
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  文旅多 Agent 行程规划系统 — 一键启动" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

# ---------------------------------------------------------------------------
# 检查 Docker 是否可用
# ---------------------------------------------------------------------------
try {
    $dockerVer = docker --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker 未安装" }
    Write-Host "[✓] Docker 已就绪：$dockerVer" -ForegroundColor Green
} catch {
    Write-Host "[✗] 未检测到 Docker，请先安装 Docker Desktop 并启动" -ForegroundColor Red
    exit 1
}

# 检查 Docker 守护进程
docker info *> $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[✗] Docker 守护进程未运行，请先启动 Docker Desktop" -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------------
# 停止服务
# ---------------------------------------------------------------------------
if ($Stop) {
    Write-Host "[>] 停止并移除所有服务容器..." -ForegroundColor Yellow
    docker compose down
    Write-Host "[✓] 已停止" -ForegroundColor Green
    exit 0
}

# ---------------------------------------------------------------------------
# 查看日志
# ---------------------------------------------------------------------------
if ($Logs) {
    docker compose logs -f --tail=100
    exit 0
}

# ---------------------------------------------------------------------------
# 构建并启动
# ---------------------------------------------------------------------------
if ($NoBuild) {
    Write-Host "[>] 跳过构建，直接启动（使用已有镜像）..." -ForegroundColor Yellow
    docker compose up -d
} else {
    Write-Host "[>] 构建镜像并启动（首次可能需要几分钟下载依赖）..." -ForegroundColor Yellow
    docker compose up -d --build
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "[✗] 启动失败，请查看上方错误日志" -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------------
# 等待服务健康
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "[>] 等待服务就绪..." -ForegroundColor Yellow

$services = @("postgres", "redis", "api", "worker", "frontend")
$maxWait = 120  # 最多等 120 秒
$elapsed = 0

while ($elapsed -lt $maxWait) {
    $healthy = $true
    foreach ($s in $services) {
        $status = docker inspect --format='{{.State.Health.Status}}' "wenlv-$s" 2>$null
        if ($status -ne "healthy") {
            $healthy = $false
            break
        }
    }
    if ($healthy) { break }
    Start-Sleep -Seconds 3
    $elapsed += 3
}

if ($elapsed -ge $maxWait) {
    Write-Host "[!] 部分服务未在 $maxWait 秒内就绪，请查看日志：docker compose logs" -ForegroundColor Yellow
} else {
    Write-Host "[✓] 全部服务已就绪（用时 $elapsed 秒）" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# 打印访问地址
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  服务已启动，访问地址如下：" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  🌐 前端看板   : " -NoNewline; Write-Host "http://localhost:8080" -ForegroundColor Green
Write-Host "  🔧 后端 API   : " -NoNewline; Write-Host "http://localhost:8001/docs" -ForegroundColor Green
Write-Host "  📊 Prometheus : " -NoNewline; Write-Host "http://localhost:9091" -ForegroundColor Green
Write-Host "  📈 Grafana    : " -NoNewline; Write-Host "http://localhost:3002 (admin/admin)" -ForegroundColor Green
Write-Host ""
Write-Host "  演示账号：" -ForegroundColor Yellow
Write-Host "    旅行顾问  advisor_demo / wenlv123" -ForegroundColor White
Write-Host "    主管审核  supervisor_demo / wenlv123" -ForegroundColor White
Write-Host ""
Write-Host "  常用命令：" -ForegroundColor Yellow
Write-Host "    .\start.ps1 -Logs      查看日志" -ForegroundColor White
Write-Host "    .\start.ps1 -Stop      停止服务" -ForegroundColor White
Write-Host "    .\start.ps1 -NoBuild   快速重启（代码未变）" -ForegroundColor White
Write-Host ""

# 自动打开浏览器
try {
    Start-Process "http://localhost:8080"
    Write-Host "[✓] 已自动打开浏览器" -ForegroundColor Green
} catch {
    Write-Host "[!] 请手动在浏览器打开 http://localhost:8080" -ForegroundColor Yellow
}
