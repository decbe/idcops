from functools import cached_property
from typing import Any, Dict, List, Tuple

from django.contrib import messages
from django.contrib.admin.utils import NestedObjects
from django.contrib.auth import get_permission_codename
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db import router
from django.db.models.deletion import ProtectedError
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse, reverse_lazy
from django.utils import timezone
from django.utils.html import format_html
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _

from dcrm.models.base import LogEntry
from dcrm.models.choices import ChangeActionChoices
from dcrm.utilities.base import camel_to_snake
from dcrm.utilities.display import camel_to_snake
from dcrm.utilities.serialization import serialize_object

from .base import HtmxResponseMixin

__all__ = [
    "DeleteViewMixin",
]


class DeleteViewMixin(HtmxResponseMixin, PermissionRequiredMixin):
    """通用删除视图 Mixin

    特性:
    1. 自动检测关联对象
    2. 支持批量删除
    3. 支持软删除
    4. 集成 HTMX
    5. 支持撤销删除
    6. 处理受保护的外键关系
    """

    template_name = "confirm_delete.html"
    success_message = _("删除成功")
    cancel_url = None

    def get_permission_required(self):
        codename = get_permission_codename("delete", self.opts)
        self.permission_required = f"{self.opts.app_label}.{codename}"
        return super().get_permission_required()

    def handle_no_permission(self):
        verbose_name = self.model._meta.verbose_name
        messages.warning(self.request, f"您没有删除 {verbose_name} 的权限.")
        return super().handle_no_permission()

    def get_cancel_url(self) -> str:
        """获取取消按钮的URL"""
        if self.cancel_url:
            return self.cancel_url
        prefix = camel_to_snake(self.model._meta.object_name)
        return reverse_lazy(f"{prefix}_list")

    def get_success_url(self) -> str:
        """获取成功后的跳转URL"""
        return self.get_cancel_url()

    def get_object_url(self, obj):
        """获取对象的详细页面URL

        Args:
            obj: 需要获取URL的对象

        Returns:
            str: 对象的URL，如果没有则返回 None
        """
        try:
            # 使用 camel_to_snake 转换模型名称
            view_name = f"{camel_to_snake(obj.__class__.__name__)}_detail"
            return reverse(view_name, kwargs={"pk": obj.pk})
        except NoReverseMatch:
            return None

    def format_callback(self, obj):
        """格式化对象显示

        Args:
            obj: 需要格式化的对象

        Returns:
            str: 格式化后的对象显示文本，如果有URL则包含链接
        """
        opts = obj._meta
        no_edit_link = "%s: %s" % (capfirst(opts.verbose_name), obj)

        try:
            # 使用 camel_to_snake 转换模型名称
            view_name = f"{camel_to_snake(obj.__class__.__name__)}_detail"
            url = reverse(view_name, kwargs={"pk": obj.pk})
            # 显示带链接的文本
            return format_html(
                '{}: <a href="{}">{}</a>', capfirst(opts.verbose_name), url, obj
            )
        except NoReverseMatch:
            # 如果没有详情页面，只显示文本
            return no_edit_link

    def get_deleted_objects(self):
        """获取将被删除的对象列表和受保护的对象

        Returns:
            Tuple: (要删除的对象列表, 模型计数, 受保护对象)
        """
        collector = NestedObjects(using=router.db_for_write(self.model))
        collector.collect([self.object])

        # 获取要删除的对象、受保护的对象等
        to_delete = collector.nested()
        model_count = {
            model._meta.verbose_name: len(objs)
            for model, objs in collector.model_objs.items()
        }

        return to_delete, model_count, collector.protected

    @cached_property
    def current_datacenter(self):
        return self.request.user.data_center

    def get_protected_objects(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取受保护的关联对象

        Returns:
            Dict[str, List[Dict]]: {
                模型名称: [{
                    'object': 对象字符串表示,
                    'url': 对象URL
                }]
            }
        """
        _, _, protected = self.get_deleted_objects()

        # 按模型分组受保护的对象
        grouped_objects = {}

        for obj in protected:
            if obj.data_center != self.current_datacenter:  # 排除非当前用户机房的条目
                continue
            if not hasattr(obj, "_meta"):
                continue

            model_name = obj._meta.verbose_name
            if model_name not in grouped_objects:
                grouped_objects[model_name] = []

            url = self.get_object_url(obj)
            grouped_objects[model_name].append({"object": str(obj), "url": url})

        return grouped_objects

    def get_related_objects(self) -> List[Tuple[str, List[Dict[str, Any]]]]:
        """获取关联对象

        Returns:
            List[Tuple[str, List[Dict]]]: [
                (模型名称, [{
                    'object': 对象字符串表示,
                    'url': 对象URL
                }])
            ]
        """
        to_delete, _, _ = self.get_deleted_objects()
        result = []

        def process_nested_objects(obj_list):
            """处理嵌套对象列表"""
            if not isinstance(obj_list, (list, tuple)):
                return

            # 如果列表为空，直接返回
            if not obj_list:
                return

            # 获取第一个元素
            first_item = obj_list[0]

            # 如果第一个元素是模型实例
            if hasattr(first_item, "_meta"):
                model_name = first_item._meta.verbose_name
                # 格式化每个对象
                objects = []
                for item in obj_list:
                    if item != self.object:  # 排除当前对象
                        try:
                            url = self.get_object_url(item)
                            objects.append({"object": str(item), "url": url})
                        except (AttributeError, TypeError):
                            continue
                if objects:  # 只添加非空列表
                    result.append((model_name, objects))
            # 如果是嵌套列表，递归处理
            elif isinstance(first_item, (list, tuple)):
                for item in obj_list:
                    process_nested_objects(item)

        process_nested_objects(to_delete)
        return result

    def get_context_data(self, **kwargs) -> Dict[str, Any]:
        """获取上下文数据"""
        context = super().get_context_data(**kwargs)
        protected_objects = self.get_protected_objects()

        context.update(
            {
                "title": _("确认删除"),
                "subtitle": str(self.object),
                "cancel_url": self.get_cancel_url(),
                "related_objects": self.get_related_objects(),
                "protected_objects": protected_objects,
                "can_delete": len(protected_objects) == 0,
            }
        )
        return context

    def form_valid(self, form):
        """处理表单验证成功的情况"""
        self.object = self.get_object()
        success_url = self.get_success_url()
        try:
            extra_data = {
                "ipaddr": self.request.ipaddr,
                "user_agent": self.request.META.get("HTTP_USER_AGENT"),
            }
            content_type = ContentType.objects.get_for_model(self.object._meta.model)
            prechange_data = serialize_object(self.object, delete=True)
            object_repr = str(self.object)
            self.object.delete()

            LogEntry.objects.create(
                created_by=self.request.user,
                data_center=self.request.user.data_center,
                action=ChangeActionChoices.DELETE,
                action_type="delete",
                content_type=content_type,
                object_id=0,
                message=f"{self.success_message}: ({object_repr})",
                timestamp=str(int(timezone.now().timestamp() * 1000)),
                prechange_data=prechange_data,
                postchange_data={},
                extra_data=extra_data,
            )
            messages.success(self.request, self.success_message)
            return redirect(success_url)
        except ProtectedError:
            messages.error(
                self.request,
                _("无法删除 %(object)s，因为它正在被其他对象引用。")
                % {"object": str(self.object)},
            )
            return self.render_to_response(self.get_context_data(form=form))
