"""QR Code utilities for public rack/device access.

Provides:
- Signed token generation (no DB field required)
- Token resolution back to model instances
- QR image generation (PNG bytes)
- Public URL construction
"""

from __future__ import annotations

import io
from typing import Any

from django.conf import settings
from django.core import signing
from django.contrib.contenttypes.models import ContentType
from django.http import HttpRequest

__all__ = [
    "QR_SIGNER_SALT",
    "generate_token",
    "resolve_token",
    "generate_qr_image",
    "get_public_url",
    "get_public_fields_config",
]

QR_SIGNER_SALT = "dcrm-qr-public"

_signer = signing.Signer(salt=QR_SIGNER_SALT)


def generate_token(obj: Any) -> str:
    """生成对象的防伪 QR token（无需数据库字段）。

    Token 由 SECRET_KEY 派生的 HMAC-SHA256 签名，不可伪造。
    格式：``{app_label}.{model_name}:{pk}``，再由 Signer 签名。
    """
    opts = obj._meta
    value = f"{opts.app_label}.{opts.model_name}:{obj.pk}"
    return _signer.sign(value)


def resolve_token(token: str) -> Any:
    """将 token 还原为模型实例。

    Raises:
        signing.BadSignature: token 签名无效
        ContentType.DoesNotExist: 模型类型不存在
        ObjectDoesNotExist: 对象不存在
    """
    value = _signer.unsign(token)  # raises BadSignature if tampered
    label, pk_str = value.rsplit(":", 1)  # "dcrm.rack" : "42"
    app_label, model_name = label.split(".", 1)
    ct = ContentType.objects.get(app_label=app_label, model=model_name)
    return ct.get_object_for_this_type(pk=int(pk_str))


def generate_qr_image(content: str) -> io.BytesIO:
    """生成包含 content 的 QR PNG 图像，返回 BytesIO。

    使用纠错级别 L（低冗余，适合短 URL），box_size=8，border=4。
    """
    try:
        import qrcode
        from qrcode.image.pil import PilImage
    except ImportError as exc:
        raise ImportError(
            "qrcode[pil] is required. Run: pip install 'qrcode[pil]'"
        ) from exc

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=8,
        border=4,
    )
    qr.add_data(content)
    qr.make(fit=True)
    img = qr.make_image(image_factory=PilImage, fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def get_public_url(request: HttpRequest, obj: Any) -> str:
    """拼接该对象的完整公开扫码 URL（含域名）。

    格式：``https://{host}/scan/{token}/``
    二维码内嵌此 URL，用于直接访问公开详情页。
    """
    token = generate_token(obj)
    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    # 兼容 SITE_PREFIX 配置
    prefix = getattr(settings, "SITE_PREFIX", "/")
    if prefix and prefix != "/":
        prefix = prefix.rstrip("/")
    else:
        prefix = ""
    return f"{scheme}://{host}{prefix}/scan/{token}/"


# 默认公开字段配置（可被 settings.QR_PUBLIC_FIELDS 覆盖）
_DEFAULT_PUBLIC_FIELDS: dict[str, list[str]] = {
    "dcrm.rack": [
        "room",
        "name",
        "rack_type",
        "status",
        "space_usage",
        "tenant",
        "opening_date",
        "contract_power",
        "u_height",
        "pdu_count",
        "pdu_16a_count",
        "description",
    ],
    "dcrm.device": ["name", "model", "type", "rack", "position", "status"],
    "dcrm.onlinedevice": [
        "name",
        "model",
        "type",
        "rack",
        "position",
        "status",
    ],
}


def get_public_fields_config() -> dict[str, list[str]]:
    """返回公开展示字段配置，优先读取 settings.QR_PUBLIC_FIELDS。"""
    return getattr(settings, "QR_PUBLIC_FIELDS", _DEFAULT_PUBLIC_FIELDS)
