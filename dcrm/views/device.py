from typing import Any, Literal

from django.contrib.auth import get_permission_codename
from django.db.models import Model
from django.forms import ModelForm
from django.http import HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from dcrm.forms.deivce import (
    DeviceBaseForm,
    DeviceCreateForm,
    DeviceModelForm,
    DeviceUpdateForm,
)
from dcrm.models import (
    Device,
    DeviceHost,
    DeviceModel,
    DevicePort,
    DeviceType,
    LogEntry,
    OnlineDevice,
    Rack,
)
from dcrm.models.choices import (
    ChangeActionChoices,
    DevicePortStatusChoices,
    DeviceStatusChoices,
)
from dcrm.utilities.serialization import serialize_object
from dcrm.views.imports.views import BulkImportView

from .mixins.base import BaseRequestMixin
from .mixins.delete import DeleteViewMixin
from .mixins.detail import DetailViewMixin
from .mixins.edit import BulkCreateViewMixin, CreateViewMixin, FieldSet, UpdateViewMixin
from .mixins.list import ListViewMixin


class DeviceListView(BaseRequestMixin, ListViewMixin, ListView):
    model = Device
    list_fields = [
        "name",
        "serial_number",
        "rack",
        "position",
        "height",
        "model",
        "type",
        "tenant",
        "status",
        "rack_pdus",
        "ips",
        "tags",
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["create_url"] = reverse("online_device_create")
        return context


class DeviceCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = Device
    form_class = DeviceCreateForm
    success_url = reverse_lazy("device_list")
    clone_fields = [
        "rack",
        "name",
        "tenant",
        "model",
        "type",
        "height",
        "serial_number",
        "warranty_expiry",
    ]
    fields = [
        "rack",
        "created_at",
        "position",
        "serial_number",
        "name",
        "tenant",
        "model",
        "type",
        "height",
        "rack_pdus",
        "ips",
        "warranty_expiry",
        "tags",
    ]

    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "rack",
                "name",
                "serial_number",
                "model",
                "position",
                "rack_pdus",
                "created_at",
            ],
            description=_("设备序列号、位置、租户、型号等信息"),
        ),
        FieldSet(
            name=_("配置信息"),
            fields=["tenant", "type", "height", "ips", "warranty_expiry", "tags"],
            description=_("设备IP地址、保修期、标签等"),
            collapse=False,
        ),
    ]

    def get_template_names(
        self,
    ) -> Literal["device/form_htmx.html", "device/form.html"]:
        """获取模板名称"""
        if self.request.htmx:
            return "device/form_htmx.html"
        return "device/form.html"

    def form_valid(self, form: DeviceBaseForm) -> Any:
        """表单验证成功处理"""
        # Save without committing to handle M2M fields
        self.object = form.save(commit=False)

        # Set data_center if not set
        if not form.cleaned_data.get("data_center") and hasattr(
            self.model, "data_center"
        ):
            self.object.data_center = self.request.user.data_center

        # Save the main object
        self.object.save()

        # Sync device ports
        self.object._sync_ports()

        # Now save M2M fields
        form.save_m2m()

        # messages.success(self.request, self.success_message)
        return super().form_valid(form)

    def get_context_data(self, **kwargs) -> Any:
        context = super().get_context_data(**kwargs)
        if rack := self.request.GET.get("rack", None):
            context["rack"] = Rack.objects.get(pk=rack)
        return context


class DeviceDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = Device
    fields = "__all__"
    enable_comments = True  # 启用评论功能
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": [
                "name",
                "serial_number",
                "rack",
                "position",
                "rack_pdus",
                "model",
                "type",
                "height",
                "tenant",
                "status",
                "tags",
            ],
            "description": _("设备的基本信息，包括名称、序列号、型号等"),
        },
        {
            "title": _("配置信息"),
            "fields": ["ips", "warranty_expiry"],
            "description": _("设备的配置和状态信息"),
        },
    ]

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        status = self.object.status
        if status in [DeviceStatusChoices.MOUNTED, DeviceStatusChoices.MIGRATED]:
            return HttpResponseRedirect(
                reverse("online_device_detail", args=[self.object.pk])
            )
        return super().get(request, *args, **kwargs)


class DeviceUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = Device
    # template_name = 'device/form.html'
    form_class = DeviceUpdateForm
    fields = [
        "rack",
        "created_at",
        "position",
        "serial_number",
        "name",
        "tenant",
        "model",
        "type",
        "height",
        "rack_pdus",
        "ips",
        "warranty_expiry",
        "tags",
    ]

    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "rack",
                "name",
                "serial_number",
                "model",
                "rack_pdus",
                "position",
                "created_at",
            ],
            description=_("设备序列号、位置、租户、型号等信息"),
        ),
        FieldSet(
            name=_("状态信息"),
            fields=["tenant", "type", "height", "ips", "warranty_expiry", "tags"],
            description=_("设备IP地址、保修期、标签等"),
            collapse=False,
        ),
    ]

    def get_template_names(
        self,
    ) -> Literal["device/form_htmx.html", "device/form.html"]:
        """获取模板名称"""
        if self.request.htmx:
            return "device/form_htmx.html"
        return "device/form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["rack"] = self.object.rack
        if rack := self.request.GET.get("rack", None):
            context["rack"] = Rack.objects.get(pk=rack)
        return context

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        initial["rack"] = self.request.GET.get("rack", self.object.rack_id)
        return initial


class DeviceBulkImportView(BulkImportView):
    model = Device
    return_url = reverse_lazy("device_list")


class DeviceDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """设备删除视图"""

    model = Device
    success_message = _("设备已删除")

    def get_success_url(self):
        return reverse("device_list")


class OnlineDeviceListView(BaseRequestMixin, ListViewMixin, ListView):
    model = OnlineDevice
    list_fields = [
        "name",
        "serial_number",
        "rack",
        "position",
        "height",
        "model",
        "type",
        "tenant",
        "status",
        "rack_pdus",
        "ips",
        "tags",
    ]


class OnlineDeviceCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = OnlineDevice
    form_class = DeviceCreateForm
    success_url = reverse_lazy("online_device_list")
    clone_fields = [
        "rack",
        "name",
        "tenant",
        "model",
        "type",
        "height",
        "serial_number",
        "warranty_expiry",
    ]
    fields = [
        "rack",
        "created_at",
        "position",
        "serial_number",
        "name",
        "tenant",
        "model",
        "type",
        "height",
        "rack_pdus",
        "ips",
        "warranty_expiry",
        "tags",
    ]

    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "rack",
                "name",
                "serial_number",
                "model",
                "position",
                "rack_pdus",
                "ips",
            ],
            description=_("设备序列号、位置、型号、IP地址等信息"),
        ),
        FieldSet(
            name=_("配置信息"),
            fields=[
                "tenant",
                "type",
                "height",
                "created_at",
                "warranty_expiry",
                "tags",
            ],
            description=_("设备租户、上架日期、保修期、标签等"),
            collapse=False,
        ),
    ]

    def get_template_names(self):
        """获取模板名称"""
        if self.request.htmx:
            return "onlinedevice/form_htmx.html"
        return "onlinedevice/form.html"

    def clone_object_initial(self, instance):
        """自定义设备克隆逻辑"""
        initial = super().clone_object_initial(instance)
        return initial

    def form_valid(self, form: DeviceBaseForm):
        """表单验证成功处理"""
        # Save without committing to handle M2M fields
        self.object = form.save(commit=False)

        # Set data_center if not set
        if not form.cleaned_data.get("data_center") and hasattr(
            self.model, "data_center"
        ):
            self.object.data_center = self.request.user.data_center

        # Save the main object
        self.object.save()

        # Sync device ports
        self.object._sync_ports()

        # Now save M2M fields
        form.save_m2m()

        # messages.success(self.request, self.success_message)
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if rack := self.request.GET.get("rack", None):
            context["rack"] = Rack.objects.get(pk=rack)
        return context


