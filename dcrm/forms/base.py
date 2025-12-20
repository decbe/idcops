from django import forms
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import models
from django.utils import timezone
from django.utils.html import format_html, mark_safe

from .fields import CustomFieldFormField
from .mixins import AutoSequenceMixin


class BaseModelFormMixin(forms.ModelForm):
    """ModelForm基类"""

    # 依赖 self.data_center 的模型需要注意 MRO 引用顺序。
    def __init__(self, *args, **kwargs):
        request = kwargs.pop("request", None)
        htmx_configs = kwargs.get("htmx_configs", {})
        super().__init__(*args, **kwargs)
        self.request = request
        self.data_center = None
        self.preferences = request.user.get_all_configs()
        if self.request and hasattr(self.request.user, "data_center"):
            self.data_center = self.request.user.data_center
        for field_name, field in self.fields.items():
            if not hasattr(self.Meta.model, field_name):
                continue
            if hasattr(field, "queryset"):
                default_filter = models.Q()
                if hasattr(field.queryset.model, "data_center"):
                    default_filter |= models.Q(data_center=self.data_center)
                if hasattr(field.queryset.model, "shared"):
                    default_filter |= models.Q(shared=True)
                field.queryset = field.queryset.filter(default_filter)
            if field.required:
                field.label = format_html(
                    '{}<span class="text-red" style="margin-left: 5px;">*</span>',
                    field.label or field_name.title(),
                )
            if self.request and not self.preferences.get("SIMPLE_FORM_MODE", False):
                field.widget.attrs.update({"placeholder": field.help_text})
            if isinstance(field.widget, forms.widgets.Textarea):
                field.widget.attrs.update({"placeholder": field.help_text, "rows": "3"})

            field.widget.attrs.update({"class": "form-control", "autocomplete": "off"})
            if isinstance(
                field.widget, (forms.widgets.Select, forms.widgets.SelectMultiple)
            ):
                field.widget.attrs.update(
                    {
                        "class": "form-control select",
                        "style": "width: 100%",
                        "data-width": "100%",
                    }
                )
            if isinstance(field, forms.fields.DateTimeField):
                current_attrs = self.fields[field_name].widget.attrs.copy()
                current_attrs.update(
                    {"data-datetime": "true", "type": "datetime-local"}
                )
                self.fields[field_name].widget = forms.DateTimeInput(
                    attrs=current_attrs, format="%Y-%m-%dT%H:%M"
                )
                # 如果字段是必填的，初始化为当前日期时间
                if field.required and not self.initial.get(field_name):
                    self.initial[field_name] = timezone.now()
            if isinstance(field, forms.fields.DateField):
                current_attrs = self.fields[field_name].widget.attrs.copy()
                current_attrs.update({"data-date": "true", "type": "date"})
                self.fields[field_name].widget = forms.DateInput(
                    attrs=current_attrs, format="%Y-%m-%d"
                )
            if isinstance(field, forms.fields.BooleanField):
                self.fields[field_name].widget.attrs.update(
                    {"data-boolean": "true", "class": "checkbox"}
                )
                self.fields[field_name].label = mark_safe(f"<b>{field.help_text}</b>")
            if field_name in htmx_configs:
                self.fields[field_name].widget.attrs.update(htmx_configs[field_name])

    def clean(self):
        # 1. 依赖 self.data_center 的模型需要注意 MRO 引用顺序。
        cleaned_data = super().clean()
        if (
            self.data_center
            and not cleaned_data.get("data_center")
            and self.instance.pk is None
        ):
            self.instance.data_center = self.data_center
            cleaned_data["data_center"] = self.data_center
        # 2. 处理模型的clean验证
        # TODO: 内联表单的clean验证需要额外处理。
        from dcrm.models.inventory import InventoryItem, ItemInstance
        from dcrm.models.patchcords import PatchCord, PatchCordNode
        from dcrm.models.users import User

        if self.Meta.model in [
            PatchCord,
            PatchCordNode,
            User,
            InventoryItem,
            ItemInstance,
        ]:
            return cleaned_data
        if self.instance and self.instance.pk is not None:
            return cleaned_data
        try:
            # 创建一个模型实例用于验证
            instance = self.instance or self._meta.model()
            # 更新实例的字段值，排除多对多字段
            instance.data_center = self.data_center
            opts = self._meta.model._meta
            for field, value in cleaned_data.items():
                try:
                    field_obj = opts.get_field(field)
                    if not field_obj.many_to_many:
                        setattr(instance, field, value)
                except FieldDoesNotExist:
                    # TODO: 需要进一步验证自定义字段
                    # self.add_error(None, f"无效字段：{field}")
                    continue
            # 调用模型的clean方法
            instance.full_clean()
        except ValidationError as e:
            self.add_error(None, str(e.messages))
        return cleaned_data


