"""QR code views: public detail, scanner page, and image/download endpoints."""

from __future__ import annotations

import re

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core import signing
from django.http import Http404, HttpResponse
from django.utils.safestring import mark_safe
from django.views import View
from django.views.generic import TemplateView

from dcrm.models import CustomField
from dcrm.utilities.display import get_object_display
from dcrm.utilities.lookup import LookupFields
from dcrm.utilities.qr import (
    generate_qr_image,
    get_public_fields_config,
    get_public_url,
    generate_token,
    resolve_token,
)

__all__ = [
    "QRPublicDetailView",
    "QRScannerPageView",
    "QRImageView",
    "QRImageDownloadView",
]


_ANCHOR_TAG_RE = re.compile(r"<a\b[^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)


def _get_public_custom_fields(obj):
    data_center = getattr(obj, "data_center", None)
    if data_center is None:
        return CustomField.objects.none()
    return CustomField.objects.get_for_model(obj.__class__, data_center)


def _sanitize_public_value(value):
    if value in (None, ""):
        return "-"

    rendered = str(value)
    if not rendered:
        return "-"

    if "<a" in rendered.lower():
        rendered = _ANCHOR_TAG_RE.sub(r"\1", rendered)
        return mark_safe(rendered)

    return value


def _get_public_context(token: str) -> dict:
    """公共辅助：解析 token，构建公开详情上下文。"""
    try:
        obj = resolve_token(token)
    except (signing.BadSignature, Exception):
        raise Http404

    opts = obj._meta
    model_key = f"{opts.app_label}.{opts.model_name}"
    config = get_public_fields_config()
    field_names = config.get(model_key, [])
    custom_fields = _get_public_custom_fields(obj)
    lookup = LookupFields(obj.__class__, field_names, custom_fields=custom_fields)
    _, object_name, _ = get_object_display(obj)

    fields = []
    for field_name in field_names:
        try:
            label = lookup.get_field_label(field_name)
            value = _sanitize_public_value(lookup.get_field_value(obj, field_name))
        except Exception:
            label = field_name
            raw = getattr(obj, field_name, None)
            if raw is None:
                value = "-"
            elif hasattr(raw, "all"):
                value = ", ".join(str(v) for v in raw.all()) or "-"
            else:
                value = str(raw) if raw != "" else "-"
        fields.append({"label": label, "value": value})

    return {
        "object": obj,
        "object_name": object_name,
        "model_verbose_name": opts.verbose_name,
        "fields": fields,
        "token": token,
    }


class QRPublicDetailView(View):
    """公开扫码详情页，无需登录。

    URL: /scan/<token>/
    """

    template_name = "scan/public_detail.html"

    def get(self, request, token: str, *args, **kwargs):
        from django.shortcuts import render

        context = _get_public_context(token)
        return render(request, self.template_name, context)


class QRScannerPageView(TemplateView):
    """摄像头扫码识别页，无需登录。

    URL: /scan/
    扫描到任意含 /scan/{token}/ 路径的 QR 码后，提取 token 并以相对路径跳转，
    旧域名部分被完全丢弃，实现域名变更兼容。
    """

    template_name = "scan/scanner.html"


class QRImageView(LoginRequiredMixin, View):
    """返回 inline PNG 图像，供详情页 Modal 内嵌显示。

    URL: /qr/image/<token>/
    需要登录（防止随意枚举遍历）。
    """

    def get(self, request, token: str, *args, **kwargs):
        try:
            obj = resolve_token(token)
        except (signing.BadSignature, Exception):
            raise Http404

        url = get_public_url(request, obj)
        buf = generate_qr_image(url)
        return HttpResponse(
            buf.read(),
            content_type="image/png",
            headers={"Content-Disposition": "inline"},
        )


class QRImageDownloadView(LoginRequiredMixin, View):
    """返回 attachment PNG，供单个下载保存。

    URL: /qr/download/<token>/
    """

    def get(self, request, token: str, *args, **kwargs):
        try:
            obj = resolve_token(token)
        except (signing.BadSignature, Exception):
            raise Http404

        url = get_public_url(request, obj)
        buf = generate_qr_image(url)

        # 文件名：{model}_{pk}_{name}.png，清理非法字符
        name = re.sub(r"[^\w\-]", "_", str(obj))
        opts = obj._meta
        filename = f"{opts.model_name}_{obj.pk}_{name}.png"

        return HttpResponse(
            buf.read(),
            content_type="image/png",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
