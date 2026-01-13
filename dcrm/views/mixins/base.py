from datetime import datetime, timedelta
from typing import Any

from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Model
from django.http import HttpResponse
from django.http.response import (
    HttpResponse,
    HttpResponsePermanentRedirect,
    HttpResponseRedirect,
)
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from mptt.models import MPTTModel

from dcrm.actions import registry
from dcrm.models import DataCenter, User

__all__ = ["BaseRequestMixin", "HtmxResponseMixin", "BasePeriodMixin"]


class BaseRequestMixin(LoginRequiredMixin):
    """基础请求 Mixin
    """

    @cached_property
    def has_model(self) -> bool | None:
        model = getattr(self, "model") if hasattr(self, "model") else None
        if model:
            return issubclass(model, Model)
        return

    @cached_property
    def opts(self) -> Any | None:
        """模型元数据属性"""
        return self.model._meta if self.has_model else None

    @cached_property
    def actions(self) -> list | list[dict]:
        """操作权限属性"""
        if not self.has_model:
            return []
        actions = registry.get_user_model_actions(self.request.user, self.model)
        return actions

    def get_model_meta(self) -> dict | dict[str, Any]:
        """获取模型元数据
        """
        if not self.has_model:
            return {}
        opts = self.model._meta
        default_icon = "fa fa-circle-o"
        model_name = opts.model_name
        create_url = (
            self.model().get_create_url()
            if hasattr(self.model, "get_create_url")
            else None
        )
        list_url = (
            self.model().get_list_url() if hasattr(self.model, "get_list_url") else None
        )
        model_meta = {
            "title": opts.verbose_name,
            "subtitle": opts.verbose_name_plural,
            "icon": getattr(self.model, "_icon", default_icon),
            "model_name": f"{opts.app_label}.{model_name}",
            "model_name_lower": model_name.lower(),
            "create_url": create_url,
            "list_url": list_url,
            "breadcrumbs": [
                {
                    "name": _("仪表盘"),
                    "url": reverse("index"),
                    "icon": "fa fa-dashboard",
                },
                {
                    "name": opts.verbose_name,
                    "url": list_url,
                    "icon": getattr(self.model, "_icon", default_icon),
                },
            ],
        }
        if hasattr(self, "object") and isinstance(self.object, Model):
            if hasattr(self.object, "parent") and isinstance(
                self.object.parent, MPTTModel
            ):
                model_meta["breadcrumbs"].append({"name": self.object.parent})
            model_meta["breadcrumbs"].append({"name": self.object})
        return model_meta

    def handle_authentication(
        self,
    ) -> HttpResponsePermanentRedirect | HttpResponseRedirect:
        """处理未认证请求"""
        app = apps.get_app_config("dcrm")
        if app.has_datacenter is None and app.has_superuser is None:
            app.has_datacenter = DataCenter.objects.filter(is_active=True).exists()
            app.has_superuser = User.objects.filter(is_superuser=True).exists()
        if not app.has_datacenter and not app.has_superuser:
            return redirect("create_first_superuser")
        dev_env = getattr(settings, "DEV_ENV", False)
        if dev_env:
            message = _("测试用户： demo / admin.123 ")
            messages.warning(self.request, message)
        return redirect_to_login(
            self.request.get_full_path(),
            self.get_login_url(),
            self.get_redirect_field_name(),
        )

    def handle_no_datacenter(
        self, request
    ) -> HttpResponsePermanentRedirect | HttpResponseRedirect | None:
        """处理用户没有默认数据中心的情况"""
        if request.user.is_superuser:
            default_dc = DataCenter.objects.filter().first()
            if default_dc:
                request.user.data_center = default_dc
                request.user.save(update_fields=["data_center"])
                messages.info(request, _("已自动为您设置默认数据中心"))
                return None
            messages.error(request, _("系统没有可用的数据中心，请新建一个数据中心"))
            return redirect("welcome")
        messages.error(request, _("您没有关联任何数据中心，请联系管理员"))
        return self.handle_no_permission()

    def get_lookup_model(self) -> Any | None:
        """获取模型类"""
        model_name = self.kwargs.get("model_name")
        if not model_name:
            return None

        try:
            return apps.get_model("dcrm", model_name)
        except LookupError:
            raise ImproperlyConfigured(f"找不到模型 {model_name}")

    def dispatch(
        self, request, *args, **kwargs
    ) -> HttpResponsePermanentRedirect | HttpResponseRedirect | Any:
        """请求分发处理"""
        if not request.user.is_authenticated:
            return self.handle_authentication()

        # 检查数据中心
        if not request.user.data_center:
            response = self.handle_no_datacenter(request)
            if response:
                return response
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs) -> Any:
        """扩展上下文数据"""
        context = super().get_context_data(**kwargs)
        if self.has_model and not self.request.htmx:
            context.update(self.get_model_meta())
        context.update(dict(actions=self.actions))
        return context


