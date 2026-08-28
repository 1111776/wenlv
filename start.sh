#!/usr/bin/env bash
# =============================================================================
# 文旅多 Agent 行程规划系统 — 一键启动脚本（Linux / macOS）
# =============================================================================
# 用法：
#   ./start.sh              # 构建并启动全部服务
#   ./start.sh --no-build   # 跳过重新构建镜像
#   ./start.sh --stop       # 停止并移除所有容器
#   ./start.sh --logs       # 查看服务日志
#
# 启动后访问：
#   前端看板   http://localhost:3000
#   后端 API   http://localhost:8000/docs
#   Prometheus http://localhost:9090
#   Grafana    http://localhost:3001  (admin/admin)
# =============================================================================

set -e
cd "$(dirname "$0")"

NO_BUILD=false
STOP=false
LOGS=false

for arg in "$@"; do
  case $arg in
    --no-build) NO_BUILD=true ;;
    --stop) STOP=true ;;
    --logs) LOGS=true ;;
  esac
done

echo ""
echo "=============================================="
echo "  文旅多 Agent 行程规划系统 — 一键启动"
echo "=============================================="
echo ""

# 检查 Docker
if ! command -v docker &> /dev/null; then
  echo "[✗] 未检测到 Docker，请先安装 Docker"
  exit 1
fi

docker info &> /dev/null || {
  echo "[✗] Docker 守护进程未运行，请先启动 Docker"
  exit 1
}

if [ "$STOP" = true ]; then
  echo "[>] 停止并移除所有服务容器..."
  docker compose down
  echo "[✓] 已停止"
  exit 0
fi

if [ "$LOGS" = true ]; then
  docker compose logs -f --tail=100
  exit 0
fi

# 构建并启动
if [ "$NO_BUILD" = true ]; then
  echo "[>] 跳过构建，直接启动..."
  docker compose up -d
else
  echo "[>] 构建镜像并启动（首次可能需要几分钟）..."
  docker compose up -d --build
fi

echo ""
echo "[>] 等待服务就绪..."

for i in $(seq 1 40); do
  all_healthy=true
  for s in postgres redis api worker frontend; do
    status=$(docker inspect --format='{{.State.Health.Status}}' "wenlv-$s" 2>/dev/null || echo "none")
    if [ "$status" != "healthy" ]; then
      all_healthy=false
      break
    fi
  done
  [ "$all_healthy" = true ] && break
  sleep 3
done

echo ""
echo "=============================================="
echo "  服务已启动，访问地址如下："
echo "=============================================="
echo "  🌐 前端看板   : http://localhost:8080"
echo "  🔧 后端 API   : http://localhost:8001/docs"
echo "  📊 Prometheus : http://localhost:9091"
echo "  📈 Grafana    : http://localhost:3002 (admin/admin)"
echo ""
echo "  演示账号："
echo "    旅行顾问  advisor_demo / wenlv123"
echo "    主管审核  supervisor_demo / wenlv123"
echo ""
