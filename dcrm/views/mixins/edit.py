import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Never

from django.contrib.auth import get_permission_codename
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.forms import ModelForm, modelform_factory
from django.forms.models import ModelForm, model_to_dict
from django.http.response import HttpResponse
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.timezone import datetime
from django.utils.translation import gettext_lazy as _

from dcrm.forms.base import BaseModelFormMixin as NoneBaseModelFormMixin
from dcrm.forms.base import BulkModelFormMixin
from dcrm.forms.forms import CustomFieldModelForm
from dcrm.forms.mixins import AutoSequenceMixin
from dcrm.models.base import LogEntry
from dcrm.models.choices import ChangeActionChoices
from dcrm.models.codingrule import CodingRule
from dcrm.models.customfields import CustomField
from dcrm.utilities.display import camel_to_snake
from dcrm.utilities.lookup import is_model_field
from dcrm.utilities.serialization import serialize_object

from .base import HtmxResponseMixin

__all__ = (
    "CreateViewMixin",
    "UpdateViewMixin",
    "FieldSet",
    "BaseFormMixin",
)


class BaseModelFormMixin(
    AutoSequenceMixin, CustomFieldModelForm, NoneBaseModelFormMixin
):
    pass


@dataclass
class FieldSet:
    """字段集合"""

    name: str
    fields: list[str]
    classes: str = ""
    description: str = ""
    collapse: bool = False
    col: int = 6
    inline_groups: list[list[str]] = None
    inline_positions: dict[str, int] = None  # 新增：指定每个内联组的位置

    @property
    def field_groups(self) -> list[list[str]]:
        """获取字段分组，将内联字段和普通字段分开处理"""
        if not self.fields:
            return []

        # 初始化结果列表和已使用字段集合
        groups = []
        used_fields = set()

        # 创建字段到位置的映射
        field_positions = {field: idx for idx, field in enumerate(self.fields)}

        if self.inline_groups:
            # 为每个内联组创建位置信息
            group_positions = []
            for group in self.inline_groups:
                # 如果指定了位置，使用指定位置；否则使用组中第一个字段的位置
                if self.inline_positions and ",".join(group) in self.inline_positions:
                    pos = self.inline_positions[",".join(group)]
                else:
                    pos = min(
                        field_positions[field]
                        for field in group
                        if field in field_positions
                    )
                group_positions.append((pos, group))

            # 按位置排序内联组
            group_positions.sort()

            # 处理每个位置的字段
            current_pos = 0
            for pos, group in group_positions:
                # 添加位置之前的单个字段
                while current_pos < pos:
                    if (
                        current_pos < len(self.fields)
                        and self.fields[current_pos] not in used_fields
                    ):
                        groups.append([self.fields[current_pos]])
                        used_fields.add(self.fields[current_pos])
                    current_pos += 1

                # 添加内联组
                if all(field in self.fields for field in group):
                    groups.append(group)
                    used_fields.update(group)
                current_pos = pos + len(group)

        # 处理剩余字段
        for field in self.fields:
            if field not in used_fields:
                groups.append([field])

        return groups