class OnlineDeviceBulkCreateView(BaseRequestMixin, BulkCreateViewMixin, CreateView):
    model = OnlineDevice
    success_url = reverse_lazy("online_device_list")
    fields = [
        "rack",
        "name",
        "serial_number",
        "model",
        "position",
        "ips",
        "tags",
        "tenant",
        "warranty_expiry",
    ]

    # 配置表单集参数
    extra = 3  # 默认显示3个表单
    min_num = 1
    max_num = 10
    validate_min = True
    validate_max = True

    def get_shared_initial(self):
        """所有表单共享的初始值"""
        initial = super().get_shared_initial()
        initial.update(
            {
                "rack_id": self.request.GET.get("rack_id"),  # 从 URL 获取机柜 ID
            }
        )
        return initial

    def get_dynamic_initial(self, index):
        """每个表单的动态初始值"""
        initial = super().get_dynamic_initial(index)

        # 设置序列化的序列号
        from dcrm.models import CodingRule

        rules = CodingRule.objects.get_for_model(
            self.model, self.request.user.data_center
        )
        if rules.exists():
            for rule in rules:
                initial_value = rule.get_available_codes(1)[0]
                if initial_value and isinstance(initial_value, str):
                    initial[rule.to_field] = initial_value
        return initial


class OnlineDeviceDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = OnlineDevice
    template_name = "onlinedevice/detail.html"
    fields = "__all__"
    extra_tabs = ["ips"]
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": [
                "name",
                "serial_number",
                "rack",
                "position",
                "rack_pdus",
                "model",
                "type",
                "height",
                "tenant",
                "status",
                "warranty_expiry",
                "tags",
            ],
            "description": _("设备的基本信息，包括名称、序列号、型号等"),
        },
        {
            "title": _("配置信息"),
            "fields": ["ips", "warranty_expiry"],
            "description": _("设备的配置和状态信息"),
        },
    ]


class OnlineDeviceUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = OnlineDevice
    form_class = DeviceUpdateForm
    fields = [
        "rack",
        "created_at",
        "position",
        "serial_number",
        "name",
        "tenant",
        "model",
        "type",
        "height",
        "rack_pdus",
        "ips",
        "warranty_expiry",
        "tags",
    ]

    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "rack",
                "name",
                "serial_number",
                "model",
                "rack_pdus",
                "position",
                "created_at",
            ],
            description=_("设备序列号、位置、租户、型号等信息"),
        ),
        FieldSet(
            name=_("状态信息"),
            fields=["tenant", "type", "height", "ips", "warranty_expiry", "tags"],
            description=_("设备IP地址、保修期、标签等"),
            collapse=False,
        ),
    ]

    def get_template_names(
        self,
    ) -> Literal["onlinedevice/form_htmx.html", "onlinedevice/form.html"]:
        """获取模板名称"""
        if self.request.htmx:
            return "onlinedevice/form_htmx.html"
        return "onlinedevice/form.html"

    def get_context_data(self, **kwargs) -> Any:
        context = super().get_context_data(**kwargs)
        context["rack"] = self.object.rack
        if rack := self.request.GET.get("rack", None):
            context["rack"] = Rack.objects.get(pk=rack)
        return context

    def is_migrated(self, prechange, postchange) -> bool:
        """判断是否迁移
        判断依据:
        1. rack 字段改变
        2. rack 没有变化 但是 position 字段改变
        """
        # 检查参数是否存在
        if not prechange or not postchange:
            return False
        # 获取变更前的rack值
        old_rack = prechange.get("rack")
        new_rack = postchange.get("rack")
        if old_rack != new_rack:
            return True
        # 获取变更前后的position值
        old_position = prechange.get("position")
        new_position = postchange.get("position")

        # 如果position字段发生了变化，则认为发生了迁移
        return old_position != new_position

    def form_valid(self, form: ModelForm) -> Any:
        """表单验证成功处理"""
        if hasattr(form.instance, "updated_by"):
            form.instance.updated_by = self.request.user
        # 直接调用UpdateView的form_valid方法，跳过UpdateViewMixin的form_valid方法
        # 避免重复记录日志
        response = super(UpdateViewMixin, self).form_valid(form)
        extra_data = {
            "ipaddr": getattr(self.request, "ipaddr", ""),
            "user_agent": self.request.META.get("HTTP_USER_AGENT"),
        }
        is_migrated = self.is_migrated(
            self.prechange_data, serialize_object(self.object)
        )
        LogEntry.objects.log_action(
            user=self.request.user,
            action=ChangeActionChoices.UPDATE,
            action_type="device_migrate" if is_migrated else "device_update",
            object_repr=self.object,
            message=f"{self.success_message}: ({str(self.object)})",
            changed=True,
            prechange_data=self.prechange_data,
            postchange_data=serialize_object(self.object),
            extra_data=extra_data,
        )
        return response

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        initial["rack"] = self.request.GET.get("rack", self.object.rack_id)
        return initial


