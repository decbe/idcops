import sys
from typing import Any

from django.contrib import messages
from django.forms.models import modelformset_factory
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_htmx.http import HttpResponseClientRedirect

from dcrm.forms.deivce import DeviceMigrateForm
from dcrm.models import Device, LogEntry, OnlineDevice
from dcrm.models.choices import (
    NETWORK_PORT_TYPES,
    ActionColorChoices,
    ChangeActionChoices,
    DevicePortStatusChoices,
    DevicePortTypeChoices,
    DeviceStatusChoices,
    IPAddressStatusChoices,
    RackPDUStatusChoices,
)
from dcrm.utilities.serialization import serialize_object

from .actions import registry

__all__ = ["device_move_down", "device_migrate"]


@registry.register(
    name=_("下架"),
    models=(OnlineDevice,),
    permissions=("change",),
    description=_("将设备下架，不允许同时下架多个客户的设备"),
    color=ActionColorChoices.DEFAULT,
    icon="fa fa-level-down",
    order=100,
    is_htmx=True,
    confirm_message=_("确定要下架这些设备吗？？"),
)
def device_move_down(request, instances, **kwargs) -> Any | HttpResponseClientRedirect:
    queryset = instances.filter(
        data_center=request.user.data_center,
        status__in=[DeviceStatusChoices.MOUNTED, DeviceStatusChoices.MIGRATED],
    )
    if not queryset.exists():
        # 防止其他位置触发
        messages.error(request, _("选择中没有可下架的设备"))
        return reverse("online_device_list")
    action_type = sys._getframe().f_code.co_name
    extra_data = {
        "ipaddr": request.ipaddr,
        "user_agent": request.META.get("HTTP_USER_AGENT"),
    }
    for device in queryset:
        # 变更前的数据
        old_data = serialize_object(device)
        # 更新设备状态
        device.status = DeviceStatusChoices.UNMOUNTED
        device.updated_by = request.user
        device.save()
        # 更新设备电源端口状态
        device.ports.filter(port_type=DevicePortTypeChoices.POWER).update(
            status=DevicePortStatusChoices.DISCONNECTED,
            connected_object_id=None,
            connected_to=None,
        )
        # 更新设备pdus状态
        device.rack_pdus.update(status=RackPDUStatusChoices.EMPTY)
        device.ips.update(
            status=IPAddressStatusChoices.ALLOCATED,  # 手动回收或释放，才移除IP地址归属租户
            connected_to=None,
            connected_object_id=None,
        )
        # 检测设备端口网络跳线连接
        device.ports.filter(port_type__in=NETWORK_PORT_TYPES).update(
            status=DevicePortStatusChoices.DISCONNECTED
        )
        # TODO: 通知组用户

        # 记录日志
        message = f"从 {device.rack}({device.position}U) 下架了 {device.tenant} 的设备 ({device.name})"
        LogEntry.objects.log_action(
            user=request.user,
            action=ChangeActionChoices.UPDATE,
            action_type=action_type,
            object_repr=device,
            message=message,
            prechange_data=old_data,
            postchange_data=serialize_object(device),
            changed=True,
            extra_data=extra_data,
        )
    messages.success(request, _("下架成功"))
    return HttpResponseClientRedirect(reverse("online_device_list"))


@registry.register(
    name=_("迁移"),
    is_htmx=True,
    models=(OnlineDevice,),
    permissions=("change",),
    description=_("批量迁移设备"),
    color=ActionColorChoices.DEFAULT,
    icon="fa fa-exchange",
    order=100,
)
def device_migrate(
    request, instances, **kwargs
) -> HttpResponseClientRedirect | Any | TemplateResponse:
    """设备位置变更
    1. 设备U位一定会变更
    2. 设备PDU可能会变更
    """
    user = request.user
    queryset = instances.filter(
        data_center=user.data_center,
        status__in=[DeviceStatusChoices.MOUNTED, DeviceStatusChoices.MIGRATED],
    )
    if not queryset.exists():
        messages.error(request, _("选择的设备中，没有可迁移的设备"))
        return HttpResponseClientRedirect(reverse("online_device_list"))
    fields = ["rack", "position", "rack_pdus", "ips"]
    _MigrateForm = modelformset_factory(
        Device,
        form=DeviceMigrateForm,
        fields=fields,
        edit_only=True,
        extra=0,
        can_delete=False,
    )
    formset = _MigrateForm(queryset=queryset, form_kwargs={"request": request})
    detail_fields = [
        "name",
        "tenant",
        "rack",
        "position",
        "height",
        "rack_pdus",
    ]
    context = {
        "action": registry.get_action(OnlineDevice, "device_migrate"),
        "formset": formset,
        "detail_fields": detail_fields,
        "next_url": reverse("online_device_list"),
    }
    _verify = all(
        [
            request.POST.get("action") == "device_migrate",
            request.POST.get("apply") == "true",
        ]
    )
    if _verify:
        # 前端返回的数据
        formset = _MigrateForm(request.POST, form_kwargs={"request": request})
        if formset.is_valid():
            # 前端返回的数据
            formset.save()
            messages.success(request, _("迁移成功"))
            return reverse("online_device_list")
        else:
            messages.error(request, _("设备迁移失败"))
            return TemplateResponse(request, "device/migrate_form.html", context)
    else:
        context["formset"] = formset
    return TemplateResponse(request, "device/migrate_form.html", context)
