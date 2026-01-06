import logging
from datetime import datetime

from django.apps import AppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class DcrmConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dcrm"
    verbose_name = _("DCRM")

    def ready(self) -> None:
        """
        初始化应用
        """
        from dcrm.signals import signals  # noqa: F401
        from dcrm.signals.counters import tracker_models_register
        from dcrm.views.api.schemas.dynamic import register_ninja_schema
        from dcrm.views.autocomplete import register_or_get_autocomplete_views
        from dcrm.views.imports.registrations import register_import_views

        self.has_datacenter = None
        self.has_superuser = None
        self.model_predictor = None
        self.start_time = datetime.now()

        try:
            # 注册所有导入视图
            register_import_views()
            # 注册所有Autocomplete视图
            register_or_get_autocomplete_views()
            # 注册所有Ninja 模型的 Ninja Schema
            register_ninja_schema()
            # 注册统计追踪器
            tracker_models_register()

            from dcrm.tasks.census import send_census_report_job
            from dcrm.tasks.counters import auto_fix_cached_counts

            auto_fix_cached_counts.delay(interval=settings.AUTOFIX_CACHE_COUNT_INTERVAL)
            # 发送使用情况统计
            send_census_report_job.delay()

        except Exception as e:
            logger.error(f"DCRM应用初始化失败: {e}")

        logger.info("DCRM应用初始化完成")
