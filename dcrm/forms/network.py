from ipaddress import ip_address, ip_interface

from django import forms
from django.utils.translation import gettext_lazy as _

from dcrm.models import Subnet

from .base import BaseModelFormMixin
from .forms import CustomFieldModelForm


class DNSWidget(forms.Textarea):
    """Render each key-value pair of a dictionary on a new line within a textarea for easy editing.
    """

    def format_value(self, value):
        if not value:
            return None
        if type(value) is list:
            return "\n".join(value)
        return value


class SubnetBaseForm(CustomFieldModelForm, BaseModelFormMixin):

    dns_servers = forms.CharField(
        widget=DNSWidget(),
        required=False,
        label=_("DNS服务器"),
        help_text=_("每行输入一个DNS地址。例如：8.8.8.8"),
    )

    class Meta:
        model = Subnet
        fields = [
            "name",
            "network",
            "gateway",
            "tenant",
            "vlan",
            "vrf",
            "network_product",
            "dns_servers",
            "status",
            "is_scan",
            "description",
            "tags",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "dns_servers" in self.initial and self.initial["dns_servers"]:
            dns_servers = []
            for dns in self.initial["dns_servers"]:
                dns_servers.append(dns)
            self.initial["dns_servers"] = dns_servers

    def clean_dns_servers(self):
        """清理DNS服务器地址，转为json格式
        """
        data = []
        dns_value = self.cleaned_data["dns_servers"].splitlines()
        if not dns_value:
            return
        for line in dns_value:
            dns_ip = line.strip()
            try:
                ip_address(dns_ip)
            except ValueError:
                self.add_error("dns_servers", _(f"无效的DNS服务器地址: {line}"))
            data.append(dns_ip)
        return data

    def clean(self):
        cleaned_data = super().clean()
        ip_interface_fields = ["network", "gateway"]
        for inet_field in ip_interface_fields:
            value = cleaned_data.get(inet_field)
            if value:
                try:
                    ip_interface(value)
                except ValueError:
                    self.add_error(inet_field, _(f"无效的IP地址格式: {value}"))

        return cleaned_data
