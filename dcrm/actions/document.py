import sys
from typing import Any

from django.contrib import messages
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_htmx.http import HttpResponseClientRedirect

from dcrm.models import Category, Document, LogEntry, Tag
from dcrm.models.choices import ActionColorChoices, ChangeActionChoices
from dcrm.utilities.serialization import serialize_object

from .actions import registry

__all__ = [
    "set_document_classification",
    "set_document_status",
]


@registry.register(
    name=_("设置分类标签"),
    models=(Document,),
    permissions=("change",),
    description=_("批量设置文档的分类和标签"),
    color=ActionColorChoices.DEFAULT,
    icon="fa fa-tags",
    order=100,
    is_htmx=True,
)
def set_document_classification(
    request, instances, **kwargs
) -> HttpResponseClientRedirect | Any | TemplateResponse:
    """批量设置文档的分类和标签
    """
    queryset = instances.filter(data_center=request.user.data_center)
    if not queryset.exists():
        messages.error(request, _("请选择要操作的文档"))
        return HttpResponseClientRedirect(reverse("document_list"))

    # 获取可用的分类和标签
    categories = Category.objects.filter(data_center=request.user.data_center)
    tags = Tag.get_available_tags(
        data_center=request.user.data_center, model=Document, include_shared=True
    )

    context = {
        "action": registry.get_action(Document, "set_document_classification"),
        "instances": queryset,
        "categories": categories,
        "tags": tags,
        "next_url": reverse("document_list"),
    }

    # 检查是否为表单提交
    handle_verify = all(
        [
            request.POST.get("action") == "set_document_classification",
            request.POST.get("apply") == "true",
        ]
    )

    if handle_verify:
        # 获取表单数据
        category_ids = request.POST.getlist("categories")
        tag_ids = request.POST.getlist("tags")

        # 记录操作日志
        action_type = sys._getframe().f_code.co_name
        extra_data = {
            "ipaddr": getattr(request, "ipaddr", "") or "",
            "user_agent": request.META.get("HTTP_USER_AGENT"),
        }

        for document in queryset:
            # 变更前的数据
            old_data = serialize_object(document)

            # 更新分类
            if category_ids:
                document.categories.set(category_ids)
            else:
                document.categories.clear()

            # 更新标签
            if tag_ids:
                document.tags.set(tag_ids)
            else:
                document.tags.clear()

            document.updated_by = request.user
            document.save()

            # 记录日志
            category_names = ", ".join([cat.name for cat in document.categories.all()])
            tag_names = ", ".join([tag.name for tag in document.tags.all()])
            message = f"设置文档 '{document.title}' 的分类为: {category_names or '无'}, 标签为: {tag_names or '无'}"

            LogEntry.objects.log_action(
                user=request.user,
                action=ChangeActionChoices.UPDATE,
                action_type=action_type,
                object_repr=document,
                message=message,
                prechange_data=old_data,
                postchange_data=serialize_object(document),
                changed=True,
                extra_data=extra_data,
            )

        messages.success(request, _("分类和标签设置成功"))
        return reverse("document_list")

    # 显示表单
    return TemplateResponse(request, "document/set_classification.html", context)


@registry.register(
    name=_("设置状态"),
    models=(Document,),
    permissions=("change",),
    description=_("批量设置文档状态"),
    color=ActionColorChoices.DEFAULT,
    icon="fa fa-toggle-on",
    order=110,
    is_htmx=True,
)
def set_document_status(
    request, instances, **kwargs
) -> HttpResponseClientRedirect | TemplateResponse | Any:
    """批量设置文档状态
    """
    queryset = instances.filter(data_center=request.user.data_center)
    if not queryset.exists():
        messages.error(request, _("请选择要操作的文档"))
        return HttpResponseClientRedirect(reverse("document_list"))

    context = {
        "action": registry.get_action(Document, "set_document_status"),
        "instances": queryset,
        "status_choices": Document._meta.get_field("status").choices,
        "next_url": reverse("document_list"),
    }

    # 检查是否为表单提交
    handle_verify = all(
        [
            request.POST.get("action") == "set_document_status",
            request.POST.get("apply") == "true",
        ]
    )

    if handle_verify:
        # 获取表单数据
        new_status = request.POST.get("status")

        if not new_status:
            messages.error(request, _("请选择文档状态"))
            return TemplateResponse(request, "document/set_status.html", context)

        # 验证状态值是否有效
        valid_statuses = [
            choice[0] for choice in Document._meta.get_field("status").choices
        ]
        if new_status not in valid_statuses:
            messages.error(request, _("无效的文档状态"))
            return TemplateResponse(request, "document/set_status.html", context)

        # 记录操作日志
        action_type = sys._getframe().f_code.co_name
        extra_data = {
            "ipaddr": getattr(request, "ipaddr", "") or "",
            "user_agent": request.META.get("HTTP_USER_AGENT"),
        }

        for document in queryset:
            # 变更前的数据
            old_data = serialize_object(document)

            # 更新状态
            document.status = new_status
            document.updated_by = request.user
            document.save()

            # 记录日志
            status_display = dict(Document._meta.get_field("status").choices).get(
                new_status, new_status
            )
            message = f"将文档 '{document.title}' 的状态设置为: {status_display}"

            LogEntry.objects.log_action(
                user=request.user,
                action=ChangeActionChoices.UPDATE,
                action_type=action_type,
                object_repr=document,
                message=message,
                prechange_data=old_data,
                postchange_data=serialize_object(document),
                changed=True,
                extra_data=extra_data,
            )

        messages.success(request, _("文档状态设置成功"))
        return reverse("document_list")

    # 显示表单
    return TemplateResponse(request, "document/set_status.html", context)