class BulkModelFormMixin(forms.ModelForm):
    """批量创建和更新表单的Mixin"""

    # 依赖 self.data_center 的模型需要注意 MRO 引用顺序。
    def __init__(self, *args, **kwargs):
        request = kwargs.pop("request", None)
        htmx_configs = kwargs.get("htmx_configs", {})
        super().__init__(*args, **kwargs)
        self.request = request
        self.data_center = None
        if self.request and hasattr(self.request.user, "data_center"):
            self.data_center = self.request.user.data_center
        for field_name, field in self.fields.items():
            if not hasattr(self.Meta.model, field_name):
                continue
            if hasattr(field, "queryset"):
                default_filter = models.Q()
                if hasattr(field.queryset.model, "data_center"):
                    default_filter |= models.Q(data_center=self.data_center)
                if hasattr(field.queryset.model, "shared"):
                    default_filter |= models.Q(shared=True)
                field.queryset = field.queryset.filter(default_filter)
            if field.required:
                field.label = format_html(
                    '{}<span class="text-red" style="margin-left: 5px;">*</span>',
                    field.label or field_name.title(),
                )
            if self.request and not getattr(self.request.user, "form_help_mode", False):
                field.widget.attrs.update({"placeholder": field.help_text})
            field.widget.attrs.update({"class": "form-control", "autocomplete": "off"})
            if isinstance(
                field.widget, (forms.widgets.Select, forms.widgets.SelectMultiple)
            ):
                field.widget.attrs.update(
                    {
                        "class": "form-control select2",
                        "style": "width: 100%",
                        "data-width": "100%",
                    }
                )
            if isinstance(field, forms.fields.DateTimeField):
                current_attrs = self.fields[field_name].widget.attrs.copy()
                current_attrs.update(
                    {"data-datetime": "true", "type": "datetime-local"}
                )
                self.fields[field_name].widget = forms.DateTimeInput(
                    attrs=current_attrs, format="%Y-%m-%dT%H:%M"
                )
                # 如果字段是必填的，初始化为当前日期时间
                if field.required and not self.initial.get(field_name):
                    self.initial[field_name] = timezone.now()
            if isinstance(field, forms.fields.DateField):
                current_attrs = self.fields[field_name].widget.attrs.copy()
                current_attrs.update({"data-date": "true", "type": "date"})
                self.fields[field_name].widget = forms.DateInput(
                    attrs=current_attrs, format="%Y-%m-%d"
                )
            if isinstance(field, forms.fields.BooleanField):
                self.fields[field_name].widget.attrs.update(
                    {"data-boolean": "true", "class": "checkbox"}
                )
            if isinstance(field.widget, forms.widgets.Textarea):
                self.fields[field_name].widget.attrs.update({"rows": "5"})
            if field_name in htmx_configs:
                self.fields[field_name].widget.attrs.update(htmx_configs[field_name])

    def clean(self):
        # 1. 依赖 self.data_center 的模型需要注意 MRO 引用顺序。
        cleaned_data = super().clean()
        if (
            self.data_center
            and not cleaned_data.get("data_center")
            and self.instance.pk is None
        ):
            self.instance.data_center = self.data_center
            cleaned_data["data_center"] = self.data_center
        # 2. 处理模型的clean验证
        # TODO: 内联表单的clean验证需要额外处理。
        from dcrm.models.patchcords import PatchCord, PatchCordNode

        if self.Meta.model in [PatchCord, PatchCordNode]:
            return cleaned_data
        if self.instance and self.instance.pk is not None:
            return cleaned_data
        try:
            # 创建一个模型实例用于验证
            instance = self.instance or self._meta.model()
            # 更新实例的字段值，排除多对多字段
            instance.data_center = self.data_center
            opts = self._meta.model._meta
            for field, value in cleaned_data.items():
                try:
                    field_obj = opts.get_field(field)
                    if not field_obj.many_to_many:
                        setattr(instance, field, value)
                except FieldDoesNotExist:
                    # TODO: 需要进一步验证自定义字段
                    # self.add_error(None, f"无效字段：{field}")
                    continue
            # 调用模型的clean方法
            instance.full_clean()
        except ValidationError as e:
            self.add_error(None, str(e.messages))
        return cleaned_data


