from typing import Any

from django import forms
from django.contrib import messages
from django.db.models import Q
from django.forms.models import modelformset_factory
from django.http.response import HttpResponsePermanentRedirect, HttpResponseRedirect
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from dcrm.forms.base import BaseModelFormMixin
from dcrm.models import LogEntry, Rack, RackStatus
from dcrm.models.choices import ActionColorChoices, ChangeActionChoices
from dcrm.utilities.serialization import serialize_object

from .actions import registry

__all__ = ["rack_allocate", "rack_deallocate"]


# 机柜操作
@registry.register(
    name=_("分配机柜"),
    models=(Rack,),
    permissions=("add", "change"),
    description=_("将机柜分配给指定租户"),
    color=ActionColorChoices.DEFAULT,
    icon="fa fa-puzzle-piece",
    order=100,
    is_htmx=True,
)
def rack_allocate(
    request, instances, **kwargs
) -> HttpResponsePermanentRedirect | HttpResponseRedirect | Any | TemplateResponse:
    """分配机柜"""
    user = request.user

    # 机柜状态可分配
    query = Q(data_center=user.data_center) | Q(shared=True)
    can_allocate_status = (
        RackStatus.objects.filter(query)
        .filter(allowed_mount=False)
        .values_list("id", flat=True)
    )
    rack_query = Q(data_center=user.data_center, status__isnull=True) | Q(
        data_center=user.data_center, status__in=can_allocate_status
    )
    queryset = instances.filter(rack_query)
    if not queryset.exists():
        # 没有可分配的机柜
        messages.error(request, _("选择的机柜中，没有可分配的机柜"))
        return redirect("rack_list")

    fields = [
        "room",
        "name",
        "rack_type",
        "tenant",
        "status",
        "opening_date",
        "contract_power",
    ]
    _BaseModelFormSet = modelformset_factory(
        Rack,
        form=BaseModelFormMixin,
        fields=fields,
        edit_only=True,
        extra=0,
        can_delete=False,
        widgets={
            "name": forms.TextInput(attrs={"readonly": True}),
            "room": forms.Select(attrs={"readonly": True}),
            "tenant": forms.Select(attrs={"required": False}),
        },
    )
    formset = _BaseModelFormSet(form_kwargs={"request": request}, queryset=queryset)
    context = {
        "action": registry.get_action(Rack, "rack_allocate"),
        "next_url": reverse("rack_list"),
        "formset": formset,
    }
    # 如果是POST请求，更新机柜状态
    handle_verfiy = all(
        [
            request.POST.get("action") == "rack_allocate",
            request.POST.get("apply") == "true",
        ]
    )
    if handle_verfiy:
        original_objects = {
            instance.id: serialize_object(instance) for instance in queryset
        }
        formset = _BaseModelFormSet(
            request.POST,
            form_kwargs={"request": request},
        )
        if formset.is_valid():
            formset.save()
            messages.success(request, _(f"机柜分配成功，共 {queryset.count()} 个"))
            # 记录日志
            for rack in formset:
                instance = rack.instance
                tenant = rack.cleaned_data["tenant"]
                if tenant:
                    message = f'分配机柜: ({instance.name}): {instance.status}, {rack.cleaned_data["tenant"]}'
                else:
                    message = f"分配机柜: ({instance.name}): {instance.status}"
                # 记录日志
                extra_data = {
                    "ipaddr": request.ipaddr,
                    "user_agent": request.META.get("HTTP_USER_AGENT"),
                }
                LogEntry.objects.log_action(
                    user=user,
                    action=ChangeActionChoices.UPDATE,
                    action_type="rack_allocate",
                    object_repr=instance,
                    message=message,
                    prechange_data=original_objects[instance.id],
                    postchange_data=serialize_object(instance),
                    extra_data=extra_data,
                )
            return reverse("rack_list")
        else:
            messages.error(request, _("机柜分配失败"))
            return TemplateResponse(request, "rack/rack_allocate.html", context)
    return TemplateResponse(request, "rack/rack_allocate.html", context)


@registry.register(
    name=_("释放"),
    models=(Rack,),
    permissions=("add", "change"),
    description=_("将机柜释放出来，必须先清空机柜中的设备"),
    color=ActionColorChoices.DEFAULT,
    icon="fa fa-recycle",
    order=150,
    is_htmx=True,
    confirm_message=_("确定要释放这些机柜吗？？"),
)
def rack_deallocate(
    request, instances, **kwargs
) -> HttpResponsePermanentRedirect | HttpResponseRedirect:
    """解除机柜分配,
    1. 更新机柜状态
    2. 记录日志
    """
    user = request.user
    queryset = instances.filter(
        data_center=user.data_center, status__allowed_mount=True
    )
    if not queryset.exists():
        # 没有可释放的机柜
        messages.error(request, _("选择的机柜中，没有可释放的机柜"))
        return redirect("rack_list")
    protect_count = 0
    for rack in queryset:
        # 更新机柜状态
        if rack.mounted_devices.exists():
            protect_count += 1
            continue
        prechange_data = serialize_object(rack)
        rack.status = None
        rack.opening_date = None
        rack.contract_power = None
        rack.tenant = None
        rack.updated_by = user
        rack.save()
        # 记录日志
        postchange_data = serialize_object(rack)
        extra_data = {
            "ipaddr": request.ipaddr,
            "user_agent": request.META.get("HTTP_USER_AGENT"),
        }
        LogEntry.objects.log_action(
            user=user,
            action=ChangeActionChoices.UPDATE,
            action_type="rack_deallocate",
            object_repr=rack,
            message=f"释放机柜: ({rack.name})",
            prechange_data=prechange_data,
            postchange_data=postchange_data,
            extra_data=extra_data,
        )
    if queryset.count() == protect_count:
        message = _(f"选中的{protect_count}个机柜中，有设备未下架")
        state = messages.WARNING
    else:
        if protect_count:
            message = _(
                f"释放机柜:共 {queryset.count()-protect_count} 个，{protect_count} 个机柜设备未下架"
            )
        else:
            message = _(f"释放机柜: 共 {queryset.count()} 个")
        state = messages.SUCCESS
    messages.add_message(request, state, message)
    return redirect("rack_list")