class OnlineDeviceBulkImportView(BulkImportView):
    model = OnlineDevice
    return_url = reverse_lazy("online_device_list")


class OnlineDeviceDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """设备删除视图"""

    model = OnlineDevice
    success_message = _("设备已删除")

    def get_success_url(self):
        return reverse("device_list")


class DeviceModelListView(BaseRequestMixin, ListViewMixin, ListView):
    model = DeviceModel
    list_fields = [
        "name",
        "type",
        "height",
        "manufacturer",
        "ethernet_port_count",
        "fiber_port_count",
        "console_port_count",
        "usb_port_count",
        "power_port_count",
        "mgmt_port_count",
        "other_port_count",
        "shared",
        "data_center",
    ]


class DeviceModelDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = DeviceModel
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": [
                "manufacturer",
                "name",
                "type",
                "height",
                "description",
                "shared",
                "tags",
            ],
            "description": _("设备型号的基本信息"),
        },
        {
            "title": _("端口配置"),
            "fields": [
                "ethernet_port_count",
                "fiber_port_count",
                "console_port_count",
                "usb_port_count",
                "power_port_count",
                "mgmt_port_count",
                "other_port_count",
            ],
            "description": _("设备型号的端口配置信息"),
        },
    ]


class DeviceModelCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = DeviceModel
    form_class = DeviceModelForm
    fields = [
        "manufacturer",
        "type",
        "name",
        "height",
        "ethernet_port_count",
        "fiber_port_count",
        "console_port_count",
        "usb_port_count",
        "power_port_count",
        "mgmt_port_count",
        "other_port_count",
        "description",
        "shared",
        "tags",
    ]

    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "manufacturer",
                "type",
                "name",
                "height",
                "shared",
                "description",
                "tags",
            ],
            description=_("设备型号的基本信息，包括制造商、名称、类型和高度"),
        ),
        FieldSet(
            name=_("端口配置"),
            fields=[
                "ethernet_port_count",
                "fiber_port_count",
                "console_port_count",
                "usb_port_count",
                "power_port_count",
                "mgmt_port_count",
                "other_port_count",
            ],
            description=_("设备型号的各类端口数量配置"),
        ),
    ]


class DeviceModelUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = DeviceModel
    fields = [
        "manufacturer",
        "type",
        "name",
        "height",
        "ethernet_port_count",
        "fiber_port_count",
        "console_port_count",
        "usb_port_count",
        "power_port_count",
        "mgmt_port_count",
        "other_port_count",
        "description",
        "shared",
        "tags",
    ]

    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "manufacturer",
                "type",
                "name",
                "height",
                "shared",
                "description",
                "tags",
            ],
            description=_("设备型号的基本信息，包括制造商、名称、类型和高度"),
        ),
        FieldSet(
            name=_("端口配置"),
            fields=[
                "ethernet_port_count",
                "fiber_port_count",
                "console_port_count",
                "usb_port_count",
                "power_port_count",
                "mgmt_port_count",
                "other_port_count",
            ],
            description=_("设备型号的各类端口数量配置"),
        ),
    ]

    def render_row_actions(self, obj: Model) -> str:
        """渲染行操作按钮"""
        parent_actions = super().render_row_actions(obj)
        if self.request.user.has_perm(get_permission_codename("change", self.opts)):
            verify = all(
                [
                    obj.port_type in ["ethernet", "fiber", "console", "usb"],
                    obj.status == DevicePortStatusChoices.DISCONNECTED,
                ]
            )
            if verify:
                if obj.is_pre_connected():
                    title = _("已添加")
                    label_class = "label-success"
                else:
                    title = _("预连接")
                    label_class = "label-info"
                href = reverse("pre_add_node_api", args=[obj.id])
                pre_connect_btn = format_html(
                    '<a href="javascript:void(0)" class="label {} margin-r-5" '
                    'data-toggle="control-sidebar" '
                    'data-drawer-width="320" data-drawer-title="预连接" '
                    'data-id="{}" data-handle-url="{}">'
                    "{}</a>",
                    label_class,
                    obj.id,
                    href,
                    title,
                )
                return mark_safe(f"{pre_connect_btn}{parent_actions}")
        return mark_safe(parent_actions)


