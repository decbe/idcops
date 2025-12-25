#!/bin/bash

# PostgreSQL数据库自动备份和恢复脚本
# 功能：支持全量备份、单库备份、自动清理、数据库恢复

set -euo pipefail

# 项目 .env 路径（脚本位于 contrib/ 下，.env 在项目根目录）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"

# 内置默认配置（不再使用外部配置文件）
BACKUP_DIR="$PROJECT_ROOT/backups/postgresql"
LOG_FILE="$PROJECT_ROOT/logs/postgresql_backup.log"
DAYS_TO_KEEP=30
COMPRESS_LEVEL=6
BACKUP_FORMAT="plain"  # plain, custom, directory
ENCRYPT_BACKUP=false
ENCRYPT_PASSWORD=""

# 初始化目录与备份后缀
init_config() {
    mkdir -p "$BACKUP_DIR" "$(dirname "$LOG_FILE")" 2>/dev/null || true
    case "$BACKUP_FORMAT" in
        "custom") BACKUP_EXT="dump" ;;
        "directory") BACKUP_EXT="dir" ;;
        *) BACKUP_EXT="sql" ;;
    esac
}

# 日志记录函数
log() {
    local level="INFO"
    if [[ $# -gt 1 ]]; then
        level="$1"
        shift
    fi
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
    
    # 如果需要邮件通知且级别为ERROR
    # 邮件通知功能已移除配置文件依赖，若需可自行扩展
}

# 错误处理函数
error_exit() {
    log "ERROR" "$1"
    exit 1
}

# 检查依赖
check_dependencies() {
    local deps=("pg_dump" "pg_restore" "psql" "gzip")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            error_exit "缺少必要依赖: $dep"
        fi
    done
    if [[ "${ENCRYPT_BACKUP:-false}" == "true" ]]; then
        if ! command -v "openssl" &> /dev/null; then
            error_exit "启用了加密备份，但未安装 openssl"
        fi
    fi
}

# 检查数据库连接
check_db_connection() {
    if ! PGPASSWORD="$PG_PASSWORD" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "SELECT 1;" > /dev/null 2>&1; then
        error_exit "无法连接到PostgreSQL服务器"
    fi
}

# 仅使用项目 .env 指定的数据库
get_database_name() {
    echo "$POSTGRES_DB"
}

# 从项目 .env 读取数据库连接信息
load_project_env() {
    if [[ -f "$ENV_FILE" ]]; then
        while IFS= read -r line || [[ -n "$line" ]]; do
            [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
            [[ ! "$line" =~ ^POSTGRES_ ]] && continue
            key="${line%%=*}"
            value="${line#*=}"
            # 去掉包裹引号
            if [[ "$value" == '"'*'"' ]]; then
                value="${value:1:-1}"
            elif [[ "$value" == "'"*"'" ]]; then
                value="${value:1:-1}"
            fi
            # 去掉行尾 CR（Windows 格式）
            value="${value%$'\r'}"
            export "$key"="$value"
        done < "$ENV_FILE"
    fi

    # 兼容默认值（与 settings.py 一致）
    POSTGRES_DB="${POSTGRES_DB:-dcrm}"
    PG_HOST="${POSTGRES_HOST:-postgres}"
    PG_PORT="${POSTGRES_PORT:-5432}"
    PG_USER="${POSTGRES_USER:-postgres}"
    PG_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
}

# 检查磁盘空间
check_disk_space() {
    local required_space=$((1024 * 1024 * 2))  # 默认要求2GB空间
    local available_space=$(df "$BACKUP_DIR" | awk 'NR==2 {print $4}')
    
    if [[ $available_space -lt $required_space ]]; then
        log "WARNING" "磁盘空间可能不足，可用空间: ${available_space}KB"
        return 1
    fi
    return 0
}

# 执行数据库备份
backup_database() {
    local db_name="${1:-$(get_database_name)}"
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_file="${BACKUP_DIR}/${db_name}_${timestamp}.${BACKUP_EXT}"
    local compress_cmd=""
    
    log "INFO" "开始备份数据库: $db_name"
    
    # 构建备份命令
    local backup_cmd="PGPASSWORD=\"$PG_PASSWORD\" pg_dump -h $PG_HOST -p $PG_PORT -U $PG_USER -d $db_name"
    
    case "$BACKUP_FORMAT" in
        "custom")
            backup_cmd+=" -Fc -v -f ${backup_file}"
            ;;
        "directory")
            backup_cmd+=" -Fd -v -f ${backup_file}"
            ;;
        "plain")
            backup_cmd+=" -Fp -v"
            compress_cmd=" | gzip -c${COMPRESS_LEVEL} > ${backup_file}.gz"
            ;;
    esac
    
    # 执行备份
    if [[ -n "$compress_cmd" ]]; then
        eval "$backup_cmd $compress_cmd"
    else
        eval "$backup_cmd"
    fi
    
    if [[ $? -eq 0 ]]; then
        # 加密备份（如果启用）
        if [[ "$ENCRYPT_BACKUP" == "true" && -n "$ENCRYPT_PASSWORD" ]]; then
            if [[ "$BACKUP_FORMAT" == "plain" ]]; then
                backup_file="${backup_file}.gz"
            fi
            openssl enc -aes-256-cbc -salt -in "$backup_file" -out "${backup_file}.enc" -k "$ENCRYPT_PASSWORD"
            rm -f "$backup_file"
            backup_file="${backup_file}.enc"
        fi
        
        log "INFO" "数据库 $db_name 备份成功: $backup_file"
        echo "$backup_file"
    else
        log "ERROR" "数据库 $db_name 备份失败"
        return 1
    fi
}

