#!/bin/bash

echo "========================================"
echo "  Zensers 生产环境启动"
echo "========================================"
echo

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未找到 Python，请先安装 Python 3.10+"
    exit 1
fi

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo "[错误] 未找到 Node.js，请先安装 Node.js 18+"
    exit 1
fi

echo "[1/4] 检查后端依赖..."
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements-lock.txt -q

echo "[2/4] 构建前端..."
cd web
npm ci --only=production
npm run build
cd ..

echo "[3/4] 启动后端服务 (端口 8000)..."
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 2 &
BACKEND_PID=$!

echo "[4/4] 启动前端服务 (端口 3000)..."
cd web
NODE_ENV=production npm start &
FRONTEND_PID=$!
cd ..

echo
echo "========================================"
echo "  生产环境启动完成！"
echo "========================================"
echo
echo "  前端地址: http://localhost:3000"
echo "  后端地址: http://localhost:8000"
echo "  API 文档: http://localhost:8000/api/v1/docs"
echo
echo "  按 Ctrl+C 停止所有服务..."

# 等待用户按 Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT
wait