class BaseFormMixin:
    """表单基础 Mixin，为创建和更新视图提供通用功能"""

    form_class: type[ModelForm] | None = None
    template_name_suffix: str = "_form"
    success_message: str = _("保存成功")
    success_url: str = None
    error_message: str = _("保存失败，请检查输入")
    fieldsets: list[FieldSet] | None = None
    htmx_configs: dict[str, dict[str, str]] = None

    def get_htmx_config(self, field_name: str) -> dict:
        """获取字段的HTMX配置
        Args:
            field_name: 字段名
        Returns:
            dict: HTMX配置字典
        """
        config = self.htmx_configs.get(field_name, {}).copy()
        return config

    def get_form_class(self) -> type[ModelForm]:
        """获取表单类"""
        if self.form_class:
            return self.form_class
        if self.model and not self.form_class:
            fields = self.get_form_fields()
            return modelform_factory(
                model=self.model,
                form=BaseModelFormMixin,
                fields=fields,
            )

        raise ImproperlyConfigured(
            "Using BaseFormMixin requires either 'form_class' or 'model'"
        )

    def get_form_kwargs(self) -> Any:
        """获取表单参数"""
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def get_clone_session_key(self) -> str:
        """获取克隆数据的session key"""
        model_name = camel_to_snake(self.model._meta.object_name)
        return f"{self.request.user.id}_clone_{model_name}_initial"

    def clone_object_initial(self, instance) -> dict:
        """克隆对象, 根据模型以及实例返回表单initial字典
        排除在coding_rule指定的自动填充字段
        从模型或视图中获取 clone_fields = []
        :param instance:
        :return: dict
        """
        if hasattr(self, "clone_fields"):
            # 从视图中获取 clone_fields = []
            clone_fields = self.clone_fields
        elif hasattr(instance, "clone_fields"):
            # 从模型中获取 clone_fields = []
            clone_fields = instance.clone_fields
        else:
            clone_fields = []
        coding_rule = (
            CodingRule.objects.get_for_model(self.model, self.request.user.data_center)
            .only("to_field")
            .values_list("to_field", flat=True)
        )
        if coding_rule.exists():
            clone_fields = list(filter(lambda x: x not in coding_rule, clone_fields))
        return model_to_dict(self.object, fields=clone_fields)

    def get_success_url(self) -> str:
        redirect_success = all(
            map(
                lambda x: x not in self.request.POST,
                ["_addanother", "_clone_add", "_saveview", "_return"],
            )
        )
        if self.success_url and redirect_success:
            return self.success_url
        model_name = camel_to_snake(self.model._meta.object_name)
        if "_addanother" in self.request.POST:
            return reverse(f"{model_name}_create")
        if "_clone_add" in self.request.POST:
            # 存储数据到session，包含过期时间
            session_key = self.get_clone_session_key()
            self.request.session[session_key] = {
                "data": json.loads(
                    json.dumps(
                        self.clone_object_initial(self.object), cls=DjangoJSONEncoder
                    )
                ),
                "expires": time.time() + 300,  # 当前时间 + 300秒(5分钟)
            }
            self.request.session.modified = True

            params = self.request.GET.copy()
            url = reverse(f"{model_name}_create") + "?" + params.urlencode()
            return url
        elif "_saveview" in self.request.POST:
            return reverse(f"{model_name}_detail", args=(self.object.pk,))
        elif "_return" in self.request.POST:
            referrer = self.request.META.get("HTTP_REFERER")
            return referrer if referrer else reverse(f"{model_name}_list")
        else:
            return reverse(f"{model_name}_list")

    def get_form_fields(self) -> list[str]:
        """获取表单字段列表"""
        if getattr(self, "form_class", None) is not None:
            return self.form_class.Meta.fields
        if getattr(self, "fields", None) is not None:
            return self.fields
        else:
            # 构建默认字段
            exclude = [
                "id",
                "created_by",
                "updated_by",
                "created_at",
                "updated_at",
                "data_center",
            ]
            fields = []
            for field in self.opts.fields + self.opts.many_to_many:
                field_name = field.name
                if isinstance(field, models.JSONField):
                    continue
                if not field.editable or field_name in exclude:
                    continue
                fields.append(field_name)
            return fields

    def get_smart_fieldsets(self) -> list[FieldSet]:
        """智能分析字段并分组"""
        fields = self.get_form_fields()
        if not fields:
            return []

        required_fields = []
        optional_fields = []
        system_fields = []
        m2m_fields = []
        custom_fields = []

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
            try:
                field = self.model._meta.get_field(field_name)
                is_system = any(pattern in field_name for pattern in system_patterns)

                if isinstance(field, models.ManyToManyField):
                    m2m_fields.append(field_name)
                elif is_system:
                    system_fields.append(field_name)
                elif field.blank and not field.null and not field.has_default():
                    optional_fields.append(field_name)
                else:
                    required_fields.append(field_name)
            except FieldDoesNotExist:
                if field_name.startswith("cf_"):
                    custom_fields.append(field_name)
                else:
                    required_fields.append(field_name)

        def sort_fields(field_list) -> list:
            def get_field_priority(field_name) -> Literal[0, 1, 2, 3]:
                try:
                    field = self.model._meta.get_field(field_name)
                    if isinstance(field, models.CharField):
                        return 0
                    elif isinstance(field, models.ForeignKey):
                        return 1
                    return 2
                except FieldDoesNotExist:
                    return 3

            return sorted(field_list, key=get_field_priority)

        fieldsets = []

        if required_fields:
            fieldsets.append(
                FieldSet(
                    name=_("基本信息"),
                    fields=sort_fields(required_fields),
                    description=_("请填写基本信息"),
                )
            )

        if optional_fields:
            fieldsets.append(
                FieldSet(
                    name=_("选填信息"),
                    fields=sort_fields(optional_fields),
                    description=_("以下信息为选填项"),
                )
            )

        if system_fields:
            fieldsets.append(
                FieldSet(
                    name=_("系统信息"),
                    fields=sort_fields(system_fields),
                    description=_("系统自动维护的信息"),
                )
            )

        if m2m_fields:
            fieldsets.append(
                FieldSet(
                    name=_("关联信息"),
                    fields=sort_fields(m2m_fields),
                    description=_("多对多关联信息"),
                )
            )
        if custom_fields:
            fieldsets.append(
                FieldSet(
                    name=_("自定义字段"),
                    fields=sort_fields(custom_fields),
                    description=_("菜单>自定义>自定义字段"),
                )
            )

        return fieldsets

    def get_fieldsets(self) -> list[FieldSet]:
        """获取字段集配置"""
        if self.fieldsets is not None:
            # 检查是否已经包含自定义字段
            self.fieldsets = list(self.fieldsets)
            has_custom_fields = False
            for fieldset in self.fieldsets:
                if any(field.startswith("cf_") for field in fieldset.fields):
                    has_custom_fields = True
                    break

            # 如果没有自定义字段，添加自定义字段组
            if not has_custom_fields:
                data_center = self.request.user.data_center
                model_custom_fields = CustomField.objects.get_for_model(
                    self.model, data_center
                )
                if model_custom_fields:
                    custom_field_names = [
                        f"cf_{field.name}" for field in model_custom_fields
                    ]
                    self.fieldsets.append(
                        FieldSet(
                            name=_("自定义字段"),
                            fields=custom_field_names,
                            description=_("菜单>自定义>自定义字段"),
                        )
                    )

            return self.fieldsets

        return self.get_smart_fieldsets()

    def form_valid(self, form: ModelForm) -> Any:
        """表单验证成功处理"""
        # Save without committing to handle M2M fields
        self.object = form.save(commit=False)

        # 如果表单中有创建时间，则设置，否则使用当前时间。在Create和Update中都需要
        if form.cleaned_data.get("created_at") is not None:
            created_at = form.cleaned_data["created_at"]
            if isinstance(created_at, date):
                time = datetime.now().time()
                created_at = datetime.combine(created_at, time)
            self.object.created_at = created_at

        # Save the main object
        self.object.save()

        # Now save M2M fields
        form.save_m2m()
        return super().form_valid(form)

    def form_invalid(self, form: ModelForm) -> Any:
        """表单验证失败处理"""
        response = super().form_invalid(form)
        return response

    def get_context_data(self, **kwargs) -> dict:
        """获取上下文数据"""
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "fieldsets": self.get_fieldsets(),
                "original": getattr(self, "object", None),
                "show_delete": self.object is not None,
            }
        )
        return context

    def get_initial(self) -> dict[str, Any]:
        initial = {"data_center_id": self.request.user.data_center_id}
        if self.request.method == "GET":
            initial.update(self.request.GET.dict())
        return initial


