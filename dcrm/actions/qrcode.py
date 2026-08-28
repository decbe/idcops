"""批量二维码导出 Actions（注册到 Rack 和 Device）。

提供方式：
1. export_qrcodes_zip — 多张 PNG 打包 ZIP 下载
"""

from __future__ import annotations

import io
import re
import zipfile

from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _

from dcrm.models import Device, Rack, OnlineDevice
from dcrm.models.choices import ActionColorChoices

from .actions import registry

__all__ = ["export_qrcodes_zip"]


def _safe_name(s: str) -> str:
    """替换文件名中的非法字符。"""
    return re.sub(r"[^\w\-]", "_", str(s))


@registry.register(
    name=_("导出二维码(ZIP)"),
    models=(Rack, Device, OnlineDevice),
    permissions=("view",),
    description=_("将选中记录的二维码图片打包为 ZIP 文件下载，可用于打印张贴"),
    color=ActionColorChoices.DEFAULT,
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
