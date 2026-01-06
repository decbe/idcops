import logging
from typing import Any, Literal, Never

from django.contrib import messages
from django.contrib.auth import get_permission_codename
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.fields.related import ForeignKey, ManyToManyField, OneToOneField
from django.http import HttpResponseRedirect
from django.http.response import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from dcrm.forms.comment import CommentForm
from dcrm.models import CustomField
from dcrm.models.base import Comment, DataCenter, DataCenterGroup, LogEntry
from dcrm.models.choices import ChangeActionChoices
from dcrm.models.customfields import CustomFieldVisibilityChoices
from dcrm.utilities.base import camel_to_snake
from dcrm.utilities.lookup import EMPTY_VALUE_DISPLAY, LookupFields
from dcrm.utilities.serialization import serialize_object

from .base import HtmxResponseMixin

__all__ = [
    "DetailViewMixin",
]

logger = logging.getLogger(__name__)


class DetailViewMixin(HtmxResponseMixin, PermissionRequiredMixin):
    """通用的详情视图 Mixin

    特性:
    1. 支持 fields 和 fieldsets 配置
    2. 支持响应式布局
    3. 支持 GET/POST 请求
    4. 集成 HTMX
    5. 使用 LookupFields 处理字段值
    6. 支持评论功能
    """

    model = None
    fields = []  # 要显示的字段列表
    fieldsets = None  # 字段分组配置
    exclude_fields = [
        "id",
        "level",
        "lft",
        "rght",
        "tree_id",
        "custom_field_data",
        "data_center",
        "ip_addr",
    ]
    enable_related_objects = True  # 是否启用关联对象
    related_fields = {}  # 关联字段配置，格式: {'field_name': ['field1', 'field2']}
    enable_tabs = True
    enable_create_update = True
    enable_comments = True  # 是否启用评论功能
    tabs = None  # 自定义标签页配置
    exclude_tabs = []  # 要排除的关联对象
    extra_tabs = []  # 要额外添加的关联对象

    def get_permission_required(self) -> tuple[Never]:
        codename = get_permission_codename("view", self.opts)
        self.permission_required = f"{self.opts.app_label}.{codename}"
        return super().get_permission_required()

    def get_queryset(self) -> Any:
        select_related: list[str] = [
            f.name for f in self.opts.fields if f.is_relation and f.many_to_one
        ]
        prefetch_related: list[str] = [f.name for f in self.opts.local_many_to_many]
        defer_fields: list[str] = [
            f"{f.name}__{field}"
            for f in self.opts.fields
            if f.is_relation and f.many_to_one
            for field in [
                "created_by",
                "updated_by",
                "data_center",
                "custom_field_data",
                "updated_at",
                "created_at",
            ]
            if hasattr(f.related_model, field)
        ]
        if select_related:
            queryset = self.model._default_manager.all().select_related(*select_related)
        if prefetch_related:
            queryset = queryset.prefetch_related(*prefetch_related)
        return queryset.defer(*defer_fields)

    def get(self, request, *args, **kwargs) -> HttpResponseRedirect | Any:
        self.object = self.get_object()
        # 检查权限
        list_url = self.object.get_list_url()
        if not self.request.user.is_superuser:
            verify = []
            if hasattr(self.object, "shared") and self.object.shared:
                verify.append(self.object.shared)
            else:
                if hasattr(self.object, "data_center"):
                    verify.append(
                        self.object.data_center == self.request.user.data_center
                    )
            if not all(verify):
                messages.add_message(
                    self.request, messages.WARNING, _("您无权访问该对象，请联系管理员")
                )
                return HttpResponseRedirect(list_url)
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def post(
        self, request, *args, **kwargs
    ) -> HttpResponse | Any | HttpResponseRedirect:
        """处理POST请求，主要用于评论提交"""
        self.object = self.get_object()

        # 如果是评论提交
        if "comment_content" in request.POST and self.enable_comments:
            return self.handle_comment_submission(request)

        # 其他POST处理逻辑可以在这里扩展
        return self.get(request, *args, **kwargs)

    def handle_comment_submission(self, request) -> HttpResponse | Any:
        """处理评论提交"""
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.data_center = request.user.data_center
            comment.content_type = ContentType.objects.get_for_model(self.object)
            comment.object_id = self.object.pk
            comment.created_by = request.user
            comment.save()

            # 记录操作日志
            LogEntry.objects.log_action(
                user=request.user,
                action=ChangeActionChoices.CREATE,
                object_repr=self.object,
                message=_("{} 添加了评论: {}").format(
                    request.user.username,
                    (
                        comment.content[:50] + "..."
                        if len(comment.content) > 50
                        else comment.content
                    ),
                ),
                action_type="add_comment",
                postchange_data=serialize_object(comment),
                extra_data={
                    "ipaddr": getattr(request, "ipaddr", "") or "",
                    "user_agent": request.META.get("HTTP_USER_AGENT", ""),
                },
            )

            messages.success(request, _("评论已添加"))

            # 如果是HTMX请求，返回部分更新
            if request.htmx:
                # 清空表单内容
                form = CommentForm()  # 创建一个新的空表单
                context = {
                    "comments": self.get_comments(),
                    "comment_form": form,
                    "enable_comments": self.enable_comments,
                }
                from django.http import HttpResponse
                from django.template.loader import render_to_string

                html = render_to_string(
                    "_includes/comments_list.html", context, request=request
                )
                return HttpResponse(html)
        else:
            messages.error(request, _("评论提交失败，请检查输入内容"))

        # 返回完整页面
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    @cached_property
    def lookup_fields(self) -> LookupFields:
        """获取字段查找工具实例"""
        return LookupFields(
            self.model, self.get_fields(), self.custom_fields, EMPTY_VALUE_DISPLAY
        )

    @cached_property
    def custom_fields(self) -> Any:
        """获取当前对象类型的自定义字段"""
        content_type = ContentType.objects.get_for_model(self.model)
        return CustomField.objects.filter(
            data_center=self.request.user.data_center,
            object_types=content_type,
            ui_visible__in=[
                CustomFieldVisibilityChoices.ONLY_DETAIL,
                CustomFieldVisibilityChoices.LIST_AND_DETAIL,
            ],
        )

    def get_fields(self) -> list[str]:
        """获取要显示的字段列表"""
        if self.fields == "__all__":
            # 获取所有字段，包括多对多字段
            fields = [
                f.name
                for f in self.model._meta.get_fields()
                if not any([f.one_to_many, f.auto_created])  # 只排除反向关系字段
            ]
        else:
            fields = self.fields

        # 处理关联字段
        expanded_fields = []
        for field in fields:
            expanded_fields.append(field)
            # 如果字段在 related_fields 中配置了要显示的字段
            if field in self.related_fields:
                # 添加关联字段，格式为: field__related_field
                expanded_fields.extend(
                    [
                        f"{field}__{related_field}"
                        for related_field in self.related_fields[field]
                    ]
                )
        # 添加自定义字段
        custom_fields = [f.name for f in self.custom_fields]
        expanded_fields.extend(custom_fields)

        # 排除不需要的字段
        return [f for f in expanded_fields if f not in self.exclude_fields]

    def get_field_label(self, field_name: str) -> str:
        """获取字段标签"""
        # 优先处理自定义字段
        if field_name in [f.name for f in self.custom_fields]:
            custom_field = next(f for f in self.custom_fields if f.name == field_name)
            return custom_field.label
        return self.lookup_fields.get_field_label(field_name)

    def get_field_value(self, obj: models.Model, field_name: str) -> str:
        """获取字段值"""
        # 优先处理自定义字段
        if field_name in [f.name for f in self.custom_fields]:
            custom_field = next(f for f in self.custom_fields if f.name == field_name)
            return self.render_custom_field_value(
                custom_field, obj.get_custom_field_display(field_name, custom_field)
            )

        return self.lookup_fields.get_field_value(obj, field_name)

    def get_smart_fieldsets(self) -> list[dict[str, Any]]:
        """智能分析字段并分组"""
        fields = self.get_fields()

        # 初始化字段组
        required_fields = []
        optional_fields = []
        m2m_fields = {}  # 使用字典存储多对多字段及其分组
        custom_fields = []
        system_fields = []

        # 初始化关联字段处理器
        related_lookups = {}
        for field_name, related_fields in self.related_fields.items():
            try:
                # 获取关联字段对应的模型类
                field = self.model._meta.get_field(field_name)
                if field.is_relation:
                    related_model = field.remote_field.model
                    # 为关联模型创建 LookupFields 实例
                    related_lookups[field_name] = LookupFields(
                        related_model, related_fields, EMPTY_VALUE_DISPLAY
                    )
            except Exception as e:
                logger.warning(f"处理关联字段 {field_name} 时出错: {str(e)}")

        system_patterns = [
            "created",
            "updated",
            "creator",
            "modifier",
            "deleted",
            "is_",
            "has_",
        ]

        for field_name in fields:
            # 处理自定义字段
            if field_name in [f.name for f in self.custom_fields]:
                custom_fields.append(field_name)
                continue

            # 跳过关联字段的扩展字段
            if "__" in field_name:
                continue

            try:
                # 使用 lookup_fields 获取字段信息
                field = self.lookup_fields.model._meta.get_field(field_name)
                is_system = any(pattern in field_name for pattern in system_patterns)

                if isinstance(field, models.ManyToManyField):
                    # 获取多对多字段的相关模型名称作为分组
                    related_model = field.remote_field.model
                    group_name = related_model._meta.verbose_name_plural
                    if group_name not in m2m_fields:
                        m2m_fields[group_name] = []
                    m2m_fields[group_name].append(field_name)
                elif is_system:
                    system_fields.append(field_name)
                elif (
                    hasattr(field, "blank")
                    and field.blank
                    and not field.null
                    and not field.has_default()
                ):
                    optional_fields.append(field_name)
                else:
                    required_fields.append(field_name)
            except Exception:
                required_fields.append(field_name)

        def sort_fields(field_list) -> list:
            """按字段类型排序"""

            def get_field_priority(field_name) -> Literal[0, 1, 2, 3]:
                try:
                    field = self.model._meta.get_field(field_name.split("__")[0])
                    if isinstance(field, models.CharField):
                        return 0
                    elif isinstance(field, models.ForeignKey):
                        return 1
                    return 2
                except Exception:
                    return 3

            return sorted(field_list, key=get_field_priority)

        fieldsets = []

        # 构建基本字段集
        field_groups = [
            (_("基本信息"), required_fields),
            (_("其他信息"), optional_fields),
            (_("自定义字段"), custom_fields),
            # (_("系统信息"), system_fields)
        ]

        # 添加基本字段集
        for title, field_list in field_groups:
            if not field_list:
                continue

            fields = []
            for field_name in sort_fields(field_list):
                fields.append(
                    {
                        "name": field_name,
                        "label": self.get_field_label(field_name),
                        "value": self.get_field_value(self.object, field_name),
                    }
                )
            fieldsets.append({"title": title, "fields": fields})

        # 添加多对多字段集
        for group_name, field_list in m2m_fields.items():
            if not field_list:
                continue

            fields = []
            for field_name in sort_fields(field_list):
                fields.append(
                    {
                        "name": field_name,
                        "label": self.get_field_label(field_name),
                        "value": self.get_field_value(self.object, field_name),
                    }
                )
            fieldsets.append(
                {
                    "title": group_name,
                    "fields": fields,
                    "is_m2m": True,  # 标记为多对多字段组
                }
            )

        # 添加关联字段集
        for field_name, lookup in related_lookups.items():
            try:
                # 获取关联对象
                related_obj = getattr(self.object, field_name)
                if not related_obj:
                    continue

                # 获取关联字段的 verbose_name 作为标题
                field = self.model._meta.get_field(field_name)
                title = field.verbose_name

                # 使用关联字段的 LookupFields 处理字段
                fields = []
                for related_field in lookup.fields:
                    fields.append(
                        {
                            "name": f"{field_name}__{related_field}",
                            "label": lookup.get_field_label(related_field),
                            "value": lookup.get_field_value(related_obj, related_field),
                        }
                    )

                fieldsets.append({"title": title, "fields": fields})
            except Exception as e:
                logger.warning(f"处理关联字段集 {field_name} 时出错: {str(e)}")

        return fieldsets

    def get_fieldsets(self) -> list[dict[str, Any]]:
        """获取字段集配置"""
        if self.fieldsets is not None:
            # 处理自定义fieldsets配置
            fieldsets = []
            for fieldset in self.fieldsets:
                fields = []
                for field_name in fieldset["fields"]:
                    fields.append(
                        {
                            "name": field_name,
                            "label": self.get_field_label(field_name),
                            "value": self.get_field_value(self.object, field_name),
                        }
                    )
                fieldsets.append({"title": fieldset["title"], "fields": fields})
            if self.custom_fields:
                fieldsets.insert(
                    -1,
                    {
                        "title": _("自定义字段"),
                        "fields": [
                            {
                                "name": field.name,
                                "label": field.label,
                                "value": self.object.get_custom_field_display(
                                    field.name, field
                                ),
                            }
                            for field in self.custom_fields
                        ],
                    },
                )
            return fieldsets
        return self.get_smart_fieldsets()

    def get_comments(self):
        """获取对象的评论列表"""
        if not self.enable_comments:
            return Comment.objects.none()

        content_type = ContentType.objects.get_for_model(self.object)
        return (
            Comment.objects.filter(
                data_center=self.request.user.data_center,
                content_type=content_type,
                object_id=self.object.pk,
            )
            .select_related("created_by")
            .order_by("-created_at")
        )

    def get_comment_form(self):
        """获取评论表单"""
        if not self.enable_comments:
            return None
        return CommentForm()

    def render_custom_field_value(self, field: CustomField, value: Any) -> str:
        """渲染自定义字段值

        Args:
            field: 自定义字段实例
            value: 字段值

        Returns:
            格式化后的HTML字符串

        """
        if value is None:
            return EMPTY_VALUE_DISPLAY

        if field.type == "boolean":
            return format_html(
                '<i class="fa fa-{} text-{}"></i>',
                "check-circle" if value else "times-circle",
                "success" if value else "danger",
            )
        elif field.type == "choice":
            return format_html('<span class="label label-default">{}</span>', value)
        elif field.type == "url":
            return format_html('<a href="{}" target="_blank">{}</a>', value, value)
        elif field.type == "email":
            return format_html('<a href="mailto:{}">{}</a>', value, value)
        else:
            return str(value)

    def get_related_objects(self):
        """获取对象的所有关联对象配置"""
        if self.tabs is not None:
            return self.tabs

        related_objects = []

        # 获取所有关联字段
        for field in self.model._meta.get_fields():
            # 跳过排除的关联对象
            if field.name in self.exclude_tabs:
                continue

            if isinstance(field, (ForeignKey, ManyToManyField, OneToOneField)):
                continue  # 跳过外键字段，因为它们指向其他对象

            # 处理反向关系
            if field.auto_created and field.is_relation:
                related_model = field.related_model
                if related_model is DataCenter or related_model is DataCenterGroup:
                    continue
                # 获取关联模型的列表视图URL
                try:
                    model_name = camel_to_snake(related_model._meta.object_name)
                    url_name = f"{model_name}_list"
                    list_url = reverse(url_name)

                    related_objects.append(
                        {
                            "name": field.name,
                            "model": related_model,
                            "verbose_name": field.related_model._meta.verbose_name_plural,
                            "url": list_url,
                            "filter_field": field.field.name,  # 用于过滤的字段名
                        }
                    )
                except Exception as e:
                    logger.warning(f"无法获取 {related_model} 的列表URL: {str(e)}")

        return related_objects

    def get_context_data(self, **kwargs):
        """扩展上下文数据，添加标签页信息"""
        context = super().get_context_data(**kwargs)
        context["fieldsets"] = self.get_fieldsets()
        if self.enable_related_objects:
            # 获取关联对象配置
            related_objects = self.get_related_objects()

            # 构建标签页数据
            tabs = []
            for related in related_objects:
                # 获取关联对象的数量
                related_model = related["model"]
                filter_kwargs = {related["filter_field"]: self.object}
                if hasattr(related_model, "data_center"):
                    filter_kwargs.update(
                        {"data_center_id": self.request.user.data_center_id}
                    )
                count = related_model.objects.filter(**filter_kwargs).count()
                url = f"{related['url']}?{related['filter_field']}={self.object.pk}"
                if count > 0:
                    tabs.append(
                        {
                            "title": related["verbose_name"],
                            "url": f"{url}&next_url={self.object.get_absolute_url()}",
                            "count": count,
                            "icon": (
                                related_model._icon
                                if hasattr(related_model, "_icon")
                                else "fa fa-list"
                            ),
                        }
                    )
            context["tabs"] = tabs
            context["col_width"] = 2
        context["enable_tabs"] = self.enable_tabs
        context["enable_create_update"] = self.enable_create_update

        # 添加评论相关上下文
        if self.enable_comments:
            context["enable_comments"] = True
            context["comments"] = self.get_comments()
            context["comment_form"] = self.get_comment_form()
        else:
            context["enable_comments"] = False

        return context

    def get_template_names(self):
        """获取模板名称

        模板查找顺序：
        1. app_label/model_name/detail.html
        2. model_name/detail.html
        3. base/detail.html
        """
        if self.template_name:
            return self.template_name
        model_name = camel_to_snake(self.model._meta.object_name)
        return [f"{model_name}/detail.html", "detail.html"]