class CreateViewMixin(PermissionRequiredMixin, BaseFormMixin, HtmxResponseMixin):
    """创建视图 Mixin"""

    success_message: str = _("创建成功")

    def get_permission_required(self) -> tuple[Never]:
        codename = get_permission_codename("add", self.opts)
        self.permission_required = f"{self.opts.app_label}.{codename}"
        return super().get_permission_required()

    def form_valid(self, form: ModelForm) -> Any:
        """表单验证成功处理"""
        if hasattr(form.instance, "created_by"):
            form.instance.created_by = self.request.user
        if "data_center" not in form.cleaned_data and is_model_field(
            self.model, "data_center"
        ):
            form.instance.data_center = self.request.user.data_center
        extra_data = {
            "ipaddr": self.request.ipaddr,
            "user_agent": self.request.META.get("HTTP_USER_AGENT"),
        }
        response = super().form_valid(form)
        # 记录日志
        LogEntry.objects.log_action(
            user=self.request.user,
            action=ChangeActionChoices.CREATE,
            object_repr=self.object,
            message=f"{self.success_message}: ({str(self.object)})",
            created_at=form.instance.created_at,
            changed=True,
            prechange_data={},
            postchange_data=serialize_object(self.object),
            extra_data=extra_data,
        )
        return response

    def get_initial(self) -> dict[str, Any]:
        initial = super().get_initial()
        # 直接从session获取initial数据
        clone_initial = self.request.session.pop(self.get_clone_session_key(), None)
        if clone_initial and clone_initial.get("data"):
            initial.update(clone_initial.get("data"))
            # 确保session被保存
            self.request.session.modified = True
        return initial

    def form_invalid(self, form) -> Any:
        # 表单验证失败时也清理session
        self.request.session.pop(self.get_clone_session_key(), None)
        self.request.session.modified = True
        return super().form_invalid(form)

    def get_template_names(self) -> list[str]:
        """获取模板名称"""
        if self.template_name:
            return self.template_name
        model_name = self.model._meta.model_name
        if self.request.htmx:
            return [f"{model_name}/form_htmx.html", "form_htmx.html"]
        return [f"{model_name}/form.html", "form.html"]

    def htmx_post(self, request, *args, **kwargs) -> Any:
        """处理 HTMX POST 请求"""
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def htmx_get(self, request, *args, **kwargs) -> HttpResponse:
        """处理 HTMX GET 请求"""
        self.object = None
        context = self.get_context_data()
        content = render_to_string(
            template_name=self.get_template_names(),
            context=context,
            request=self.request,
        )
        return HttpResponse(content)

    def get_context_data(self, **kwargs) -> dict:
        """获取上下文数据"""
        context = super().get_context_data(**kwargs)
        context.update({"is_create": True})
        return context