class BaseModelWithAutoSequenceMixin(AutoSequenceMixin, BaseModelFormMixin):
    """支持自动设置序号的Model基类"""


class CustomFieldsModelForm(forms.ModelForm):
    """支持自定义字段的ModelForm"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_custom_fields()

    def setup_custom_fields(self):
        """设置自定义字段"""
        custom_fields = self._meta.model.get_custom_fields()

        for field in custom_fields:
            field_name = f"custom_{field.name}"
            self.fields[field_name] = CustomFieldFormField(field)

            # 设置初始值
            if self.instance and self.instance.pk:
                self.initial[field_name] = self.instance.get_custom_field_value(
                    field.name
                )

    def save(self, commit=True):
        """保存表单时处理自定义字段"""
        instance = super().save(commit=False)

        custom_fields = self._meta.model.get_custom_fields()
        for field in custom_fields:
            field_name = f"custom_{field.name}"
            if field_name in self.cleaned_data:
                instance.set_custom_field_value(
                    field.name, self.cleaned_data[field_name], instance.data_center
                )

        if commit:
            instance.save()

        return instance


class ModelFormWithFormset(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        form_kwargs = kwargs.get("form_kwargs", {})
        if form_kwargs:
            form_kwargs["request"] = request
        self.request = request
        self.data_center = None
        if self.request and hasattr(self.request.user, "data_center"):
            self.data_center = self.request.user.data_center
        for field_name, field in self.fields.items():
            if not hasattr(self.Meta.model, field_name):
                continue
            # 处理 查询集类型的字段
            if hasattr(field, "queryset"):
                default_filter = models.Q()
                if hasattr(field.queryset.model, "data_center"):
                    default_filter |= models.Q(data_center=self.data_center)
                if hasattr(field.queryset.model, "shared"):
                    default_filter |= models.Q(shared=True)
                field.queryset = field.queryset.filter(default_filter)
            # 重新处理 required

            if field.required:
                field.label = format_html(
                    '{}<span class="text-red" style="margin-left: 5px;">*</span>',
                    field.label or field_name.title(),
                )
            if self.request and getattr(self.request.user, "form_help_mode", False):
                field.widget.attrs.update({"placeholder": field.help_text})
            field.widget.attrs.update({"class": "form-control", "autocomplete": "off"})
            if isinstance(
                field.widget, (forms.widgets.Select, forms.widgets.SelectMultiple)
            ):
                field.widget.attrs.update(
                    {
                        "class": "form-control select2",
                        "style": "width: 100%",
                        "data-width": "100%",
                    }
                )
