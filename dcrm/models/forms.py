from ipaddress import (
    AddressValueError,
    IPv4Interface,
    IPv6Interface,
    NetmaskValueError,
    ip_interface,
)

from django import forms


class InterfaceIPAddressFormField(forms.CharField):
    """表单字段，用于处理带掩码的IP地址输入
    """

    def __init__(self, protocol="both", unpack_ipv4=False, *args, **kwargs):
        self.protocol = protocol
        self.unpack_ipv4 = unpack_ipv4
        super().__init__(*args, **kwargs)

    def clean(self, value):
        value = super().clean(value)
        if not value:
            return value

        try:
            ip = ip_interface(str(value))

            # 验证IP版本
            if self.protocol == "ipv4" and not isinstance(ip, IPv4Interface):
                raise forms.ValidationError("仅支持IPv4地址")
            if self.protocol == "ipv6" and not isinstance(ip, IPv6Interface):
                raise forms.ValidationError("仅支持IPv6地址")

            # 是否需要解压缩IPv4映射的IPv6地址
            if isinstance(ip, IPv6Interface) and self.unpack_ipv4:
                if ip.ipv4_mapped:
                    return ip.ipv4_mapped

            return ip

        except (AddressValueError, NetmaskValueError) as e:
            raise forms.ValidationError(f"无效的IP地址格式: {str(e)}")