class HtmxResponseMixin:
    """HTMX 响应处理 Mixin"""

    htmx_triggers: dict[str, str] = {}
    htmx_push_url: str | None = None
    htmx_redirect: str | None = None
    htmx_refresh: bool = False
    partial_template_name: str | None = None

    def get_htmx_push_url(self) -> str | None:
        """获取要推送的 URL"""
        return self.htmx_push_url or self.request.path

    def get_template_names(self) -> list[str] | Any:
        """获取模板名称"""
        if self.request.htmx and self.partial_template_name:
            return [self.partial_template_name]
        return super().get_template_names()

    def htmx_dispatch(self, request, *args, **kwargs) -> Any | HttpResponse:
        """HTMX 请求处理"""
        handler = getattr(self, f"htmx_{request.method.lower()}", None)
        if handler:
            return handler(request, *args, **kwargs)
        return self.handle_htmx_default(request, *args, **kwargs)

    def handle_htmx_default(self, request, *args, **kwargs) -> HttpResponse:
        """默认 HTMX 处理"""
        response = super().dispatch(request, *args, **kwargs)
        return self.add_htmx_headers(response)

    def add_htmx_headers(self, response: HttpResponse) -> HttpResponse:
        """添加 HTMX 响应头"""
        # 处理 URL 推送
        push_url = self.get_htmx_push_url()
        if push_url:
            response["HX-Push-Url"] = push_url

        # 处理触发器
        if self.htmx_triggers:
            triggers = []
            for event, detail in self.htmx_triggers.items():
                triggers.append(f"{event}:{detail}")
            response["HX-Trigger"] = ",".join(triggers)

        # 处理定向
        if self.htmx_redirect:
            response["HX-Redirect"] = self.htmx_redirect

        # 处页面刷新
        if self.htmx_refresh:
            response["HX-Refresh"] = "true"

        return response

    def dispatch(self, request, *args, **kwargs) -> Any | HttpResponse:
        """请求分发"""
        if request.htmx:
            return self.htmx_dispatch(request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)


class BasePeriodMixin:
    """时间范围处理 Mixin

    提供通用的时间范围处理功能，包括：
    - 时间范围选项配置
    - 日期范围计算
    - 对比时间计算
    """

    _START_DATE = "start_date"
    _END_DATE = "end_date"
    _AGGREGATION = "aggregation"

    def get_date_range(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> tuple[datetime | None, datetime | None]:
        """根据指定的start_date, end_date请求参数构建日期范围

        Args:
            start_date: 开始日期字符串，格式为 'YYYY-MM-DD'，如果为None则使用默认值
            end_date: 结束日期字符串，格式为 'YYYY-MM-DD'，如果为None则使用当前日期

        Returns:
            (起始日期, 结束日期) 元组，日期都可能为None

        """
        # 处理结束日期
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
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
        self, start_date: datetime | None, end_date: datetime | None
    ) -> tuple[datetime | None, datetime | None]:
        """根据给定的日期范围获取上一个周期的时间范围

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