# 备份所有数据库
backup_project_database() {
    log "INFO" "开始备份项目数据库"
    if ! check_disk_space; then
        log "WARNING" "继续备份，但磁盘空间可能不足"
    fi
    backup_database "$(get_database_name)"
}

# 清理旧备份
cleanup_old_backups() {
    log "INFO" "开始清理超过 $DAYS_TO_KEEP 天的旧备份"
    
    local files_deleted=0
    while IFS= read -r -d '' file; do
        rm -f "$file"
        ((files_deleted++))
        log "INFO" "删除旧备份: $file"
    done < <(find "$BACKUP_DIR" -name "*.${BACKUP_EXT}*" -mtime "+$DAYS_TO_KEEP" -print0)
    
    log "INFO" "清理完成，共删除 $files_deleted 个旧备份文件"
}

# 显示备份列表
list_backups() {
    local db_name="$1"
    local pattern="*${db_name}*.${BACKUP_EXT}*"
    
    echo "可用的备份文件:"
    find "$BACKUP_DIR" -name "$pattern" -type f -printf "%T@ %Tc %p\n" | sort -n | \
    while read -r line; do
        echo "  $line"
    done
}

# 恢复数据库
restore_database() {
    local backup_file="$1"
    local db_name="${2:-$POSTGRES_DB}"
    local options="$3"
    local temp_file=""
    
    log "INFO" "开始恢复数据库 $db_name"
    
    # 检查备份文件是否存在
    if [[ ! -f "$backup_file" && ! -d "$backup_file" ]]; then
        error_exit "备份文件不存在: $backup_file"
    fi
    
    # 解压和解密处理
    local restore_file="$backup_file"
    local decrypt_cmd=""
    local decompress_cmd=""
    
    # 检查是否需要解密
    if [[ "$backup_file" == *.enc ]]; then
        if [[ -z "$ENCRYPT_PASSWORD" ]]; then
            error_exit "备份文件已加密，但未设置解密密码"
        fi
        restore_file="${backup_file%.enc}"
        decrypt_cmd="openssl enc -aes-256-cbc -d -in '$backup_file' -out '$restore_file' -k '$ENCRYPT_PASSWORD' && "
    fi
    
    # 检查是否需要解压
    if [[ "$backup_file" == *.gz && "$BACKUP_FORMAT" == "plain" ]]; then
        decompress_cmd="gzip -dc '$restore_file' | "
        temp_file=$(mktemp)
        restore_file="$temp_file"
    fi
    
    # 构建恢复命令
    local restore_cmd=""
    if [[ "$backup_file" == *.dump || "$backup_file" == *.dir ]]; then
        # 自定义格式或目录格式
        restore_cmd="PGPASSWORD=\"$PG_PASSWORD\" pg_restore -h $PG_HOST -p $PG_PORT -U $PG_USER -d $db_name -v -c $options"
        if [[ "$backup_file" == *.dir ]]; then
            restore_cmd+=" -Fd"
        else
            restore_cmd+=" -Fc"
        fi
        restore_cmd+=" '$restore_file'"
    else
        # 纯文本格式
        restore_cmd="${decompress_cmd}PGPASSWORD=\"$PG_PASSWORD\" psql -h $PG_HOST -p $PG_PORT -U $PG_USER -d $db_name -v ON_ERROR_STOP=1 $options"
    fi
    
    # 执行恢复
    eval "${decrypt_cmd}${restore_cmd}"
    
    local result=$?
    
    # 清理临时文件
    [[ -n "${temp_file:-}" && -f "${temp_file:-}" ]] && rm -f "$temp_file"
    [[ -n "$decrypt_cmd" && -f "$restore_file" ]] && rm -f "$restore_file"
    
    if [[ $result -eq 0 ]]; then
        log "INFO" "数据库 $db_name 恢复成功"
    else
        error_exit "数据库 $db_name 恢复失败"
    fi
}

