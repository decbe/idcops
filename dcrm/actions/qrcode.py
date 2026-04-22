"""批量二维码导出 Actions（注册到 Rack 和 Device）。

提供两种导出方式：
1. export_qrcodes_zip   — 多张 PNG 打包 ZIP 下载
2. export_qrcodes_print — 打印友好 HTML 页面（A4，每行 3 个，可直接 Ctrl+P）
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from dcrm.models import Device, Rack
from dcrm.models.choices import ActionColorChoices

from .actions import registry

__all__ = ["export_qrcodes_zip", "export_qrcodes_print"]


def _safe_name(s: str) -> str:
    """替换文件名中的非法字符。"""
    return re.sub(r"[^\w\-]", "_", str(s))


@registry.register(
    name=_("批量导出二维码 (ZIP)"),
    models=(Rack, Device),
    permissions=("view",),
    description=_("将选中记录的二维码图片打包为 ZIP 文件下载，可用于打印张贴"),
    color=ActionColorChoices.INFO,
    icon="fa fa-qrcode",
    order=200,
    is_htmx=False,
)
def export_qrcodes_zip(request, instances, **kwargs) -> HttpResponse:
    """将选中对象的 QR 码 PNG 打包为 ZIP 返回。"""
    from dcrm.utilities.qr import generate_qr_image, get_public_url

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for obj in instances:
            url = get_public_url(request, obj)
            png_buf = generate_qr_image(url)
            opts = obj._meta
            filename = f"{opts.model_name}_{obj.pk}_{_safe_name(str(obj))}.png"
            zf.writestr(filename, png_buf.read())

    buf.seek(0)
    model_name = instances.model._meta.model_name
    zip_filename = f"{model_name}_qrcodes.zip"
    return HttpResponse(
        buf.read(),
        content_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
    )


@registry.register(
    name=_("批量打印二维码"),
    models=(Rack, Device),
    permissions=("view",),
    description=_("生成可打印的 HTML 页面，每行 3 个二维码，适合 A4 纸打印张贴"),
    color=ActionColorChoices.DEFAULT,
    icon="fa fa-print",
    order=201,
    is_htmx=False,
)
def export_qrcodes_print(request, instances, **kwargs) -> HttpResponse:
    """生成可打印 HTML，内嵌 base64 PNG，无需服务器回源。"""
    import base64

    from dcrm.utilities.qr import generate_qr_image, get_public_url

    items = []
    for obj in instances:
        url = get_public_url(request, obj)
        png_buf = generate_qr_image(url)
        b64 = base64.b64encode(png_buf.read()).decode("ascii")
        items.append(
            {
                "name": str(obj),
                "model_verbose_name": obj._meta.verbose_name,
                "image_data": f"data:image/png;base64,{b64}",
                "url": url,
            }
        )

    html = render_to_string(
        "scan/print_qrcodes.html",
        {"items": items},
        request=request,
    )
    return HttpResponse(html, content_type="text/html; charset=utf-8")
