from functools import wraps
from typing import Any

from django.apps import apps
from django.contrib import messages
from django.http.response import HttpResponse, StreamingHttpResponse
from django.utils.translation import gettext_lazy as _

from dcrm.models.choices import ActionColorChoices
from dcrm.utilities.exports import export_data_with_stream

from .actions import registry

__all__ = ["export_data"]


# 导出数据
@registry.register(
    name=_("导出"),
    models=[model for model in apps.get_app_config("dcrm").get_models()],
    permissions=("view",),
    description=_("导出csv数据"),
    color=ActionColorChoices.DEFAULT,
    icon="fa fa-download",
    order=20,
    is_htmx=False,
    onclick="handleExportCsv()",
)
def export_data(request, queryset, **kwargs) -> HttpResponse | StreamingHttpResponse:
    """导出数据
    """
    data_center = request.user.data_center
    # 获取请求头中的Accept-Charset
    charset = (
        "utf-8-sig" if "Windows NT" in request.headers.get("User-Agent") else "utf-8"
    )
    return export_data_with_stream(queryset, data_center, charset=charset)


def retrict_multiple_tenant(func):
    """限制操作多租户的装饰器"""

    @wraps(func)
    def wrapper(request, instances, **kwargs) -> Any:
        model = instances.model
        if hasattr(model, "tenant"):
            verify = instances.values("tenant").distinct().count() > 1
            if verify:
                message = _("不能同时操作多个租户 %(verbose_name)s").format(
                    verbose_name=model._meta.verbose_name
                )
                messages.error(request, message)
                return message
        return func(request, instances, **kwargs)

    return wrapper
