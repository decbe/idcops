"""Census（使用情况统计）任务

发送匿名使用情况数据，帮助开发者了解部署数量和版本分布。
仅上报：软件版本、Python版本、匿名部署ID（不包含任何用户数据）

用户可通过以下方式关闭此功能：
- 设置环境变量 CENSUS_REPORTING_ENABLED=0
- 设置环境变量 ISOLATED_DEPLOYMENT=1（离线部署模式）
"""

import logging
import sys

import requests
from django.conf import settings
from django_rq import job

logger = logging.getLogger(__name__)


def send_census_report():
    """发送匿名使用情况统计报告。

    上报的数据：
    - version: 软件版本号
    - python_version: Python 版本号
    - deployment_id: 基于 SECRET_KEY 生成的匿名部署ID（16位哈希）

    注意：不会上报任何用户数据、IP地址或其他敏感信息。
    """
    # 检查是否启用离线部署模式
    if getattr(settings, "ISOLATED_DEPLOYMENT", False):
        logger.info("离线部署模式已启用，跳过使用情况上报")
        return False

    # 检查是否启用 Census 上报
    if not getattr(settings, "CENSUS_REPORTING_ENABLED", True):
        logger.info("使用情况上报已禁用，跳过")
        return False

    # 获取上报地址
    census_url = getattr(
        settings, "CENSUS_URL", "https://ndcrm.yuzekeji.cn/api/census/"
    )

    # 构建上报数据
    census_data = {
        "version": getattr(settings, "VERSION", "unknown"),
        "python_version": sys.version.split()[0],
        "deployment_id": getattr(settings, "DEPLOYMENT_ID", ""),
    }

    logger.info(f"正在发送使用情况统计: {census_data}")

    try:
        response = requests.get(
            url=census_url,
            params=census_data,
            timeout=5,
            verify=False,
        )
        if response.ok:
            logger.info("使用情况统计发送成功")
            return True
        else:
            logger.warning(f"使用情况统计发送失败: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logger.warning(f"使用情况统计发送异常: {e}")
        return False


@job("default", timeout=60)
def send_census_report_job():
    """django-rq 后台任务：发送使用情况统计。

    使用方式：
        # 异步执行（推荐）
        send_census_report_job.delay()

        # 同步执行
        send_census_report_job()

    可在以下场景调用：
        - entrypoint.sh 启动时
        - 定时任务（rq-scheduler）
        - 管理命令
    """
    # 仅在非调试模式下发送
    if settings.DEBUG:
        logger.info("调试模式已启用，跳过使用情况上报")
        return

    return send_census_report()
