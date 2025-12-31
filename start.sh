#!/usr/bin/env bash
# start.sh
# 用途：如果已有 app.py 运行则先停止；然后以 nohup 启动 app.py（使用 conda ares 环境）
# 生成 pid 文件： ./app.pid
# 日志输出到 logs/ 目录（由 simple_logger 管理）

APP="app.py"
CONDA_ENV="ares"
PIDFILE="app.pid"
GRACE_PERIOD=10    # 等待优雅退出的秒数

cd "$(dirname "$0")" || exit 1

# 初始化 conda
echo "初始化 conda..."
if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/anaconda3/etc/profile.d/conda.sh"
elif [ -f "/opt/conda/etc/profile.d/conda.sh" ]; then
    source "/opt/conda/etc/profile.d/conda.sh"
else
    echo "错误: 未找到 conda 安装，请先安装 conda"
    exit 1
fi

# 检查 ares 环境是否存在
if conda env list | grep -q "^${CONDA_ENV} "; then
    echo "conda 环境 '${CONDA_ENV}' 已存在"
else
    echo "创建 conda 环境 '${CONDA_ENV}' (Python 3.12)..."
    conda create -n "${CONDA_ENV}" python=3.12 -y
    if [ $? -ne 0 ]; then
        echo "错误: 创建 conda 环境失败"
        exit 1
    fi
    echo "conda 环境 '${CONDA_ENV}' 创建成功"
fi

# 激活 conda 环境
echo "激活 conda 环境 '${CONDA_ENV}'..."
conda activate "${CONDA_ENV}"
if [ $? -ne 0 ]; then
    echo "错误: 激活 conda 环境失败"
    exit 1
fi

# 更新依赖
echo "更新依赖包..."
pip install -r requirements.txt --upgrade

# 拉取最新代码
echo "拉取最新代码..."
git pull origin main

# 获取 Python 路径
PY=$(which python)
echo "使用 Python: ${PY}"

# 查找与 app 关联的 pid（匹配 python ... app.py）
get_pids() {
    # 匹配 python + app.py 的组合
    pgrep -f "[p]ython.*${APP}" || true
}

pids=$(get_pids)

if [ -n "$pids" ]; then
    echo "检测到运行中的进程，PID(s): $pids"
    echo "发送 TERM (优雅退出)..."
    kill $pids 2>/dev/null || true

    # 等待进程退出
    t=0
    while [ $t -lt $GRACE_PERIOD ]; do
        sleep 1
        t=$((t+1))
        remaining=$(get_pids)
        if [ -z "$remaining" ]; then
            echo "进程已优雅退出。"
            break
        fi
        echo "等待中... ($t/$GRACE_PERIOD) 仍存在 PID: $remaining"
    done

    # 强制杀掉残留进程
    remaining=$(get_pids)
    if [ -n "$remaining" ]; then
        echo "优雅退出超时，执行 SIGKILL..."
        kill -9 $remaining 2>/dev/null || true
        sleep 1
        remaining=$(get_pids)
        if [ -n "$remaining" ]; then
            echo "警告：仍有进程未被杀死：$remaining"
        else
            echo "残留进程已被强制结束。"
        fi
    fi

    # 删除旧 pidfile（如果有且对应进程已结束）
    if [ -f "$PIDFILE" ]; then
        rm -f "$PIDFILE"
    fi
else
    echo "未检测到正在运行的 ${APP}。准备启动。"
fi

# 启动新进程（不生成 app.log，日志由 simple_logger 管理）
echo "使用 conda 环境 '${CONDA_ENV}' 启动 ${APP}"
echo "Python 路径: ${PY}"
echo "PID 写入 ${PIDFILE}"
echo "日志将输出到 logs/ 目录"
nohup "$PY" -u "$APP" > /dev/null 2>&1 &

NEWPID=$!
# 确保写入 pid
echo $NEWPID > "$PIDFILE"
sleep 2

# 验证是否启动成功
if ps -p $NEWPID > /dev/null 2>&1; then
    echo "启动成功，PID = $NEWPID"
    echo "查看日志："
    echo "  tail -f logs/aresbot_stdout_\$(date +%Y-%m-%d).log"
    # 显示最新日志
    latest_log=$(ls -t logs/aresbot_stdout_*.log 2>/dev/null | head -1)
    if [ -n "$latest_log" ]; then
        echo ""
        echo "最新日志内容："
        tail -n 20 "$latest_log"
    fi
else
    echo "启动失败，请检查配置"
    exit 2
fi