class UpdateViewMixin(PermissionRequiredMixin, BaseFormMixin, HtmxResponseMixin):
    """更新视图 Mixin"""

    success_message: str = _("更新成功")

    def get_permission_required(self) -> tuple[Never]:
        codename = get_permission_codename("change", self.opts)
        self.permission_required = f"{self.opts.app_label}.{codename}"
        return super().get_permission_required()

    def form_valid(self, form: ModelForm) -> Any:
        """表单验证成功处理"""
        if hasattr(form.instance, "updated_by"):
            form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        extra_data = {
            "ipaddr": self.request.ipaddr,
            "user_agent": self.request.META.get("HTTP_USER_AGENT"),
        }
        LogEntry.objects.log_action(
            user=self.request.user,
            action=ChangeActionChoices.UPDATE,
            object_repr=self.object,
            message=f"{self.success_message}: ({str(self.object)})",
            changed=True,
            action_type="update",
            prechange_data=self.prechange_data,
            postchange_data=serialize_object(self.object),
            extra_data=extra_data,
        )
        return response

    def get_template_names(self) -> list[str]:
        """获取模板名称"""
        if self.template_name:
            return self.template_name
        model_name = self.model._meta.model_name
        if self.request.htmx:
            return [f"{model_name}/form_htmx.html", "form_htmx.html"]
        return [f"{model_name}/form.html", "form.html"]

    def htmx_post(self, request, *args, **kwargs) -> Any:
        """处理 HTMX POST 请求"""
        self.object = self.get_object()
        self.prechange_data = serialize_object(self.object)
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def post(self, request, *args, **kwargs) -> Any:
        self.object = self.get_object()
        self.prechange_data = serialize_object(self.object)
        return super().post(request, *args, **kwargs)

    def htmx_get(self, request, *args, **kwargs) -> HttpResponse:
        """处理 HTMX GET 请求"""
        self.object = self.get_object()
        context = self.get_context_data()
        content = render_to_string(
            template_name=self.get_template_names(),
            context=context,
            request=self.request,
        )
        return HttpResponse(content)


