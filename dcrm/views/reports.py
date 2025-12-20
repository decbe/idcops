from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import (
    Avg,
    Case,
    Count,
    Exists,
    ExpressionWrapper,
    F,
    FloatField,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Concat
from django.http import JsonResponse
from django.http.response import JsonResponse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import TemplateView

from dcrm.models import (
    Device,
    DeviceModel,
    DeviceType,
    IPAddress,
    LogEntry,
    OnlineDevice,
    Rack,
    Subnet,
    Tenant,
)
from dcrm.models.choices import DeviceStatusChoices
from dcrm.utilities.lookup import create_trunc_function

from .mixins.base import BaseRequestMixin
from .mixins.report import ReportPeriodMixin


class DeviceReportView(ReportPeriodMixin, BaseRequestMixin, TemplateView):
    """设备报表视图"""

    template_name = "reports/device_report.html"

    def get_context_data(self, **kwargs) -> Any:
        context = super().get_context_data(**kwargs)

        # 获取URL参数
        aggregation = self.request.GET.get("aggregation", "week")
        period = self.request.GET.get("period", "quarter")

        # 获取元数据
        metadata = self.get_metadata(aggregation, period)

        context.update(
            {
                "title": _("设备报表"),
                "subtitle": _(f"{self.request.user.data_center}设备统计报表"),
                "metadata": metadata,
            }
        )
        return context


class DeviceReportDataView(ReportPeriodMixin, LoginRequiredMixin, View):
    """设备报表数据视图 - 用于AJAX请求"""

    def get(self, request, *args, **kwargs) -> JsonResponse:
        """返回设备报表的JSON数据"""
        data_center = request.user.data_center

        # 获取URL参数
        # period = request.GET.get("period", "quarter")
        aggregation = request.GET.get("aggregation", "week")
        period = self.get_date_range(
            request.GET.get("start", None), request.GET.get("end", None)
        )
        # 获取各种统计信息
        kpis = self.get_kpis(data_center, period)
        trend_stats = self.get_device_trend_data(data_center, aggregation, period)
        type_stats = self.get_device_type_distribution(data_center, period)
        tenant_stats = self.get_tenant_stats(data_center, period)

        return JsonResponse(
            {
                "kpis": kpis,
                "trend_stats": trend_stats,
                "type_stats": type_stats,
                "tenant_stats": tenant_stats,
                "aggregation": aggregation,
                "period": period,
            }
        )

    def _build_log_query(
        self, data_center, start_date: Optional[datetime], end_date: datetime
    ) -> Any:
        """构建日志查询条件"""
        query_conditions = {
            "data_center": data_center,
            "content_type": ContentType.objects.get_for_model(Device),
            "action_type__in": [
                "create",
                "device_migrate",
                "device_move_down",
            ],
        }
        if start_date:
            query_conditions["created_at__gte"] = start_date
        query_conditions["created_at__lte"] = end_date
        return LogEntry.objects.filter(**query_conditions)

    def _calc_percent(self, current_value: int, prev_value: int) -> float:
        """计算环比百分比，保留两位小数"""
        if prev_value > 0:
            return round(((current_value - prev_value) / prev_value) * 100, 2)
        return 100.0 if current_value > 0 else 0.0

    def get_kpis(self, data_center, period) -> Dict[str, Any]:
        """
        获取四个指标：总计、上架、迁移、下架（均为所选时间范围内的变更量）
        并返回与上期同比百分比
        """
        start_date, end_date = period

        logs = self._build_log_query(data_center, start_date, end_date)

        # 使用单个查询获取所有统计数据
        stats = logs.aggregate(
            created=Count("id", filter=Q(action_type="create")),
            migrated=Count("id", filter=Q(action_type="device_migrate")),
            moved_down=Count("id", filter=Q(action_type="device_move_down")),
        )

        created = stats["created"]
        migrated = stats["migrated"]
        moved_down = stats["moved_down"]
        total = created + migrated + moved_down

        # 计算上期时间范围和对比百分比
        total_change_percent = create_change_percent = migrate_change_percent = (
            move_down_change_percent
        ) = 0.0

        if start_date.year != 1970:
            prev_start, prev_end = self.get_prev_date_range(start_date, end_date)
            if prev_start and prev_end:
                prev_logs = self._build_log_query(data_center, prev_start, prev_end)
                # 同样使用单个查询获取上期统计数据
                prev_stats = prev_logs.aggregate(
                    prev_created=Count("id", filter=Q(action_type="create")),
                    prev_migrated=Count("id", filter=Q(action_type="device_migrate")),
                    prev_moved_down=Count(
                        "id", filter=Q(action_type="device_move_down")
                    ),
                )

                prev_created = prev_stats["prev_created"]
                prev_migrated = prev_stats["prev_migrated"]
                prev_moved_down = prev_stats["prev_moved_down"]
                prev_total = prev_created + prev_migrated + prev_moved_down

                create_change_percent = self._calc_percent(created, prev_created)
                migrate_change_percent = self._calc_percent(migrated, prev_migrated)
                move_down_change_percent = self._calc_percent(
                    moved_down, prev_moved_down
                )
                total_change_percent = self._calc_percent(total, prev_total)

        return {
            "total": total,
            "create": created,
            "migrate": migrated,
            "move_down": moved_down,
            "total_change_percent": total_change_percent,
            "create_change_percent": create_change_percent,
            "migrate_change_percent": migrate_change_percent,
            "move_down_change_percent": move_down_change_percent,
        }

    def get_device_trend_data(
        self, data_center, aggregation="week", period="half_year"
    ) -> Dict[str, List]:
        """获取设备变更趋势数据（按所选聚合维度）"""
        # 获取日期范围
        start_date, end_date = period

        # 构建查询条件
        logs = self._build_log_query(data_center, start_date, end_date)

        # 根据聚合方式分组统计（数据库无关）
        logs = logs.annotate(period=create_trunc_function(aggregation, "created_at"))

        trend_stats = (
            logs.values("period", "action_type")
            .annotate(count=Count("id"))
            .order_by("period")
        )

        # 重新组织数据
        trend_data = {
            "dates": [],
            "create": [],
            "device_migrate": [],
            "device_move_down": [],
        }

        # 获取所有时间段（兼容 date 与 datetime）
        def normalize_to_date(value) -> Any:
            from datetime import datetime as dt

            if isinstance(value, dt):
                return value.date()
            return value

        raw_periods = [normalize_to_date(item["period"]) for item in trend_stats]
        periods = sorted(set(raw_periods))
        if periods:
            # 格式化日期显示
            if aggregation == "day":
                trend_data["dates"] = [
                    period.strftime("%Y-%m-%d") for period in periods
                ]
            elif aggregation == "week":
                trend_data["dates"] = [period.strftime("%Y-W%U") for period in periods]
            elif aggregation == "month":
                trend_data["dates"] = [period.strftime("%Y-%m") for period in periods]
            elif aggregation == "quarter":
                trend_data["dates"] = [
                    f"{period.year}-Q{(period.month-1)//3+1}" for period in periods
                ]
            elif aggregation == "year":
                trend_data["dates"] = [period.strftime("%Y") for period in periods]
            else:
                trend_data["dates"] = [
                    period.strftime("%Y-%m-%d") for period in periods
                ]

            # 初始化数据
            for action in ["create", "device_migrate", "device_move_down"]:
                trend_data[action] = [0] * len(periods)

            # 填充数据
            for item in trend_stats:
                normalized_period = normalize_to_date(item["period"])
                if normalized_period in periods:
                    period_index = periods.index(normalized_period)
                    trend_data[item["action_type"]][period_index] = item["count"]

        return trend_data

    def get_device_type_distribution(self, data_center, period) -> List[Dict[str, Any]]:
        """获取设备类型分布数据（按所选时间范围内新建设备统计）"""
        start_date, end_date = period

        device_qs = OnlineDevice.objects.filter(data_center=data_center)
        if start_date:
            device_qs = device_qs.filter(created_at__gte=start_date)
        device_qs = device_qs.filter(created_at__lte=end_date)

        type_stats_queryset = (
            device_qs.values("type__name")
            .annotate(
                value=Count("id"),
                name=Case(
                    When(type__name__isnull=True, then=Value("未指定")),
                    When(type__name="", then=Value("未指定")),
                    default=F("type__name"),
                    output_field=models.CharField(),
                ),
            )
            .filter(value__gt=0)
            .order_by("-value")
            .values("name", "value")
        )

        return list(type_stats_queryset)

    def get_tenant_stats(self, data_center, period) -> List[Dict[str, Any]]:
        """获取客户设备变更统计（表格形式）"""
        start_date, end_date = period

        # 构建查询条件

        logs = self._build_log_query(data_center, start_date, end_date)

        # 按客户和操作类型分组统计
        tenant_stats_queryset = (
            logs.values("postchange_data__tenant")
            .annotate(
                create_count=Count("id", filter=Q(action_type="create")),
                migrate_count=Count("id", filter=Q(action_type="device_migrate")),
                move_down_count=Count("id", filter=Q(action_type="device_move_down")),
            )
            .order_by("postchange_data__tenant")
        )
        tids = set([item["postchange_data__tenant"] for item in tenant_stats_queryset])
        tenants = (
            Tenant.objects.filter(id__in=tids)
            .annotate(
                icon_url=Case(
                    When(icon__isnull=True, then=Value("")),
                    When(icon="", then=Value("")),
                    default=Concat(Value(settings.MEDIA_URL), F("icon")),
                    output_field=models.CharField(),
                )
            )
            .values("id", "name", "icon_url", "device_count")
        )
        tenant_stats = []
        for item in tenant_stats_queryset:
            # 只显示有变更的客户
            if (
                item["create_count"] > 0
                or item["migrate_count"] > 0
                or item["move_down_count"] > 0
            ):
                tenant_stats.append(
                    {
                        "tenant": tenants.get(id=item["postchange_data__tenant"]),
                        "create_count": item["create_count"],
                        "migrate_count": item["migrate_count"],
                        "move_down_count": item["move_down_count"],
                    }
                )

        return tenant_stats


class RackReportView(ReportPeriodMixin, BaseRequestMixin, TemplateView):
    """机柜报表视图"""

    template_name = "reports/rack_report.html"

    def get_context_data(self, **kwargs) -> Any:
        context = super().get_context_data(**kwargs)

        aggregation = self.request.GET.get("aggregation", "week")
        period = self.request.GET.get("period", "quarter")

        metadata = self.get_metadata(aggregation, period)

        context.update(
            {
                "title": _("机柜报表"),
                "subtitle": _(f"{self.request.user.data_center}机柜统计报表"),
                "metadata": metadata,
            }
        )
        return context


class RackReportDataView(ReportPeriodMixin, LoginRequiredMixin, View):
    """机柜报表数据视图 - 用于AJAX请求"""

    def _build_rack_log_query(
        self, data_center, start_date: Optional[datetime], end_date: datetime
    ) -> Any:
        query_conditions = {
            "data_center": data_center,
            "content_type": ContentType.objects.get_for_model(Rack),
            "action_type__in": [
                "rack_allocate",
                "rack_deallocate",
            ],
        }
        if start_date:
            query_conditions["created_at__gte"] = start_date
        query_conditions["created_at__lte"] = end_date
        return LogEntry.objects.filter(**query_conditions)

    def _calc_percent(self, current_value: int, prev_value: int) -> float:
        if prev_value > 0:
            return round(((current_value - prev_value) / prev_value) * 100, 2)
        return 100.0 if current_value > 0 else 0.0

    def get_kpis(self, data_center, period) -> Dict[str, Any]:
        start_date, end_date = period

        logs = self._build_rack_log_query(data_center, start_date, end_date)

        # 使用单个查询获取所有统计数据
        stats = logs.aggregate(
            allocated=Count("id", filter=Q(action_type="rack_allocate")),
            deallocated=Count("id", filter=Q(action_type="rack_deallocate")),
        )

        allocated = stats["allocated"]
        deallocated = stats["deallocated"]
        total = allocated + deallocated

        total_change_percent = allocate_change_percent = deallocate_change_percent = 0.0
        if start_date.year != 1970 and end_date:
            prev_start, prev_end = self.get_prev_date_range(start_date, end_date)
            if prev_start and prev_end:
                prev_logs = self._build_rack_log_query(
                    data_center, prev_start, prev_end
                )
                # 同样使用单个查询获取上期统计数据
                prev_stats = prev_logs.aggregate(
                    prev_allocated=Count("id", filter=Q(action_type="rack_allocate")),
                    prev_deallocated=Count(
                        "id", filter=Q(action_type="rack_deallocate")
                    ),
                )

                prev_allocated = prev_stats["prev_allocated"]
                prev_deallocated = prev_stats["prev_deallocated"]
                prev_total = prev_allocated + prev_deallocated

                allocate_change_percent = self._calc_percent(allocated, prev_allocated)
                deallocate_change_percent = self._calc_percent(
                    deallocated, prev_deallocated
                )
                total_change_percent = self._calc_percent(total, prev_total)

        return {
            "total": total,
            "allocate": allocated,
            "deallocate": deallocated,
            "total_change_percent": total_change_percent,
            "allocate_change_percent": allocate_change_percent,
            "deallocate_change_percent": deallocate_change_percent,
        }

    def get_rack_trend_data(self, data_center, aggregation, period) -> Dict[str, List]:
        start_date, end_date = period
        logs = self._build_rack_log_query(data_center, start_date, end_date)
        logs = logs.annotate(period=create_trunc_function(aggregation, "created_at"))
        trend_stats = (
            logs.values("period", "action_type")
            .annotate(count=Count("id"))
            .order_by("period")
        )

        def normalize_to_date(value) -> Any:
            from datetime import datetime as dt

            if isinstance(value, dt):
                return value.date()
            return value

        trend_data = {
            "dates": [],
            "rack_allocate": [],
            "rack_deallocate": [],
        }

        raw_periods = [normalize_to_date(item["period"]) for item in trend_stats]
        periods = sorted(set(raw_periods))
        if periods:
            if aggregation == "day":
                trend_data["dates"] = [p.strftime("%Y-%m-%d") for p in periods]
            elif aggregation == "week":
                trend_data["dates"] = [p.strftime("%Y-W%U") for p in periods]
            elif aggregation == "month":
                trend_data["dates"] = [p.strftime("%Y-%m") for p in periods]
            elif aggregation == "quarter":
                trend_data["dates"] = [f"{p.year}-Q{(p.month-1)//3+1}" for p in periods]
            elif aggregation == "year":
                trend_data["dates"] = [p.strftime("%Y") for p in periods]
            else:
                trend_data["dates"] = [p.strftime("%Y-%m-%d") for p in periods]

            trend_data["rack_allocate"] = [0] * len(periods)
            trend_data["rack_deallocate"] = [0] * len(periods)

            for item in trend_stats:
                normalized_period = normalize_to_date(item["period"])
                if normalized_period in periods:
                    idx = periods.index(normalized_period)
                    trend_data[item["action_type"]][idx] = item["count"]

        return trend_data

    def get_rack_status_distribution(self, data_center) -> List[Dict[str, Any]]:
        racks = Rack.objects.filter(data_center=data_center, status__isnull=False)
        qs = (
            racks.values("status__name")
            .annotate(
                value=Count("id"),
                name=Case(
                    When(status__name__isnull=True, then=Value("未指定")),
                    When(status__name="", then=Value("未指定")),
                    default=F("status__name"),
                    output_field=models.CharField(),
                ),
            )
            .filter(value__gt=0)
            .order_by("-value")
            .values("name", "value")
        )
        return list(qs)

    def get_room_rack_stacked_bars(self, data_center) -> List[Dict[str, Any]]:
        """
        返回水平堆叠条形图所需的数据：
        - 统计每个房间可上架状态(allowed_mount=True)的机柜数量
        - 仅返回数量大于 0 的房间
        - 字段：name(房间名称)、value(机柜总数)、room_id、children(各状态明细)
        - children 作为堆叠条形图的各状态分段
        """
        # 单次查询：按房间+状态分组统计（仅统计允许上架的状态）
        rows = list(
            Rack.objects.filter(data_center=data_center)
            .values("room_id", "room__name", "status__name")
            .annotate(value=Count("id", filter=Q(status__allowed_mount=True)))
            .filter(value__gt=0)
            .order_by("room_id")
        )

        # 组装结构
        room_map: Dict[int, Dict[str, Any]] = {}
        for item in rows:
            room_id = item["room_id"]
            room_name = item["room__name"]
            status_name = item["status__name"] or _("未指定")
            count = item["value"] or 0

            if room_id not in room_map:
                room_map[room_id] = {
                    "room_id": room_id,
                    "name": room_name,
                    "value": 0,
                    "children": [],
                }
            room_map[room_id]["children"].append({"name": status_name, "value": count})
            room_map[room_id]["value"] += count

        result = [v for v in room_map.values() if v["value"] > 0]
        result.sort(key=lambda x: x["value"], reverse=True)
        return result

    def get_tenant_stats(self, data_center, period) -> List[Dict[str, Any]]:
        """
        客户维度统计：
        - tenant 基本信息（name, icon_url, device_count/rack_count 可选）
        - total_racks: 当前租户拥有的机柜总数（按 Rack.tenant 统计）
        - allocated: 期间内分配的机柜数量（日志 action_type=rack_allocate）
        - deallocated: 期间内释放的机柜数量（日志 action_type=rack_deallocate）
        - avg_utilization: 机柜平均使用率（按租户名下每个机柜 used_units/u_height 平均值）
        支持对 allocated/deallocated/avg_utilization 排序由前端或后端控制（此处维持不排序，交给前端）
        """
        start_date, end_date = period

        # 1) 租户机柜总数（当前时点）
        rack_totals = (
            Rack.objects.filter(data_center=data_center, tenant__isnull=False)
            .values("tenant")
            .annotate(total_racks=Count("id"))
        )
        tenant_to_total = {item["tenant"]: item["total_racks"] for item in rack_totals}

        # 2) 期间内分配/释放统计（来源于 LogEntry）
        logs = self._build_rack_log_query(data_center, start_date, end_date)
        # 分配：租户在 postchange_data 中；释放：租户在 prechange_data 中
        allocated_stats = (
            logs.filter(action_type="rack_allocate")
            .values("postchange_data__tenant")
            .annotate(allocated=Count("id"))
        )
        deallocated_stats = (
            logs.filter(action_type="rack_deallocate")
            .values("prechange_data__tenant")
            .annotate(deallocated=Count("id"))
        )
        tenant_to_changes: Dict[int, Dict[str, int]] = {}
        for item in allocated_stats:
            tid = item["postchange_data__tenant"]
            if tid is None:
                continue
            tenant_to_changes.setdefault(tid, {"allocated": 0, "deallocated": 0})[
                "allocated"
            ] = item["allocated"]
        for item in deallocated_stats:
            tid = item["prechange_data__tenant"]
            if tid is None:
                continue
            tenant_to_changes.setdefault(tid, {"allocated": 0, "deallocated": 0})[
                "deallocated"
            ] = item["deallocated"]

        # 3) 平均使用率（基于 Device.model.height 汇总到 Rack，再对 Rack 求平均）
        # 仅统计活跃/在架设备：mounted、migrated
        rack_utilization = (
            Rack.objects.filter(data_center=data_center, tenant__isnull=False)
            .values("tenant")
            .annotate(
                used_units=Coalesce(
                    Sum(
                        Coalesce(
                            F("device__height"), F("device__model__height"), Value(0)
                        ),
                        filter=Q(
                            device__status__in=[
                                DeviceStatusChoices.MOUNTED,
                                DeviceStatusChoices.MIGRATED,
                            ]
                        ),
                        output_field=FloatField(),
                    ),
                    0.0,
                ),
                total_u=Coalesce(Sum("u_height"), 0),
            )
            .annotate(
                avg_util=Case(
                    When(
                        total_u__gt=0,
                        then=ExpressionWrapper(
                            F("used_units") / F("total_u"), output_field=FloatField()
                        ),
                    ),
                    default=Value(0.0),
                    output_field=FloatField(),
                )
            )
        )
        tenant_to_avg_util = {
            item["tenant"]: round((item["avg_util"] or 0.0) * 100, 2)
            for item in rack_utilization
        }

        # 4) 准备租户基础信息（名称与图标）
        tenant_ids = set(
            list(tenant_to_total.keys())
            + list(tenant_to_changes.keys())
            + list(tenant_to_avg_util.keys())
        )
        tenants_qs = (
            Tenant.objects.filter(id__in=tenant_ids)
            .annotate(
                icon_url=Case(
                    When(icon__isnull=True, then=Value("")),
                    When(icon="", then=Value("")),
                    default=Concat(Value(settings.MEDIA_URL), F("icon")),
                    output_field=models.CharField(),
                )
            )
            .values("id", "name", "icon_url")
        )
        tenants_map = {t["id"]: t for t in tenants_qs}

        # 5) 组装结果
        results: List[Dict[str, Any]] = []
        for tid in tenant_ids:
            tenant_info = tenants_map.get(tid)
            if not tenant_info:
                continue
            totals = tenant_to_total.get(tid, 0)
            changes = tenant_to_changes.get(tid, {"allocated": 0, "deallocated": 0})
            avg_util = tenant_to_avg_util.get(tid, 0.0)

            # 计算租户空闲机柜数量与空闲率（无在架/迁移设备的机柜）
            tenant_racks = Rack.objects.filter(data_center=data_center, tenant=tid)
            tenant_racks = tenant_racks.annotate(
                has_mounted=Exists(
                    Device.objects.filter(
                        rack=OuterRef("pk"),
                        status__in=[
                            DeviceStatusChoices.MOUNTED,
                            DeviceStatusChoices.MIGRATED,
                        ],
                    )
                )
            )
            free_racks = (
                tenant_racks.aggregate(
                    free=Sum(
                        Case(
                            When(has_mounted=False, then=Value(1)),
                            default=Value(0),
                            output_field=IntegerField(),
                        )
                    )
                )["free"]
                or 0
            )
            free_rate = round((free_racks / totals) * 100, 2) if totals > 0 else 0.0

            results.append(
                {
                    "tenant": tenant_info,
                    "total_racks": totals,
                    "allocated": changes.get("allocated", 0),
                    "deallocated": changes.get("deallocated", 0),
                    "avg_utilization": avg_util,
                    "free_racks": free_racks,
                    "free_rate": free_rate,
                }
            )

        # 按总机柜数倒序，如果相同按平均使用率倒序
        results.sort(
            key=lambda x: (x["total_racks"], x["avg_utilization"]), reverse=True
        )
        return results

    def get(self, request, *args, **kwargs) -> JsonResponse:
        data_center = request.user.data_center
        aggregation = request.GET.get("aggregation", "week")
        period = self.get_date_range(
            request.GET.get("start", None), request.GET.get("end", None)
        )

        kpis = self.get_kpis(data_center, period)
        trend_stats = self.get_rack_trend_data(data_center, aggregation, period)
        status_stats = self.get_rack_status_distribution(data_center)
        room_bar_stats = self.get_room_rack_stacked_bars(data_center)
        tenant_stats = self.get_tenant_stats(data_center, period)

        return JsonResponse(
            {
                "kpis": kpis,
                "trend_stats": trend_stats,
                "status_stats": status_stats,
                "room_bar_stats": room_bar_stats,
                "tenant_stats": tenant_stats,
                "aggregation": aggregation,
                "period": period,
            }
        )


class TenantReportView(ReportPeriodMixin, BaseRequestMixin, TemplateView):
    """租户报表视图"""

    template_name = "reports/tenant_report.html"

    def get_context_data(self, **kwargs) -> Any:
        context = super().get_context_data(**kwargs)

        aggregation = self.request.GET.get("aggregation", "week")
        period = self.request.GET.get("period", "quarter")

        metadata = self.get_metadata(aggregation, period)

        context.update(
            {
                "title": _("租户报表"),
                "subtitle": _(f"{self.request.user.data_center}租户统计报表"),
                "metadata": metadata,
            }
        )
        return context


class TenantReportDataView(ReportPeriodMixin, LoginRequiredMixin, View):
    """租户报表数据视图 - 用于AJAX请求"""

    def _build_log_query(
        self,
        data_center,
        start_date: Optional[datetime],
        end_date: datetime,
    ) -> Any:
        query_conditions = {"data_center": data_center}
        if start_date:
            query_conditions["created_at__gte"] = start_date
        query_conditions["created_at__lte"] = end_date
        return LogEntry.objects.filter(**query_conditions)

    def _build_tenant_log_query(
        self, data_center, start_date: Optional[datetime], end_date: datetime
    ) -> Any:
        """构建租户日志查询条件"""
        query_conditions = {
            "content_type": ContentType.objects.get_for_model(Tenant),
        }
        return self._build_log_query(data_center, start_date, end_date).filter(
            **query_conditions
        )

    def _calc_percent(self, current_value: int, prev_value: int) -> float:
        """计算环比百分比，保留两位小数"""
        if prev_value > 0:
            return round(((current_value - prev_value) / prev_value) * 100, 2)
        return 100.0 if current_value > 0 else 0.0

    def get_kpis(self, data_center, period) -> Dict[str, Any]:
        start_date, end_date = period

        # 当前租户总数
        total_tenants = Tenant.objects.filter(data_center=data_center).count()
        logs = self._build_tenant_log_query(data_center, start_date, end_date)
        new_tenants = logs.filter(action_type="create").count()
        logentries = self._build_log_query(data_center, start_date, end_date)
        # 优化查询，直接通过数据库获取不重复的租户数量
        # 从postchange_data中提取tenant字段并去重计数
        actived_tenants = (
            logentries.exclude(postchange_data__isnull=True)
            .exclude(postchange_data__tenant__isnull=True)
            .values_list("postchange_data__tenant", flat=True)
            .distinct()
            .count()
        )
        # 计算上期时间范围和对比百分比
        new_tenants_change_percent = 0.0
        actived_tenants_change_percent = 0.0

        if start_date is not None:
            # 对于本周、本月、本季度、今年，使用精确的对比时间
            if period in ["this_week", "this_month", "this_quarter", "this_year"]:
                prev_start, prev_end = self.get_prev_date_range(start_date, end_date)
            else:
                # 对于其他period，使用原有的相对时间计算
                duration = end_date - start_date
                prev_end = start_date - timedelta(microseconds=1)
                prev_start = prev_end - duration

            if prev_start and prev_end:
                # 查询上期新增租户数量
                prev_new_tenants = (
                    self._build_tenant_log_query(data_center, prev_start, prev_end)
                    .filter(action_type="create")
                    .count()
                )
                # 优化查询，直接通过数据库获取不重复的租户数量
                # 从postchange_data中提取tenant字段并去重计数
                prev_actived_tenants = (
                    self._build_log_query(data_center, prev_start, prev_end)
                    .exclude(postchange_data__isnull=True)
                    .exclude(postchange_data__tenant__isnull=True)
                    .values_list("postchange_data__tenant", flat=True)
                    .distinct()
                    .count()
                )

                # 计算新增租户数量与上期的百分比
                new_tenants_change_percent = self._calc_percent(
                    new_tenants, prev_new_tenants
                )

                actived_tenants_change_percent = self._calc_percent(
                    actived_tenants, prev_actived_tenants
                )

        return {
            "total": total_tenants,
            "new": new_tenants,
            "new_tenants_percent": new_tenants_change_percent,
            "actived": actived_tenants,
            "actived_change_percent": actived_tenants_change_percent,
        }

    def get_top_tenants(self, data_center, period) -> List[Dict[str, Any]]:
        """综合指标：每个租户的设备数、机柜数、使用率、空闲率，按设备数倒序（单查询实现）"""
        # 直接使用Tenant模型中的计数字段，避免子查询
        # 设备数、机柜数、子网数、IP地址数可以直接从Tenant模型字段获取
        # 使用率分子：已用U = sum(device.height or model.height)
        used_units_sq = (
            Device.objects.filter(
                data_center=data_center,
                rack__tenant=OuterRef("pk"),
                status__in=[DeviceStatusChoices.MOUNTED, DeviceStatusChoices.MIGRATED],
            )
            .annotate(h=Coalesce(F("height"), F("model__height"), Value(0)))
            .values("rack__tenant")
            .annotate(total=Coalesce(Sum("h", output_field=FloatField()), 0.0))
            .values("total")[:1]
        )

        # 使用率分母：总U = sum(rack.u_height)
        total_u_sq = (
            Rack.objects.filter(data_center=data_center, tenant=OuterRef("pk"))
            .values("tenant")
            .annotate(total=Coalesce(Sum("u_height"), 0))
            .values("total")[:1]
        )

        # 空闲机柜数：无已上架/迁移设备
        has_mounted_q = Exists(
            Device.objects.filter(
                rack=OuterRef("pk"),
                status__in=[DeviceStatusChoices.MOUNTED, DeviceStatusChoices.MIGRATED],
            )
        )
        free_count_sq = (
            Rack.objects.filter(data_center=data_center, tenant=OuterRef("pk"))
            .annotate(has_mounted=has_mounted_q)
            .values("tenant")
            .annotate(
                free=Coalesce(
                    Sum(
                        Case(
                            When(has_mounted=False, then=Value(1)),
                            default=Value(0),
                            output_field=IntegerField(),
                        )
                    ),
                    0,
                ),
            )
            .values("free")[:1]
        )

        tenants_qs = (
            Tenant.objects.filter(data_center=data_center)
            .annotate(
                icon_url=Case(
                    When(icon__isnull=True, then=Value("")),
                    When(icon="", then=Value("")),
                    default=Concat(Value(settings.MEDIA_URL), F("icon")),
                    output_field=models.CharField(),
                ),
                # 直接使用Tenant模型中的计数字段，命名为total表示固定值
                device_total=F("device_count"),
                rack_total=F("rack_count"),
                subnet_total=F("subnet_count"),
                ipaddr_total=F("ipaddr_count"),
                # 聚合计算的值，命名为count_agg
                used_units_count_agg=Coalesce(
                    Subquery(used_units_sq, output_field=FloatField()), 0.0
                ),
                total_u_count_agg=Coalesce(
                    Subquery(total_u_sq, output_field=FloatField()), 0.0
                ),
                free_racks_count_agg=Coalesce(
                    Subquery(free_count_sq, output_field=IntegerField()), 0
                ),
            )
            .annotate(
                avg_utilization=Case(
                    When(
                        total_u_count_agg__gt=0,
                        then=ExpressionWrapper(
                            F("used_units_count_agg") / F("total_u_count_agg"),
                            output_field=FloatField(),
                        ),
                    ),
                    default=Value(0.0),
                    output_field=FloatField(),
                ),
                free_rate=Case(
                    When(
                        rack_total__gt=0,
                        then=ExpressionWrapper(
                            F("free_racks_count_agg") * 100.0 / F("rack_total"),
                            output_field=FloatField(),
                        ),
                    ),
                    default=Value(0.0),
                    output_field=FloatField(),
                ),
            )
            .values(
                "id",
                "name",
                "icon_url",
                "device_total",
                "rack_total",
                "subnet_total",
                "ipaddr_total",
                "avg_utilization",
                "free_rate",
            ).exclude(device_total=0,rack_total=0,subnet_total=0,ipaddr_total=0)
            .order_by("-device_total")
        )

        rows = []
        for t in tenants_qs[:100]:
            rows.append(
                {
                    "tenant": {
                        "id": t["id"],
                        "name": t["name"],
                        "icon_url": t["icon_url"],
                    },
                    "device_count": t["device_total"] or 0,
                    "total_racks": t["rack_total"] or 0,
                    "total_subnet": t["subnet_total"] or 0,
                    "total_ipaddr": t["ipaddr_total"] or 0,
                    "avg_utilization": round((t["avg_utilization"] or 0.0) * 100, 2),
                    "free_rate": round(t["free_rate"] or 0.0, 2),
                }
            )
        return rows

    def get(self, request, *args, **kwargs) -> JsonResponse:
        data_center = request.user.data_center
        aggregation = request.GET.get("aggregation", "week")
        period = self.get_date_range(
            request.GET.get("start", None), request.GET.get("end", None)
        )

        kpis = self.get_kpis(data_center, period)
        top_tenants = self.get_top_tenants(data_center, period)

        return JsonResponse(
            {
                "kpis": kpis,
                "top_tenants": top_tenants,
                "aggregation": aggregation,
                "period": period,
            }
        )