class DeviceModelBulkImportView(BulkImportView):
    model = DeviceModel
    return_url = reverse_lazy("device_model_list")


class DeviceModelDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """设备型号删除视图"""

    model = DeviceModel
    success_message = _("设备型号已删除")

    def get_success_url(self):
        return reverse("device_model_list")


class DevicePortListView(BaseRequestMixin, ListViewMixin, ListView):
    model = DevicePort
    list_fields = [
        "name",
        "port_type",
        "device",
        "status",
        "connected_to",
        "connected_object",
        "description",
    ]


class DevicePortDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = DevicePort
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": ["device", "name", "port_type", "description", "tags"],
            "description": _("端口的基本信息"),
        },
        {
            "title": _("连接信息"),
            "fields": [
                "status",
                "connected_to",
                "connected_object_id",
                "connected_object",
            ],
            "description": _("端口的连接状态和对象"),
        },
    ]


class DevicePortCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = DevicePort
    fields = ["device", "name", "port_type", "description", "tags"]
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=["device", "name", "port_type"],
            description=_("设备端口的基本信息，包括所属设备、名称和类型"),
        ),
        FieldSet(
            name=_("其他信息"),
            fields=["description", "tags"],
            description=_("设备端口的描述和标签"),
            collapse=False,
        ),
    ]


class DevicePortUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = DevicePort
    fields = [
        "device",
        "name",
        "port_type",
        # "status",
        "connected_to",
        "connected_object_id",
        "description",
        "tags",
    ]
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=["device", "name", "port_type"],
            description=_("设备端口的基本信息，包括所属设备、名称和类型"),
        ),
        FieldSet(
            name=_("连接信息"),
            fields=["connected_to", "connected_object_id"],
            description=_("设备端口的连接状态和连接对象"),
        ),
        FieldSet(
            name=_("其他信息"),
            fields=["description", "tags"],
            description=_("设备端口的描述和标签"),
            collapse=False,
        ),
    ]


class DevicePortBulkImportView(BulkImportView):
    model = DevicePort
    return_url = reverse_lazy("device_port_list")


class DevicePortDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """设备端口删除视图"""

    model = DevicePort
    success_message = _("设备端口已删除")

    def get_success_url(self):
        return reverse("device_port_list")


class DeviceHostListView(BaseRequestMixin, ListViewMixin, ListView):
    model = DeviceHost
    list_fields = [
        "name",
        "hostname",
        "os_type",
        "os_version",
        "kernel_version",
        "cpu_cores",
        "memory_size",
        "disk_size",
        "device",
        "status",
        "group",
        "description",
        "username",
        "password",
        "ssh_port",
        "ssh_key",
        "auth_type",
    ]


class DeviceHostCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = DeviceHost
    fields = [
        "name",
        "hostname",
        "os_type",
        "os_version",
        "kernel_version",
        "cpu_cores",
        "memory_size",
        "disk_size",
        "device",
        "status",
        "group",
        "description",
        "username",
        "_password",
        "ssh_port",
        "ssh_key",
        "auth_type",
        "ips",
        "tags",
    ]
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "device",
                "name",
                "hostname",
                "os_type",
                "os_version",
                "kernel_version",
                "cpu_cores",
                "memory_size",
                "disk_size",
            ],
            description=_("主机的基本信息，包括租户设备信息、硬件信息和系统信息等"),
        ),
        FieldSet(
            name=_("认证信息"),
            fields=[
                "auth_type",
                "username",
                "_password",
                "ssh_key",
                "ssh_port",
            ],
            description=_("主机的登录认证信息"),
        ),
        FieldSet(
            name=_("其他信息"),
            fields=["description", "group", "status", "ips", "tags"],
            description=_("主机的分组和描述信息"),
            collapse=False,
        ),
    ]


class DeviceHostUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = DeviceHost
    fields = [
        "name",
        "hostname",
        "os_type",
        "os_version",
        "kernel_version",
        "cpu_cores",
        "memory_size",
        "disk_size",
        "device",
        "status",
        "group",
        "description",
        "username",
        "_password",
        "ssh_port",
        "ssh_key",
        "auth_type",
        "ips",
        "tags",
    ]
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "device",
                "name",
                "hostname",
                "os_type",
                "os_version",
                "kernel_version",
                "cpu_cores",
                "memory_size",
                "disk_size",
            ],
            description=_("主机的基本信息，包括租户设备信息、硬件信息和系统信息等"),
        ),
        FieldSet(
            name=_("认证信息"),
            fields=[
                "auth_type",
                "username",
                "_password",
                "ssh_key",
                "ssh_port",
            ],
            description=_("主机的登录认证信息"),
        ),
        FieldSet(
            name=_("其他信息"),
            fields=["description", "group", "status", "ips", "tags"],
            description=_("主机的分组和描述信息"),
            collapse=False,
        ),
    ]


class DeviceHostDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = DeviceHost
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": ["name", "hostname", "device"],
            "description": _("主机的基本信息"),
        },
        {
            "title": _("网络配置"),
            "fields": ["status", "ips", "ssh_port"],
            "description": _("主机的网络配置"),
        },
        {
            "title": _("认证信息"),
            "fields": ["auth_type", "username", "password", "ssh_key"],
            "description": _("主机的认证信息"),
        },
        {
            "title": _("系统配置"),
            "fields": [
                "os_type",
                "os_version",
                "kernel_version",
                "cpu_cores",
                "memory_size",
                "disk_size",
            ],
            "description": _("主机的系统和硬件配置"),
        },
        {
            "title": _("其他信息"),
            "fields": ["group", "description"],
            "description": _("主机的其他补充信息"),
        },
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 添加IP地址列表
        if hasattr(self.object, "ips"):
            context["ip_addresses"] = self.object.ips.all()
        return context


class DeviceHostBulkImportView(BulkImportView):
    model = DeviceHost
    return_url = reverse_lazy("device_host_list")


class DeviceHostDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """设备主机删除视图"""

    model = DeviceHost
    success_message = _("设备主机已删除")

    def get_success_url(self):
        return reverse("device_host_list")


class DeviceTypeListView(BaseRequestMixin, ListViewMixin, ListView):
    model = DeviceType
    list_fields = [
        "name",
        "code",
        "icon_with_html",
        "color_with_html",
        "description",
        "tags",
        "shared",
        "data_center",
    ]


class DeviceTypeDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = DeviceType
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": [
                "name",
                "code",
                "color",
                "color_with_html",
                "icon_with_html",
                "description",
                "shared",
                "tags",
                "data_center",
            ],
            "description": _("设备类型的基本信息"),
        },
    ]


class DeviceTypeCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = DeviceType
    fields = [
        "name",
        "color",
        "code",
        "icon",
        "shared",
        "description",
        "tags",
    ]

    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "name",
                "color",
                "code",
                "icon",
                "shared",
                "description",
                "tags",
            ],
            description=_("设备类型的基本信息，名称、颜色，编码等"),
        ),
    ]


class DeviceTypeUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = DeviceType
    fields = [
        "name",
        "color",
        "code",
        "icon",
        "shared",
        "description",
        "tags",
    ]

    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "name",
                "color",
                "code",
                "icon",
                "shared",
                "description",
                "tags",
            ],
            description=_("设备类型的基本信息，名称、颜色，编码等"),
        ),
    ]


class DeviceTypeBulkImportView(BulkImportView):
    model = DeviceType
    return_url = reverse_lazy("device_type_list")


class DeviceTypeDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """设备型号删除视图"""

    model = DeviceType
    success_message = _("设备类型已删除")

    def get_success_url(self):
        return reverse("device_type_list")