class BulkCreateViewMixin(HtmxResponseMixin):
    """批量创建视图 Mixin"""

    template_name_suffix = "_bulk_form"
    success_message = _("批量创建成功")
    error_message = _("批量创建失败，请检查输入")
    batch_size = 100  # 每批处理的对象数量
    form_class = None
    fields = None

    # 表单集支持参数
    extra = 1  # 额外表单数量
    max_num = 50  # 最大表单数量
    min_num = 1  # 最小表单数量
    validate_min = True  # 是否验证最小数量
    validate_max = True  # 是否验证最大数量
    can_delete = False  # 是否允许删除
    can_order = False  # 是否允许排序

    def get_form_class(self) -> type[ModelForm]:
        """获取表单类，支持多个表单实例"""
        if self.form_class:
            return self.form_class

        if self.model and self.fields:
            return modelform_factory(
                model=self.model, form=BulkModelFormMixin, fields=self.fields
            )

        raise ImproperlyConfigured(
            "Using BulkCreateViewMixin requires either 'form_class' or both 'model' and 'fields'"
        )

    def get_form_kwargs(self) -> Any:
        """获取表单参数"""
        kwargs = super().get_form_kwargs()
        kwargs.update({"request": self.request})
        return kwargs

    def get_dynamic_initial(self, index) -> dict:
        """获取动态初始值
        子类可以重写此方法来提供动态的初始值
        Args:
            index: 表单索引
        Returns:
            dict: 包含初始值的字典
        """
        return {}

    def get_shared_initial(self) -> dict[str, Any]:
        """获取所有表单共享的初始值
        子类可以重写此方法来提供共享的初始值
        Returns:
            dict: 包含共享初始值的字典
        """
        return {"data_center_id": self.request.user.data_center_id}

    def get_sequence_initial(
        self, field_name, start_value, step=1
    ) -> Callable[..., Any | str]:
        """生成序列化的初始值
        Args:
            field_name: 字段名
            start_value: 起始值
            step: 步长
        Returns:
            function: 返回一个函数，该函数接受索引并返回对应的值
        """

        def get_value(index) -> Any | str:
            if isinstance(start_value, int):
                return start_value + (index * step)
            elif isinstance(start_value, str):
                # 处理字符串序列，例如 "DEV001" -> "DEV002"
                prefix = "".join(filter(str.isalpha, start_value))
                num = "".join(filter(str.isdigit, start_value))
                if num:
                    new_num = int(num) + (index * step)
                    return f"{prefix}{new_num:0{len(num)}d}"
            return start_value

        return get_value

    def get_initial(self) -> dict:
        """获取初始值"""
        initial = {}
        # 添加共享的初始值
        initial.update(self.get_shared_initial())

        # 获取当前表单索引
        form_prefix = self.request.POST.get("form_prefix", "")
        if form_prefix.startswith("form-"):
            try:
                index = int(form_prefix.split("-")[1])
                # 添加动态初始值
                initial.update(self.get_dynamic_initial(index))
            except (IndexError, ValueError):
                pass

        return initial

    def get_forms(self) -> list:
        """获取多个表单实例"""
        form_class = self.get_form_class()
        form_count = int(self.request.GET.get("form_count", self.extra))

        # 验证表单数量
        if self.validate_min and form_count < self.min_num:
            form_count = self.min_num
        if self.validate_max and form_count > self.max_num:
            form_count = self.max_num

        forms = []

        for i in range(form_count):
            form_prefix = f"form-{i}"
            form_kwargs = self.get_form_kwargs()

            if self.request.method == "POST":
                form_data = {
                    k.replace(form_prefix + "-", ""): v
                    for k, v in self.request.POST.items()
                    if k.startswith(form_prefix + "-")
                }
                form_kwargs["data"] = form_data
                form_kwargs["files"] = self.request.FILES
            else:
                # 为每个表单获取独立的初始值
                initial = self.get_initial()
                initial.update(self.get_dynamic_initial(i))
                form_kwargs["initial"] = initial

            form_kwargs["prefix"] = form_prefix
            forms.append(form_class(**form_kwargs))

        return forms

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        """获取上下文数据"""
        context = kwargs
        if "forms" not in kwargs:
            context["forms"] = self.get_forms()
        context.update(
            {
                "is_bulk_create": True,
                "opts": self.model._meta,
                "extra": self.extra,
                "min_num": self.min_num,
                "max_num": self.max_num,
                "can_delete": self.can_delete,
                "can_order": self.can_order,
            }
        )
        return context

    def forms_valid(self, forms) -> Any:
        """所有表单验证成功的处理"""
        objects = []
        for form in forms:
            instance = form.save(commit=False)
            if hasattr(instance, "created_by"):
                instance.created_by = self.request.user
            if hasattr(instance, "data_center") and not instance.data_center:
                instance.data_center = self.request.user.data_center
            objects.append(instance)

        # 批量创建对象
        created_objects = []
        for i in range(0, len(objects), self.batch_size):
            batch = objects[i : i + self.batch_size]
            created_batch = self.model.objects.bulk_create(batch)
            created_objects.extend(created_batch)

        # 记录批量操作日志
        LogEntry.objects.log_action(
            user=self.request.user,
            action=ChangeActionChoices.BULK_CREATE,
            object_repr=f"批量创建 {len(created_objects)} 个 {self.model._meta.verbose_name}",
            message=self.success_message,
            changed=True,
            prechange_data={},
            postchange_data={"created_count": len(created_objects)},
        )

        return self.get_success_url()

    def forms_invalid(self, forms) -> Any:
        """任一表单验证失败的处理"""
        context = self.get_context_data(forms=forms)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs) -> Any:
        """处理 POST 请求"""
        forms = self.get_forms()
        if all(form.is_valid() for form in forms):
            return self.forms_valid(forms)
        return self.forms_invalid(forms)

    def get_template_names(self) -> list[str]:
        """获取模板名称"""
        if self.template_name:
            return [self.template_name]

        model_name = self.model._meta.model_name

        if self.request.htmx:
            return [f"{model_name}/bulk_form_htmx.html", "bulk_form_htmx.html"]

        return [f"{model_name}/bulk_form.html", "bulk_form.html"]

    def htmx_get(self, request, *args, **kwargs) -> HttpResponse:
        """处理 HTMX GET 请求"""
        context = self.get_context_data()
        content = render_to_string(
            template_name=self.get_template_names(),
            context=context,
            request=self.request,
        )
        return HttpResponse(content)

    def htmx_post(self, request, *args, **kwargs) -> HttpResponse:
        """处理 HTMX POST 请求"""
        forms = self.get_forms()
        if all(form.is_valid() for form in forms):
            response = self.forms_valid(forms)
            return HttpResponse(
                json.dumps(
                    {"message": self.success_message, "redirect_url": str(response)}
                ),
                content_type="application/json",
            )
        else:
            context = self.get_context_data(forms=forms)
            content = render_to_string(
                template_name=self.get_template_names(),
                context=context,
                request=self.request,
            )
            return HttpResponse(content, status=400)


