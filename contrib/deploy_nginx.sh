#!/bin/bash

: '
这个脚本用于部署 nginx 配置
主要功能：
1. 加载环境变量
2. 渲染 nginx 配置模板
3. 设置目录权限
4. 重启 nginx 服务
# 给脚本添加执行权限
chmod +x deploy_nginx.sh

# 基本用法（使用默认值）
sudo ./deploy_nginx.sh

# 指定自定义路径
sudo ./deploy_nginx.sh -t /path/to/nginx.conf.template -o /etc/nginx/sites-available/idcops.conf -e /path/to/.env

# 显示帮助信息
./deploy_nginx.sh -h
'

# 设置错误时退出
set -e

# 默认值设置
NGINX_CONF_TEMPLATE="./contrib/nginx.conf.template"
NGINX_CONF_PATH="/etc/nginx/conf.d/idcops.conf"
ENV_FILE=".env"

# 显示用法
show_usage() {
    echo "Usage: $0 [-t template_path] [-o output_path] [-e env_file]"
    echo "  -t: nginx配置模板路径 (默认: ${NGINX_CONF_TEMPLATE})"
    echo "  -o: 输出nginx配置文件路径 (默认: ${NGINX_CONF_PATH})"
    echo "  -e: 环境变量文件路径 (默认: ${ENV_FILE})"
    exit 1
}

# 解析命令行参数
while getopts "t:o:e:h" opt; do
    case $opt in
        t) NGINX_CONF_TEMPLATE="$OPTARG" ;;
        o) NGINX_CONF_PATH="$OPTARG" ;;
        e) ENV_FILE="$OPTARG" ;;
        h) show_usage ;;
        ?) show_usage ;;
    esac
done

# 检查必要文件是否存在
if [ ! -f "$NGINX_CONF_TEMPLATE" ]; then
    echo "错误: 找不到nginx配置模板文件: $NGINX_CONF_TEMPLATE"
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "错误: 找不到环境变量文件: $ENV_FILE"
    exit 1
fi

# 创建临时环境变量文件
TMP_ENV=$(mktemp)
trap "rm -f $TMP_ENV" EXIT

# 加载环境变量
echo "正在加载环境变量..."
set -a
source "$ENV_FILE"
set +a

# 设置默认值（如果环境变量未定义）
: "${NGINX_PORT:=80}"
: "${NGINX_SERVER_NAME:=localhost}"
: "${NGINX_CLIENT_MAX_BODY_SIZE:=100M}"
: "${APP_HOME:=/opt/idcops}"

# NGINX_UPSTREAM_HOST 默认值：127.0.0.1（非 Docker 环境）
# 在 Docker 环境中通常为 "web"
: "${NGINX_UPSTREAM_HOST:=127.0.0.1}"

# NGINX_UPSTREAM_PORT 默认值：使用 GUNICORN_PORT 的值
# 如果 GUNICORN_PORT 也未设置，则使用 8000
: "${GUNICORN_PORT:=8000}"
: "${NGINX_UPSTREAM_PORT:=$GUNICORN_PORT}"

# NGINX_STATIC_PATH 和 NGINX_MEDIA_PATH 默认值：基于 APP_HOME 自动生成
: "${NGINX_STATIC_PATH:=${APP_HOME}/static/}"
: "${NGINX_MEDIA_PATH:=${APP_HOME}/media/}"

# 确保目标目录存在
sudo mkdir -p "$(dirname "$NGINX_CONF_PATH")"

# 渲染模板
# 注意：需要包含 GUNICORN_PORT 和 APP_HOME，因为模板中可能使用它们作为默认值
echo "正在渲染nginx配置..."
envsubst '${NGINX_PORT} ${NGINX_SERVER_NAME} ${NGINX_CLIENT_MAX_BODY_SIZE} ${NGINX_UPSTREAM_HOST} ${NGINX_UPSTREAM_PORT} ${NGINX_STATIC_PATH} ${NGINX_MEDIA_PATH} ${GUNICORN_PORT} ${APP_HOME}' \
    < "$NGINX_CONF_TEMPLATE" \
    | sudo tee "$NGINX_CONF_PATH" > /dev/null

# 测试nginx配置
echo "测试nginx配置..."
sudo nginx -t

# 如果测试成功，重新加载nginx
if [ $? -eq 0 ]; then
    echo "重新加载nginx服务..."
    sudo systemctl reload nginx || sudo service nginx reload
    echo "完成！nginx配置已更新: $NGINX_CONF_PATH"
else
    echo "错误: nginx配置测试失败"
    exit 1
fi

# 创建必要的目录并设置权限
echo "创建并设置目录权限..."
sudo mkdir -p "${NGINX_STATIC_PATH}" "${NGINX_MEDIA_PATH}"
sudo chown -R nginx:nginx "${NGINX_STATIC_PATH}" "${NGINX_MEDIA_PATH}"

# 显示配置信息
echo "
Nginx配置信息:
- 监听端口: ${NGINX_PORT}
- 服务器名: ${NGINX_SERVER_NAME}
- 上游服务器: ${NGINX_UPSTREAM_HOST}:${NGINX_UPSTREAM_PORT}
- 静态文件路径: ${NGINX_STATIC_PATH}
- 媒体文件路径: ${NGINX_MEDIA_PATH}
"
