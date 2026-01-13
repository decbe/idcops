import json

from django.http import StreamingHttpResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
    View,
)

from dcrm.forms.network import SubnetBaseForm
from dcrm.models import VLAN, IPAddress, NetworkProduct, Proxy, Subnet

from .mixins.base import BaseRequestMixin
from .mixins.delete import DeleteViewMixin
from .mixins.detail import DetailViewMixin
from .mixins.edit import CreateViewMixin, FieldSet, UpdateViewMixin
from .mixins.list import ListViewMixin


class SubnetListView(BaseRequestMixin, ListViewMixin, ListView):
    model = Subnet
    # template_name = "networks/ipam.html"
    list_fields = [
        "network",
        "name",
        "tenant",
        "start_address",
        "end_address",
        "gateway",
        "vlan",
        "status",
        "is_scan",
        "total_ips",
        "allocated_ips",
        "subnet_count",
    ]


class SubnetCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = Subnet
    form_class = SubnetBaseForm
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
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "name",
                "network",
                "status",
                "tenant",
                "network_product",
                "tags",
                "description",
            ],
            description=_("子网的基本信息"),
        ),
        FieldSet(
            name=_("网络配置"),
            fields=[
                "dns_servers",
                "is_scan",
                "gateway",
                "vlan",
                "vrf",
            ],
            description=_("子网的网络配置信息"),
        ),
    ]


class SubnetUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = Subnet
    form_class = SubnetBaseForm
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
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "name",
                "network",
                "status",
                "tenant",
                "network_product",
                "tags",
                "description",
            ],
            description=_("子网的基本信息"),
        ),
        FieldSet(
            name=_("网络配置"),
            fields=[
                "dns_servers",
                "is_scan",
                "gateway",
                "vlan",
                "vrf",
            ],
            description=_("子网的网络配置信息"),
        ),
    ]


class SubnetDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    model = Subnet


class SubnetDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = Subnet
    enable_tabs = False
    enable_create_update = False
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": [
                "name",
                "network",
                "tenant",
                "network_product",
                "gateway",
                "start_address",
                "end_address",
                "total_ips",
                "allocated_ips",
                "subnet_count",
                "status",
                "tags",
                "description",
            ],
            "description": _("子网的基本信息"),
        },
        {
            "title": _("网络配置"),
            "fields": ["dns_servers", "vlan", "vrf", "is_scan", "parent"],
            "description": _("子网的网络配置信息"),
        },
    ]

    def htmx_get(self, request, *args, **kwargs):
        # 获取所有根节点
        template_name = "subnet/htmx_detail.html"
        from django.shortcuts import render

        self.object = self.get_object()
        context = self.get_context_data(**kwargs)
        return render(request, template_name, context)


class IPAddressListView(BaseRequestMixin, ListViewMixin, ListView):
    model = IPAddress
    list_fields = [
        "address",
        "subnet",
        "tenant",
        "status",
        "ip_type",
        "is_gateway",
        "mac_address",
        "tracking",
        "tags",
    ]


class IPAddressCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = IPAddress
    fields = [
        "tenant",
        "subnet",
        "address",
        "status",
        "is_primary",
        "is_management",
        "is_gateway",
        "mac_address",
        "tracking",
        "description",
        "tags",
    ]
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=["address", "subnet", "tenant", "status", "description", "tags"],
            description=_("IP地址的基本信息"),
        ),
        FieldSet(
            name=_("配置信息"),
            fields=[
                "mac_address",
                "is_primary",
                "is_management",
                "is_gateway",
                "tracking",
            ],
            description=_("IP地址的其他补充信息"),
        ),
    ]


class IPAddressUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = IPAddress
    fields = [
        "tenant",
        "subnet",
        "address",
        "status",
        "is_primary",
        "is_management",
        "is_gateway",
        "mac_address",
        "tracking",
        "description",
        "tags",
    ]
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=["address", "subnet", "tenant", "status", "description", "tags"],
            description=_("IP地址的基本信息"),
        ),
        FieldSet(
            name=_("配置信息"),
            fields=[
                "mac_address",
                "is_primary",
                "is_management",
                "is_gateway",
                "tracking",
            ],
            description=_("IP地址的其他补充信息"),
        ),
    ]


class IPAddressDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    model = IPAddress


class IPAddressDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = IPAddress
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": [
                "address",
                "ip_type",
                "subnet",
                "tenant",
                "status",
                "is_primary",
                "is_management",
                "is_gateway",
                "tracking",
            ],
            "description": _("IP地址的基本信息"),
        },
        {
            "title": _("其他信息"),
            "fields": ["mac_address", "description", "tags"],
            "description": _("IP地址的其他补充信息"),
        },
    ]


class VLANListView(BaseRequestMixin, ListViewMixin, ListView):
    model = VLAN
    list_fields = ["name", "vlan_id", "tenant", "status", "description", "tags"]


class VLANCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = VLAN
    fields = ["name", "vlan_id", "tenant", "status", "description", "tags"]
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=["name", "vlan_id", "tenant", "status", "description", "tags"],
            description=_("VLAN的基本信息"),
        )
    ]


class VLANUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = VLAN
    fields = ["name", "vlan_id", "tenant", "status", "description", "tags"]
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=["name", "vlan_id", "tenant", "status", "description", "tags"],
            description=_("VLAN的基本信息"),
        )
    ]


class VLANDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    model = VLAN


class VLANDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = VLAN
    fields = "__all__"


class NetworkProductListView(BaseRequestMixin, ListViewMixin, ListView):
    """网络产品列表视图"""

    model = NetworkProduct
    list_fields = [
        "name",
        "code",
        "description",
        "color",
        "tags",
        "shared",
        "data_center",
    ]


class NetworkProductCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    """网络产品创建视图"""

    model = NetworkProduct
    fields = ["name", "code", "description", "color", "shared", "tags"]
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=["name", "code", "description", "color", "shared", "tags"],
            description=_("网络产品的基本信息"),
        )
    ]

    def get_success_url(self):
        return reverse("network_product_detail", kwargs={"pk": self.object.pk})


class NetworkProductUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    """网络产品编辑视图"""

    model = NetworkProduct
    fields = ["name", "code", "description", "color", "shared", "tags"]
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=["name", "code", "description", "color", "shared", "tags"],
            description=_("网络产品的基本信息"),
        )
    ]

    def get_success_url(self):
        return reverse("network_product_detail", kwargs={"pk": self.object.pk})


class NetworkProductDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    """网络产品详情视图"""

    model = NetworkProduct
    fields = "__all__"


class NetworkProductDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """网络产品删除视图"""

    model = NetworkProduct
    template_name = "confirm_delete.html"

    def get_success_url(self):
        return reverse("network_product_list")


class ProxyListView(BaseRequestMixin, ListViewMixin, ListView):
    model = Proxy
    list_fields = [
        "name",
        "host",
        "port",
        "username",
        "password",
        "proxy_type",
        "is_active",
        "tags",
    ]


class ProxyCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = Proxy
    fields = [
        "name",
        "host",
        "port",
        "username",
        "password",
        "proxy_type",
        "is_active",
        "tags",
    ]


class ProxyUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = Proxy
    fields = [
        "name",
        "host",
        "port",
        "username",
        "password",
        "proxy_type",
        "is_active",
        "tags",
    ]


class ProxyDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    model = Proxy


class ProxyDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = Proxy
    fields = "__all__"


class ServerSentEventView(BaseRequestMixin, View):
    model = Subnet

    def get(self, request, *args, **kwargs):
        self.pk = kwargs.get("pk")
        response = StreamingHttpResponse(
            streaming_content=self.event_stream(), content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def event_stream(self):
        """Generator function that yields SSE events.
        """
        try:
            object = self.model.objects.get(pk=self.pk)
            if not object.is_scan:
                yield f"data: {json.dumps({'status': 'error', 'message': '子网未开启扫描'})}\n\n"
                return
            data = self.scan_ip(str(object.network))
            yield f"data: {json.dumps(data)}\n\n"
            # 发送完成信号
            yield f"data: {json.dumps({'status': 'complete'})}\n\n"
        except Exception as e:
            # 发送错误信号
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

    def scan_ip(self, ip_address):
        return {"status": "error", "message": "免费版本不支持扫描"}
