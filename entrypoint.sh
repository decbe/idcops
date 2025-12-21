#!/bin/bash

set -eo pipefail

# 设置默认值
: "${APP_HOME:=/opt/idcops}"
: "${STATIC_ROOT:=${APP_HOME}/static}"
: "${MEDIA_ROOT:=${APP_HOME}/media}"
: "${LOGS_ROOT:=${APP_HOME}/logs}"
: "${RUN_ROOT:=${APP_HOME}/run}"
: "${GUNICORN_CONFIG:=${APP_HOME}/contrib/gunicorn.py}"
: "${POSTGRES_HOST:=postgresql}"
: "${POSTGRES_PORT:=5432}"
: "${DB_WAIT_TIMEOUT:=60}"

# 等待 PostgreSQL 数据库就绪（带超时）
wait_for_db() {
    echo "等待 PostgreSQL 数据库就绪..."
    local count=0
    while ! nc -z ${POSTGRES_HOST} ${POSTGRES_PORT}; do
        count=$((count + 1))
        if [ $count -ge $DB_WAIT_TIMEOUT ]; then
            echo "错误：等待数据库超时（${DB_WAIT_TIMEOUT}秒）"
            exit 1
        fi
        sleep 1
    done
    echo "PostgreSQL 数据库已就绪"
}

# 初始化函数
initialize() {
    echo "首次运行，开始初始化..."

    # 创建必要的目录
    mkdir -p ${STATIC_ROOT} ${MEDIA_ROOT} ${LOGS_ROOT} ${RUN_ROOT}

    # 设置目录权限
    chmod -R 755 ${STATIC_ROOT}
    chmod -R 775 ${MEDIA_ROOT}
    chmod -R 755 ${LOGS_ROOT}
    chmod -R 775 ${RUN_ROOT}

    wait_for_db

    # 收集静态文件
    python manage.py collectstatic --no-input

    # 数据库迁移（生产环境不执行 makemigrations）
    python manage.py migrate --noinput --verbosity 2

    # 创建安装锁定文件（放在持久化日志目录）
    touch ${LOGS_ROOT}/install.lock
    
    echo "初始化完成"
}

# 检查是否是 web 服务
is_web_service() {
    [ -z "$*" ] || [ "$*" = "/entrypoint.sh" ]
}

# 主逻辑
if is_web_service "$@" && [ ! -f "${LOGS_ROOT}/install.lock" ]; then
    initialize
elif is_web_service "$@"; then
    echo "检测到 install.lock 文件，跳过初始化步骤"
    wait_for_db
    # 仅执行数据库迁移
    python manage.py migrate --noinput
fi

# 如果是 rq-worker，等待数据库后执行命令
if [[ "$*" == *"rqworker"* ]]; then
    echo "启动 RQ Worker..."
    wait_for_db
    exec "$@"
fi

# 如果是 web 服务，启动 Gunicorn
if is_web_service "$@"; then
    echo "启动 Gunicorn 服务器..."
    echo "监听地址: ${GUNICORN_HOST:-0.0.0.0}:${GUNICORN_PORT:-8000}"
    exec gunicorn idcops.wsgi:application --config ${GUNICORN_CONFIG}
fi
