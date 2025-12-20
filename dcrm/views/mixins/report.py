from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dcrm.utilities.lookup import create_trunc_function, format_date_display


class ReportPeriodMixin:
    """
    报表时间范围处理Mixin

    提供通用的时间范围处理功能，包括：
    - 时间范围选项配置
    - 日期范围计算
    - 对比时间计算
    - 聚合选项配置
    """

    # 聚合选项配置
    AGGREGATION_OPTIONS = [
        {"value": "day", "label": _("天")},
        {"value": "week", "label": _("周")},
        {"value": "month", "label": _("月")},
        {"value": "quarter", "label": _("季")},
        {"value": "year", "label": _("年")},
    ]

    # 时间范围选项配置
    PERIOD_OPTIONS = [
        {"value": "this_week", "label": _("本周")},
        {"value": "this_month", "label": _("本月")},
        {"value": "this_quarter", "label": _("本季度")},
        {"value": "this_year", "label": _("今年")},
        {"value": "last_week", "label": _("上周")},
        {"value": "last_month", "label": _("上月")},
        {"value": "week", "label": _("最近1周")},
        {"value": "month", "label": _("最近1个月")},
        {"value": "quarter", "label": _("最近3个月")},
        {"value": "half_year", "label": _("最近6个月")},
        {"value": "year", "label": _("最近1年")},
        {"value": "all", "label": _("全部")},
    ]

    # 聚合
    AGGREGATION = "week"
    # 周期
    PERIOD = "month"

    def get_metadata(
        self, aggregation: str = None, period: str = None
    ) -> Dict[str, Any]:
        """
        获取报表元数据

        Args:
            aggregation: 聚合方式，如果为None则从request.GET获取
            period: 时间范围，如果为None则从request.GET获取

        Returns:
            包含聚合和时间范围选项的元数据字典
        """
        if aggregation is None:
            aggregation = getattr(self.request, "GET", {}).get("aggregation", "week")
        if period is None:
            period = getattr(self.request, "GET", {}).get("period", "quarter")

        return {
            "aggregation": aggregation,
            "aggregation_options": [
                {
                    "value": option["value"],
                    "label": option["label"],
                    "selected": option["value"] == aggregation,
                }
                for option in self.AGGREGATION_OPTIONS
            ],
            "period": period,
            "period_options": [
                {
                    "value": option["value"],
                    "label": option["label"],
                    "selected": option["value"] == period,
                }
                for option in self.PERIOD_OPTIONS
            ],
        }

    def get_date_range(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        根据指定的start_date, end_date请求参数构建日期范围

        Args:
            start_date: 开始日期字符串，格式为 'YYYY-MM-DD'，如果为None则使用默认值
            end_date: 结束日期字符串，格式为 'YYYY-MM-DD'，如果为None则使用当前日期

        Returns:
            (起始日期, 结束日期) 元组，日期都可能为None
            起始日期的时间定为 00:00:00（不用操作）
            结束日期的时间定为 第二天的 00:00:00（请修正）
        """
        # 处理结束日期
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                # 结束日期的时间定为第二天的 00:00:00
                end_dt = end_dt + timedelta(days=1)
                end_dt = timezone.make_aware(end_dt)
            except ValueError:
                # 如果日期格式不正确，使用当前时间
                end_dt = timezone.now()
        else:
            # 默认使用当前时间
            end_dt = timezone.now()

        # 处理开始日期
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                start_dt = timezone.make_aware(start_dt)
            except ValueError:
                # 如果日期格式不正确，设置为None
                start_dt = None
        else:
            # 默认设置为None
            start_dt = None

        return start_dt, end_dt

    def get_prev_date_range(
        self, start_date: Optional[datetime], end_date: Optional[datetime]
    ) -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        根据给定的日期范围获取上一个周期的时间范围

        Args:
            start_date: 当前周期开始时间，可能为None
            end_date: 当前周期结束时间，可能为None

        Returns:
            (上期开始时间, 上期结束时间) 元组，可能为None
        """
        # 如果开始时间或结束时间为None，则无法计算上一个周期
        if start_date is None or end_date is None:
            return None, None

        # 确保开始时间不晚于结束时间
        if start_date > end_date:
            return None, None

        # 计算当前周期的天数
        delta = end_date - start_date

        # 上一个周期的结束时间是当前周期开始时间的前一秒
        prev_end = start_date - timedelta(microseconds=1)

        # 上一个周期的开始时间是上一个周期结束时间减去相同的天数
        prev_start = prev_end - delta

        return prev_start, prev_end

    def build_trend_dates(
        self, aggregation: str, queryset: Any, date_field: str = "created_at"
    ) -> List[str]:
        """基于给定 queryset 与聚合方式构建 dates 列表。
        - 参数 queryset 可为 _build_log_query 的查询结果
        """
        qs = queryset.annotate(
            period=create_trunc_function(aggregation, date_field)
        ).values("period")
        return format_date_display(list(qs), aggregation).get("dates", [])