# 显示使用说明
usage() {
    cat << EOF
使用方法: $0 [选项]

选项:
  --backup                备份当前项目 .env 指定的数据库
  --restore file [db]     从备份文件恢复到当前项目数据库（可选指定db覆盖）
  --list                  列出当前项目数据库的备份文件
  --cleanup               清理旧备份文件
  --config                显示当前配置
  --help                  显示此帮助信息

示例:
  $0 --backup                   # 备份项目数据库
  $0 --list                     # 列出该库的所有备份
  $0 --restore backup.dump      # 恢复到项目数据库
  $0 --restore backup.dump other_db # 恢复到指定数据库
  $0 --cleanup                  # 清理旧备份

项目环境: $ENV_FILE

Crontab 示例:
  # 每天 02:00 执行备份，并将日志追加到 logs/postgresql_backup.log
  0 2 * * * cd "$PROJECT_ROOT" && bash $0 --backup >> ./logs/postgresql_backup.log 2>&1

  # 每周日 03:00 清理超过保留天数的旧备份
  0 3 * * 0 cd "$PROJECT_ROOT" && bash $0 --cleanup >> ./logs/postgresql_backup.log 2>&1
EOF
}

# 主函数
main() {
    # 初始化配置
    init_config
    # 读取项目 .env 数据库配置
    load_project_env
    
    # 检查依赖
    check_dependencies
    
    # 解析命令行参数
    case "${1:-}" in
        --backup)
            check_db_connection
            backup_project_database
            cleanup_old_backups
            ;;
        --restore)
            if [[ $# -lt 2 ]]; then
                error_exit "恢复操作需要指定备份文件（可选第2参数指定数据库名）"
            fi
            check_db_connection
            restore_database "$2" "${3:-}" "${4:-}"
            ;;
        --list)
            list_backups "$(get_database_name)"
            ;;
        --cleanup)
            cleanup_old_backups
            ;;
        --config)
            echo "当前配置:"
            echo "BACKUP_DIR=$BACKUP_DIR"
            echo "BACKUP_FORMAT=$BACKUP_FORMAT"
            echo "DAYS_TO_KEEP=$DAYS_TO_KEEP"
            echo "ENV_FILE=$ENV_FILE"
            ;;
        --help|-h)
            usage
            ;;
        *)
            usage
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"