class BulkUpdateViewMixin(HtmxResponseMixin):
    """批量更新视图 Mixin"""

    template_name_suffix = "_bulk_form"
    success_message = _("批量更新成功")
    error_message = _("批量更新失败，请检查输入")
    batch_size = 100
    form_class = None
    fields = None

    def get_form_class(self) -> type[ModelForm]:
        """获取表单类"""
        if self.form_class:
            return self.form_class

        if self.model and self.fields:
            return modelform_factory(model=self.model, fields=self.fields)

        raise ImproperlyConfigured(
            "Using BulkUpdateViewMixin requires either 'form_class' or both 'model' and 'fields'"
        )

    def get_form_kwargs(self) -> dict[str, Any]:
        """获取表单参数"""
        kwargs = {
            "request": self.request,
            "user": self.request.user,
            "data_center": self.request.user.data_center,
        }
        return kwargs

    def get_objects(self) -> list:
        """获取要批量更新的对象"""
        if not hasattr(self, "_objects"):
            ids = self.request.GET.getlist("ids") or self.request.POST.getlist("ids")
            self._objects = list(self.model.objects.filter(pk__in=ids))
        return self._objects

    def get_forms(self) -> list:
        """获取多个表单实例"""
        form_class = self.get_form_class()
        objects = self.get_objects()
        forms = []

        for i, obj in enumerate(objects):
            form_prefix = f"form-{i}"
            form_kwargs = self.get_form_kwargs()
            form_kwargs["instance"] = obj

            if self.request.method == "POST":
                form_data = {
                    k.replace(form_prefix + "-", ""): v
                    for k, v in self.request.POST.items()
                    if k.startswith(form_prefix + "-")
                }
                form_kwargs["data"] = form_data
                form_kwargs["files"] = self.request.FILES

            form_kwargs["prefix"] = form_prefix
            forms.append(form_class(**form_kwargs))

        return forms

    def forms_valid(self, forms) -> Any:
        """所有表单验证成功的处理"""
        objects = []
        prechange_data = {}

        for i, form in enumerate(forms):
            instance = form.save(commit=False)
            if hasattr(instance, "updated_by"):
                instance.updated_by = self.request.user
            prechange_data[str(instance.pk)] = serialize_object(self.get_objects()[i])
            objects.append(instance)

        # 批量更新对象
        updated_objects = []
        for i in range(0, len(objects), self.batch_size):
            batch = objects[i : i + self.batch_size]
            for obj in batch:
                obj.save()
            updated_objects.extend(batch)

        # 记录批量操作日志
        LogEntry.objects.log_action(
            user=self.request.user,
            action=ChangeActionChoices.BULK_UPDATE,
            object_repr=f"批量更新 {len(updated_objects)} 个 {self.model._meta.verbose_name}",
            message=self.success_message,
            changed=True,
            prechange_data=prechange_data,
            postchange_data={"updated_count": len(updated_objects)},
        )

        return self.get_success_url()

    def forms_invalid(self, forms) -> Any:
        """任一表单验证失败的处理"""
        context = self.get_context_data(forms=forms)
        return self.render_to_response(context)

    def post(self, request, *args, **kwargs) -> Any:
        """处理 POST 请求"""
        forms = self.get_forms()
        if all(form.is_valid() for form in forms):
            return self.forms_valid(forms)
        return self.forms_invalid(forms)

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        """获取上下文数据"""
        context = kwargs
        if "forms" not in kwargs:
            context["forms"] = self.get_forms()
        context["is_bulk_update"] = True
        context["objects"] = self.get_objects()
        context["opts"] = self.model._meta
        return context

    def get_template_names(self) -> list[str]:
        """获取模板名称"""
        if self.template_name:
            return [self.template_name]

        model_name = self.model._meta.model_name

        if self.request.htmx:
            return [f"{model_name}/bulk_form_htmx.html", "bulk_form_htmx.html"]

        return [f"{model_name}/bulk_form.html", "bulk_form.html"]

    def htmx_get(self, request, *args, **kwargs) -> HttpResponse:
        """处理 HTMX GET 请求"""
        context = self.get_context_data()
        content = render_to_string(
            template_name=self.get_template_names(),
            context=context,
            request=self.request,
        )
        return HttpResponse(content)

    def htmx_post(self, request, *args, **kwargs) -> HttpResponse:
        """处理 HTMX POST 请求"""
        forms = self.get_forms()
        if all(form.is_valid() for form in forms):
            response = self.forms_valid(forms)
            return HttpResponse(
                json.dumps(
                    {"message": self.success_message, "redirect_url": str(response)}
                ),
                content_type="application/json",
            )
        else:
            context = self.get_context_data(forms=forms)
            content = render_to_string(
                template_name=self.get_template_names(),
                context=context,
                request=self.request,
            )
            return HttpResponse(content, status=400)
