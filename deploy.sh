#!/bin/bash
# ─────────────────────────────────────────
#  一键部署脚本 — 抖音来客商家数据下载上传工具
# ─────────────────────────────────────────
set -e

# ====== 配置区域（按需修改）======
REPO_URL="https://github.com/Kewen526/jiangxin_douyin_api.git"
BRANCH="main"
DEPLOY_DIR="/opt/jiangxin_douyin_api"
PYTHON="python3"

echo "============================================="
echo "  一键部署 — 抖音来客数据工具"
echo "============================================="

# 1. 停止已有进程
echo ""
echo "[1/6] 停止已有进程 ..."
pkill -f "python.*main.py" 2>/dev/null && echo "  已停止旧进程" || echo "  无运行中的进程"

# 2. 删除旧目录
echo ""
echo "[2/6] 清除旧部署目录：$DEPLOY_DIR ..."
if [ -d "$DEPLOY_DIR" ]; then
    rm -rf "$DEPLOY_DIR"
    echo "  已删除"
else
    echo "  目录不存在，跳过"
fi

# 3. 拉取代码
echo ""
echo "[3/6] 克隆代码 ..."
git clone -b "$BRANCH" "$REPO_URL" "$DEPLOY_DIR"
cd "$DEPLOY_DIR"
echo "  当前版本：$(git log --oneline -1)"

# 4. 创建虚拟环境并安装依赖
echo ""
echo "[4/6] 创建虚拟环境并安装依赖 ..."
$PYTHON -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  依赖安装完成"

# 5. 安装 Playwright 浏览器
echo ""
echo "[5/6] 安装 Playwright 浏览器 ..."
playwright install --with-deps chromium
echo "  Playwright 浏览器安装完成"

# 6. 启动服务（后台运行，日志输出到 app.log）
echo ""
echo "[6/6] 启动服务 ..."
nohup $PYTHON main.py > app.log 2>&1 &
echo "  服务已启动，PID: $!"
echo "  日志文件：$DEPLOY_DIR/app.log"

echo ""
echo "============================================="
echo "  部署完成！"
echo "============================================="
echo ""
echo "常用命令："
echo "  查看日志：  tail -f $DEPLOY_DIR/app.log"
echo "  立即执行：  cd $DEPLOY_DIR && source .venv/bin/activate && python main.py run"
echo "  查看状态：  cd $DEPLOY_DIR && source .venv/bin/activate && python main.py status"
echo "  停止服务：  pkill -f 'python.*main.py'"
