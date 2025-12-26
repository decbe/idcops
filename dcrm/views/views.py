import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from django_rq import utils as rq_utils

from django.apps import apps
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db import connection, models
from django.db.models import Case, Count, F, Value, When
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, TemplateView, View

from dcrm.forms.datacenter import DataCenterForm
from dcrm.forms.users import CreateFirstSuperUserForm
from dcrm.models import (
    Attachment,
    DataCenter,
    Device,
    LogEntry,
    OnlineDevice,
    Rack,
    Subnet,
    Tenant,
)
from dcrm.models.choices import ChangeActionChoices
from dcrm.models.utils import get_file_mime
from dcrm.utilities.upload import (
    extract_barcodes,
    extract_ocr_texts,
    update_attachment_metadata,
)

from .mixins.base import BaseRequestMixin

logger = logging.getLogger(__name__)


class IndexView(BaseRequestMixin, TemplateView):
    """首页视图"""

    template_name = "index.html"

    def get_device_statistics(self) -> str:
        """
        获取设备统计信息，包括设备变更趋势和设备类型分布
        """
        data_center = self.request.user.data_center

        # 获取时间范围参数，默认为最近半年
        period = self.request.GET.get("period", "year")
        aggregation = self.request.GET.get("aggregation", "week")  # 默认按周聚合

        # 计算时间范围
        now = timezone.now()
        if period == "week":
            start_date = now - timedelta(weeks=1)
        elif period == "month":
            start_date = now - timedelta(days=30)
        elif period == "quarter":
            start_date = now - timedelta(days=90)
        elif period == "half_year":
            start_date = now - timedelta(days=183)
        elif period == "year":
            start_date = now - timedelta(days=365)
        elif period == "all":
            start_date = None
        else:  # 默认半年
            start_date = now - timedelta(days=183)

        # 构建查询条件
        log_query = {
            "data_center": data_center,
            "content_type": ContentType.objects.get_for_model(Device),
        }
        if start_date:
            log_query["created_at__gte"] = start_date

        # 获取设备变更日志
        logs = LogEntry.objects.filter(**log_query)

        # 1. 设备变更趋势分析（柱状图）
        # 获取指定操作类型的数据
        action_types = ["create", "device_migrate", "device_move_down"]
        trend_data = logs.filter(action_type__in=action_types)

        # 根据聚合类型进行分组统计，按自然年划分
        if aggregation == "week":
            # 按自然周聚合
            date_trunc = "week"
        elif aggregation == "month":
            # 按自然月聚合
            date_trunc = "month"
        elif aggregation == "quarter":
            # 按自然季度聚合
            date_trunc = "quarter"
        elif aggregation == "year":
            # 按自然年聚合
            date_trunc = "year"
        else:  # 默认按天
            date_trunc = "day"

        # 对于week和quarter聚合，确保按自然年划分
        if aggregation in ["week", "quarter"]:
            # 添加年份过滤条件，确保只查询当前自然年内的数据
            if start_date and period != "all":
                # 确保起始日期不早于当前年的1月1日
                current_year_start = now.replace(
                    month=1, day=1, hour=0, minute=0, second=0, microsecond=0
                )
                if start_date < current_year_start and period in [
                    "week",
                    "month",
                    "quarter",
                    "half_year",
                ]:
                    start_date = current_year_start
                if start_date:
                    log_query["created_at__gte"] = start_date

        # 使用单个查询获取趋势数据，直接在数据库层面处理
        trend_stats = (
            trend_data.extra(select={"date": f"date_trunc('{date_trunc}', created_at)"})
            .values("date", "action_type")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        # 重新组织趋势数据 - 优化版本
        trend_chart_data = {
            "dates": [],
            "create": [],
            "device_migrate": [],
            "device_move_down": [],
        }

        # 获取所有唯一的日期并排序
        dates = sorted(set(item["date"].date() for item in trend_stats))
        if dates:
            # 格式化日期显示
            if aggregation == "day":
                trend_chart_data["dates"] = [
                    date.strftime("%Y-%m-%d") for date in dates
                ]
            elif aggregation == "week":
                trend_chart_data["dates"] = [date.strftime("%Y-W%U") for date in dates]
            elif aggregation == "month":
                trend_chart_data["dates"] = [date.strftime("%Y-%m") for date in dates]
            elif aggregation == "quarter":
                trend_chart_data["dates"] = [
                    f"{date.year}-Q{(date.month-1)//3+1}" for date in dates
                ]
            elif aggregation == "year":
                trend_chart_data["dates"] = [date.strftime("%Y") for date in dates]
            else:
                trend_chart_data["dates"] = [
                    date.strftime("%Y-%m-%d") for date in dates
                ]

            # 初始化数据数组
            for action in action_types:
                trend_chart_data[action] = [0] * len(dates)

            # 使用字典映射优化数据填充
            date_to_index = {date: idx for idx, date in enumerate(dates)}

            # 填充数据 - 优化版本
            for item in trend_stats:
                item_date = item["date"].date()
                if item_date in date_to_index:
                    date_index = date_to_index[item_date]
                    trend_chart_data[item["action_type"]][date_index] = item["count"]

        # 优化查询：一次性获取所有需要的数据
        type_stats_queryset = (
            OnlineDevice.objects.filter(data_center=data_center)
            .values("type__name")
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

        type_stats = list(type_stats_queryset)
        _aggregations = [
            {"value": "day", "label": "按天"},
            {"value": "week", "label": "按周"},
            {"value": "month", "label": "按月"},
            {"value": "quarter", "label": "按季度"},
            {"value": "year", "label": "按年"},
        ]
        _period = [
            {"value": "week", "label": "最近一周"},
            {"value": "month", "label": "最近一月"},
            {"value": "quarter", "label": "最近三月"},
            {"value": "half_year", "label": "最近半年"},
            {"value": "year", "label": "最近一年"},
            {"value": "all", "label": "所有"},
        ]
        data = {
            "trend_data": trend_chart_data,
            "type_data": type_stats,
            "periods": _period,
            "period": period,
            "aggregation": aggregation,
        }
        return data

    def get_models_stats(self) -> List[Dict[str, Any]]:
        data_center = self.request.user.data_center
        racks = Rack.objects.filter(data_center=data_center).values("status")
        actived_racks = racks.filter(status__allowed_mount=True)
        data = [
            {
                "active_count": actived_racks.count(),
                "count": data_center.rack_count,
                "icon": "fa fa-building",
                "color": "bg-aqua",
                "model": "rack",
                "name": _("机柜信息"),
                "metric": _("个"),
                "desc": _("在用/总机柜数"),
                "url": f"{Rack().get_list_url()}",
            },
            {
                "active_count": OnlineDevice.objects.filter(
                    data_center=data_center
                ).count(),
                "count": data_center.device_count,
                "icon": "fa fa-server",
                "color": "bg-green",
                "name": _("设备信息"),
                "metric": _("台"),
                "desc": _("在线/所有设备数"),
                "url": f"{Device().get_list_url()}",
            },
            {
                "count": data_center.subnet_count,
                "icon": "fa fa-sitemap",
                "color": "bg-light-blue",
                "name": _("子网信息"),
                "metric": _("个"),
                "url": f"{Subnet().get_list_url()}",
            },
            {
                "count": data_center.tenant_count,
                "icon": "fa fa-users",
                "color": "bg-yellow",
                "name": _("租户信息"),
                "metric": _("个"),
                "desc": _(""),
                "url": f"{Tenant().get_list_url()}",
            },
        ]
        return data

    def get_recent_operations(self):
        """
        获取最近的操作日志
        """
        data_center = self.request.user.data_center
        # 获取最近10条操作日志，按创建时间倒序排列
        actions = ["create", "bulk_create", "update", "bulk_update", "delete"]
        recent_logs = (
            LogEntry.objects.filter(data_center=data_center, action__in=actions)
            .select_related("content_type", "created_by")
            .order_by("-created_at")[:10]
        )
        default_icon = "fa fa-circle-o"
        operations = []
        for log in recent_logs:
            # 获取操作类型的颜色
            related_model = log.content_type.model_class()
            action_color = ChangeActionChoices.get_color(log.action)
            model_icon = getattr(related_model, "_icon", default_icon)
            color_class = f"bg-{action_color}" if action_color else "bg-gray"

            operations.append(
                {
                    "id": log.id,
                    "timestamp": log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "user": log.created_by.username if log.created_by else _("系统"),
                    "action": log.get_action_display(),
                    "action_type": log.action,
                    "message": log.message or _("无描述"),
                    "object_repr": (log.object_repr if log.object_repr else None),
                    "content_type": (
                        log.content_type.model_class()._meta.verbose_name
                        if log.content_type
                        else _("未知类型")
                    ),
                    "icon": model_icon,
                    "color_class": color_class,
                }
            )

        return operations

    def get_system_info(self):
        """
        获取系统信息
        指标：
        app 运行时间
        python 版本
        django 版本
        postgresql 版本
        postgresql 数据库大小
        rqworker 数量
        系统时间
        系统hostname
        os
        system load
        """

        data = {}

        # 系统时间
        data["system_time"] = timezone.now().strftime("%Y-%m-%d %H:%M:%S")

        # Python版本
        data["python_version"] = sys.version.split()[0]

        # 系统负载 (仅在Unix系统上可用)
        try:
            load_avg = os.getloadavg()
            data["load_average"] = {
                "1_minute": round(load_avg[0], 2),
                "5_minute": round(load_avg[1], 2),
                "15_minute": round(load_avg[2], 2),
            }
        except (AttributeError, OSError):
            data["load_average"] = "N/A"

        # PostgreSQL版本和数据库大小
        try:
            with connection.cursor() as cursor:
                # 一次性查询PostgreSQL版本和数据库大小
                cursor.execute(
                    """
                    SELECT 
                        split_part(version(), ' ', 2) as postgresql_version,
                        pg_size_pretty(pg_database_size(current_database())) as database_size;
                """
                )
                result = cursor.fetchone()
                if result:
                    data["postgresql_version"] = result[0] if result[0] else "Unknown"
                    data["database_size"] = result[1] if result[1] else "Unknown"
                else:
                    data["postgresql_version"] = "Unknown"
                    data["database_size"] = "Unknown"
        except Exception as e:
            data["postgresql_version"] = "Unknown"
            data["database_size"] = "Unknown"

        # RQ Worker数量
        try:
            rq_queues = rq_utils.get_statistics()["queues"]
            data["rqworker_count"] = sum([queue["workers"] for queue in rq_queues])
        except Exception:
            data["rqworker_count"] = "Unknown"
        try:
            # 获取应用配置的启动时间
            app = apps.get_app_config("dcrm")
            data["app_uptime"] = app.start_time
        except Exception:
            data["app_uptime"] = "Unknown"

        return data

    def get_context_data(self, **kwargs) -> Any:
        """
        获取模板上下文数据

        Args:
            **kwargs: 额外的上下文参数

        Returns:
            包含页面标题、面包屑导航和统计数据的上下文字典
        """
        context = super().get_context_data(**kwargs)
        device_stats = self.get_device_statistics()
        # 添加页面特定的上下文
        context.update(
            {
                "title": _("仪表盘"),
                "subtitle": _(f"{self.request.user.data_center}概览"),
                "period": device_stats.get("period"),
                "aggregation": device_stats.get("aggregation"),
                "breadcrumbs": [
                    {
                        "name": _(f"{self.request.user.data_center}"),
                        "icon": "fa fa-home",
                        "url": "#",
                    },
                    {"name": _("仪表盘"), "icon": "fa fa-dashboard", "url": "#"},
                ],
            }
        )

        # 添加统计数据
        context.update({"model_stats": self.get_models_stats()})

        # 添加设备统计信息
        context.update({"device_stats": json.dumps(device_stats)})
        context.update({"recent_operations": self.get_recent_operations()})
        context.update({"system_info": self.get_system_info()})

        return context


class CreateFirstSuperUserView(FormView):
    """创建第一个超级用户视图"""

    form_class = CreateFirstSuperUserForm
    template_name = "auth/create_super_user.html"
    success_url = reverse_lazy("welcome")

    def dispatch(self, request, *args, **kwargs):
        """
        请求分发处理

        检查是否已存在超级用户和数据中心，根据情况重定向到相应页面
        """
        app = apps.get_app_config("dcrm")
        if app.has_superuser and not app.has_datacenter:
            return redirect(self.success_url)
        if (
            app.has_superuser
            and app.has_datacenter
            and self.request.user.is_authenticated
        ):
            return redirect("index")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """
        表单验证成功后的处理

        Args:
            form: 验证通过的表单对象

        Returns:
            重定向响应
        """
        user = form.save(commit=False)
        user.is_superuser = True
        user.is_staff = True
        user.save()
        # 自动登录用户
        login(self.request, user)
        messages.success(self.request, _("超级管理员账户创建成功！"))
        app = apps.get_app_config("dcrm")
        app.has_superuser = True
        return super().form_valid(form)


class WelcomeView(LoginRequiredMixin, FormView):
    """欢迎页面视图"""

    model = DataCenter
    template_name = "auth/welcome.html"
    success_url = reverse_lazy("index")
    form_class = DataCenterForm

    def dispatch(self, request, *args, **kwargs):
        """
        请求分发处理

        检查是否已存在数据中心，如果存在则重定向到首页
        """
        if self.model.objects.all().exists():
            messages.warning(request, _("已有数据中心"))
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        """
        获取表单参数

        Returns:
            包含请求对象的表单参数字典
        """
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form: Any) -> HttpResponse:
        """
        表单验证成功后的处理

        Args:
            form: 验证通过的表单对象

        Returns:
            重定向响应
        """
        user = self.request.user
        form.instance.created_by = user
        datacenter = form.save()
        # 保存用户关联
        user.data_center = datacenter
        user.data_centers.add(datacenter)
        user.save(update_fields=["data_center"])
        messages.success(self.request, _("恭喜你，成功新建了第一个数据中心。"))
        # 更新应用配置
        app = apps.get_app_config("dcrm")
        app.has_datacenter = True
        app.has_superuser = True
        return super().form_valid(form)


class DataCenterCreateView(LoginRequiredMixin, FormView):
    """数据中心创建视图"""

    model = DataCenter
    form_class = DataCenterForm
    template_name = "datacenter/form.html"
    success_url = reverse_lazy("index")

    def dispatch(self, request, *args, **kwargs):
        """
        请求分发处理

        检查用户是否为超级管理员，如果不是则重定向到首页
        """
        if not self.request.user.is_superuser:
            messages.warning(request, _("您不是超级管理员用户"))
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        """
        获取表单参数

        Returns:
            包含请求对象的表单参数字典
        """
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def form_valid(self, form: Any) -> HttpResponse:
        """
        表单验证成功后的处理

        Args:
            form: 验证通过的表单对象

        Returns:
            重定向响应
        """
        user = self.request.user
        form.instance.created_by = user
        datacenter = form.save()
        # 切换到新数据中心
        user.data_center = datacenter
        user.data_centers.add(datacenter)
        user.save(update_fields=["data_center"])
        messages.success(self.request, _("恭喜你，成功新建了第一个数据中心。"))
        return super().form_valid(form)


class UploadAttachment(BaseRequestMixin, View):
    """
    附件上传视图

    主要功能：
    1. 仅允许 POST 请求上传文件，GET 请求会被拒绝。
    2. 支持批量上传多个文件，自动计算文件 MD5，避免重复保存。
    3. 对已存在的附件，如果文件丢失则自动补充上传；如需 OCR 则自动识别并更新 metadata。
    4. 对新上传的文件，自动保存相关信息（如 data_center、创建人、MD5、MIME 类型等）。
    5. 支持文件大小限制，超限文件会被拒绝保存。
    6. 可选 OCR 识别，识别结果自动写入附件 metadata 字段。
    7. 支持条码识别（通过 get_barcodes 方法，可扩展调用）。
    8. 所有处理过程均有详细日志，便于追踪和排查问题。
    9. 返回所有处理后的文件信息，包括名称、大小、URL、元数据、MD5、是否存在等。

    关键方法说明：
    - get_barcodes: 识别图片中的条形码并更新 metadata。
    - get_ocr_result: OCR 识别图片文本并更新 metadata。
    - post: 主处理入口，负责文件接收、去重、保存、识别、返回结果。

    依赖：
    - dcrm.utilities.upload 中的 extract_barcodes, extract_ocr_texts, update_attachment_metadata 方法。
    - dcrm.models.Attachment 模型。
    - 日志 logger。

    适用场景：
    - 前端批量文件上传。
    - 需要自动识别图片内容（OCR/条码）。
    - 附件去重与元数据自动维护。
    """

    def get(self, request: HttpRequest, *args, **kwargs):
        logger.info("收到GET请求，拒绝，仅允许POST")
        return JsonResponse(
            {"status": "false", "message": _("只允许POST方法请求")}, status=400
        )

    def get_barcodes(self, attachment, file_path):
        """
        获取图片中的条形码，将识别的条码结果添加到附件对象的 metadata 字段中
        Args:
            attachment: 附件对象
            file_path: 文件路径

        Returns:
            处理后的附件对象
        """
        barcodes = extract_barcodes(file_path)
        update_attachment_metadata(attachment, barcodes=barcodes)
        return attachment

    def get_ocr_result(self, attachment):
        """
        OCR识别，将识别结果添加到附件对象的 metadata 字段中
        Args:
            attachment: 附件对象
            file_path: 文件路径

        Returns:
            处理后的附件对象
        """
        ocr_texts = extract_ocr_texts(attachment.id, force_ocr=True)
        update_attachment_metadata(attachment, ocr_texts=ocr_texts)
        # 重新获取metadata
        attachment.refresh_from_db(fields=["metadata"])
        logger.debug(f"OCR文本识别结果: {attachment.metadata.get('ocr_texts')}")
        return attachment

    def post(self, request: HttpRequest, *args, **kwargs):
        logger.info(f"收到POST请求，用户: {request.user}")
        if not request.FILES.getlist("files"):
            logger.warning("未收到任何文件")
            return JsonResponse(
                {"status": "false", "message": _("No files were requested")}, status=400
            )

        kwargs = request.POST.copy()
        kwargs.pop("csrfmiddlewaretoken", None)
        require_ocr = kwargs.pop("require_ocr", False)
        require_barcode = kwargs.pop("require_barcode", False)

        try:
            attachments = []
            for file in request.FILES.getlist("files"):
                logger.info(f"处理文件: {file.name}, size={file.size}")
                m = hashlib.md5()
                for chunk in file.chunks():
                    m.update(chunk)
                md5sum = m.hexdigest()
                logger.debug(f"文件MD5: {md5sum}")

                attachment = Attachment.objects.filter(md5sum=md5sum).first()
                if attachment:
                    file_exists = attachment.file_exists()
                    logger.info(f"附件已存在: {attachment.id}, 文件存在: {file_exists}")
                    if not file_exists:
                        logger.info(f"使用新上传的文件更新附件记录, md5sum={md5sum}")
                        attachment.file = file
                        attachment.name = file.name
                        attachment.md5sum = md5sum
                        attachment.mime_type = get_file_mime(
                            next(file.chunks(chunk_size=512)), buffer=True
                        )
                        attachment.save()
                        logger.info(f"附件更新成功, 新路径={attachment.file.path}")
                    if require_ocr and not attachment.metadata.get("ocr_texts", None):
                        logger.info(f"附件需OCR识别: {attachment.id}")
                        attachment = self.get_ocr_result(attachment)
                    attachments.append(attachment)
                else:
                    attachment = Attachment()
                    attachment.data_center = request.user.data_center
                    attachment.created_by = request.user
                    attachment.file = file
                    attachment.name = file.name
                    attachment.md5sum = md5sum
                    attachment.mime_type = get_file_mime(
                        next(file.chunks(chunk_size=512)), buffer=True
                    )
                    if file.size > 1024 * 1024 * 10:
                        logger.warning(f"文件过大: {file.name}, size={file.size}")
                        return JsonResponse(
                            {
                                "status": "false",
                                "message": _(
                                    "File size exceeds the limit allowed and cannot be saved"
                                ),
                            },
                            status=400,
                        )
                    attachment.save(**kwargs)
                    logger.info(f"新附件已保存: {attachment.id}")
                    if require_ocr:
                        logger.info(f"新附件需OCR识别: {attachment.id}")
                        attachment = self.get_ocr_result(attachment)
                    attachments.append(attachment)

            response_files = []
            for attachment in attachments:
                file_info = attachment.get_file_info()
                logger.info(
                    f"返回文件信息: {file_info['name']}, exists={file_info['exists']}"
                )
                response_files.append(
                    {
                        "name": file_info["name"],
                        "size": file_info["size"],
                        "url": file_info["url"],
                        "metadata": attachment.metadata,
                        "md5sum": file_info["md5sum"],
                        "exists": file_info["exists"],
                    }
                )

            logger.info(f"上传处理完成，返回{len(response_files)}个文件")
            return JsonResponse({"status": "true", "files": response_files})
        except IOError as e:
            logger.error(f"保存附件时出错: {str(e)}")
            return JsonResponse(
                {"status": "false", "message": _("Failed to save attachment")},
                status=500,
            )
