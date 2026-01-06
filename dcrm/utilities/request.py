from ipaddress import (
    AddressValueError,
    IPv4Address,
    IPv6Address,
    NetmaskValueError,
    ip_address,
)
from typing import Literal
from urllib.parse import urlparse

from django.utils.translation import gettext_lazy as _


def get_request_ip(
    request, additional_headers=()
) -> IPv4Address | IPv6Address | Literal[""]:
    """返回请求的真实IP地址
    """
    HTTP_HEADERS = (
        "HTTP_X_REAL_IP",
        "HTTP_X_FORWARDED_FOR",
        "REMOTE_ADDR",
        *additional_headers,
    )
    for header in HTTP_HEADERS:
        if header in request.META:
            ip = request.META[header].split(",")[0].strip()
            try:
                return ip_address(ip)
            except (AddressValueError, NetmaskValueError):
                ip = urlparse(f"//{ip}").hostname

            try:
                return ip_address(ip)
            except (AddressValueError, NetmaskValueError):
                raise ValueError(
                    _("为 {header} 设置的 IP 地址无效：{ip}").format(
                        header=header, ip=ip
                    )
                )
    return ""
