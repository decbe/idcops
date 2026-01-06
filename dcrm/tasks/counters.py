import logging
from datetime import timedelta

import django_rq
from django.core.management import call_command
from django_rq import job

logger = logging.Logger(__name__)


@job("default", timeout=60)
def auto_fix_cached_counts(interval=60) -> None:
    """自动修复缓存字段计数器
    在 interval 时间范围内只允许执行/入队一次
    """
    # 获取 redis 连接
    connection = django_rq.get_connection("default")
    lock_key = "auto_fix_cached_counts:lock"

    # 尝试获取锁
    got_lock = connection.set(lock_key, "1", nx=True, ex=interval)
    if not got_lock:
        logger.warning("auto_fix_cached_counts: 已存在锁，跳过本次执行")
        return None

    queue = django_rq.get_queue("default")
    call_command("fix_cached_counts")
    job = queue.enqueue_in(
        timedelta(seconds=interval),
        auto_fix_cached_counts,
        interval=interval,
    )
    logger.info(f"auto_fix_cached_counts: {job.id}")
    return None
