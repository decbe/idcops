from django.contrib import messages
from django.urls import reverse
from django.utils.timezone import datetime
from django.utils.translation import gettext as _
from django_htmx.http import HttpResponseClientRedirect

from dcrm.models import CustomField, LogEntry
from dcrm.models.choices import ActionColorChoices, ChangeActionChoices
from dcrm.utilities.serialization import serialize_object

from .actions import registry

__all__ = ["disable_custom_field"]


@registry.register(
    name=_("禁用字段"),
    description=_("禁用自定义字段"),
    is_htmx=True,
    confirm_message=_("确定要禁用这些字段吗？？"),
    models=(CustomField,),
    permissions=("add", "change"),
    color=ActionColorChoices.DEFAULT,
    icon="fa fa-close",
    order=100,
)
def disable_custom_field(request, queryset, **kwargs):
    """禁用自定义字段
    """
    queryset = queryset.filter(is_active=True)
    if not queryset:
        messages.warning(request, _("没有需要禁用的自定义字段"))
        return HttpResponseClientRedirect(reverse("custom_field_list"))
    for custom_field in queryset:
        old_data = serialize_object(custom_field)
        custom_field.is_active = False
        custom_field.updated_by = request.user
        custom_field.updated_at = datetime.now()
        custom_field.save(update_fields=["is_active", "updated_by", "updated_at"])
        # TODO: 禁用之后，要检查用户的自定义列表显示配置

        # 记录日志
        message = f"禁用了 {custom_field.name} 字段"
        extra_data = {
            "ipaddr": request.ipaddr,
            "user_agent": request.META.get("HTTP_USER_AGENT"),
        }
        LogEntry.objects.log_action(
            user=request.user,
            action=ChangeActionChoices.UPDATE,
            action_type="disable_custom_field",
            object_repr=custom_field,
            message=message,
            prechange_data=old_data,
            postchange_data=serialize_object(custom_field),
            changed=True,
            extra_data=extra_data,
        )
    messages.success(request, _("已成功禁用自定义字段"))
    return HttpResponseClientRedirect(reverse("custom_field_list"))
