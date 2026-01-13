from django import forms
from django.forms.models import BaseInlineFormSet, inlineformset_factory

from dcrm.models.codingrule import CodingRule
from dcrm.models.customfields import CustomField

from .fields import CustomFieldFormField


class CustomFieldsFormMixin:
    """处理自定义字段的表单混入类"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._add_custom_fields()

    def _add_custom_fields(self):
        """添加自定义字段到表单"""
        if hasattr(self.Meta.model, "custom_fields"):
            instance = getattr(self, "instance", None)

            custom_fields = CustomField.objects.get_for_model(
                self.Meta.model, self.data_center
            )
            for custom_field in custom_fields:
                field_name = f"custom_field_{custom_field.name}"

                # 创建表单字段
                form_field = CustomFieldFormField(custom_field)
                self.fields[field_name] = form_field

                # 设置初始值
                if instance and instance.pk:
                    self.initial[field_name] = instance.get_custom_field_value(
                        custom_field.name
                    )

    def save(self, commit=True):
        """保存自定义字段的值"""
        instance = super().save(commit=False)

        if hasattr(instance, "custom_fields"):
            for custom_field in instance.custom_fields.all():
                field_name = f"custom_field_{custom_field.name}"
                if field_name in self.cleaned_data:
                    instance.set_custom_field_value(
                        custom_field.name,
                        self.cleaned_data[field_name],
                        instance.data_center,
                    )

        if commit:
            instance.save()
        return instance


class AutoSequenceMixin:
    """自动设置序号Mixin"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        enable_auto_sequence = getattr(self.data_center, "auto_sequence", True)
        if not enable_auto_sequence or self.instance.pk:
            return
        rules = CodingRule.objects.get_for_model(self._meta.model, self.data_center)
        if not rules.exists():
            return
        for rule in rules:
            initial_value = rule.get_available_codes(1)[0]
            if initial_value and isinstance(initial_value, str):
                self.initial[rule.to_field] = initial_value


class BaseInlineFormSetMixin(BaseInlineFormSet):
    """内联表单集的基类Mixin"""

    minimum_forms = None  # 最小表单数
    maximum_forms = None  # 最大表单数
    # prefix = None  # 表单集前缀

    def add_fields(self, form, index):
        """添加字段时自动设置序号"""
        super().add_fields(form, index)
        if hasattr(form.instance, "sequence"):
            form.initial["sequence"] = index

    def clean(self):
        """验证内联表单集"""
        super().clean()
        if not self.is_valid():
            return

        # 验证表单数量
        if self.minimum_forms and len(self.forms) < self.minimum_forms:
            raise forms.ValidationError(f"至少需要 {self.minimum_forms} 个表单项")
        if self.maximum_forms and len(self.forms) > self.maximum_forms:
            raise forms.ValidationError(f"最多只能有 {self.maximum_forms} 个表单项")

        # 重新分配序号，确保连续且从0开始
        if self.forms and hasattr(self.forms[0].instance, "sequence"):
            valid_forms = [
                f
                for f in self.forms
                if f.is_valid() and not f.cleaned_data.get("DELETE", False)
            ]
            for index, form in enumerate(valid_forms):
                form.cleaned_data["sequence"] = index
                form.instance.sequence = index


def create_inline_formset(
    parent_model,
    model,
    form=None,
    formset=BaseInlineFormSetMixin,
    fk_name=None,
    fields=None,
    exclude=None,
    extra=1,
    can_order=False,
    can_delete=True,
    max_num=None,
    min_num=None,
    validate_max=False,
    validate_min=False,
    can_delete_extra=False,
):
    """创建内联表单集的工厂函数

    Args:
        parent_model: 父模型类
        model: 子模型类
        form: 表单类，默认为 ModelForm
        formset: 表单集类，默认为 BaseInlineFormSet
        fk_name: 外键字段名
        fields: 要包含的字段列表
        exclude: 要排除的字段列表
        extra: 额外的空表单数量
        can_order: 是否可以排序
        can_delete: 是否可以删除
        max_num: 最大表单数量
        min_num: 最小表单数量
        validate_max: 是否验证最大数量
        validate_min: 是否验证最小数量

    Returns:
        InlineFormSet 类

    """
    defaults = {
        "form": form,
        "formset": formset,
        "fk_name": fk_name,
        "fields": fields,
        "exclude": exclude,
        "extra": extra,
        "can_order": can_order,
        "can_delete": can_delete,
        "max_num": max_num,
        "min_num": min_num,
        "validate_max": validate_max,
        "validate_min": validate_min,
        "can_delete_extra": can_delete_extra,
    }

    return inlineformset_factory(parent_model, model, **defaults)


class RequestFormMixin:
    """表单混入类，用于将 request 对象传递给表单实例

    使用方法：
    1. 在视图中，通过 form.set_request(request) 设置请求对象
    2. 在表单中，通过 self.request 访问请求对象
    """

    def __init__(self, *args, **kwargs):
        self.request = None
        super().__init__(*args, **kwargs)

    def set_request(self, request):
        """设置请求对象"""
        self.request = request
        return self  # 支持链式调用


class DynamicFormMixin(RequestFormMixin):
    """动态表单混入类，用于处理动态依赖字段

    提供以下功能：
    1. 自动将请求对象传递给表单实例
    2. 处理API请求参数
    3. 注入动态字段处理逻辑
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._process_dynamic_fields()

    def _process_dynamic_fields(self):
        """处理表单中的动态字段"""
        from .fields import DynamicModelChoiceField

        # 遍历所有字段，找出动态字段
        for field_name, field in self.fields.items():
            if isinstance(field, DynamicModelChoiceField) and field.dependencies:
                # 确保依赖字段存在于表单中
                for dep_name in field.dependencies:
                    if dep_name not in self.fields and not dep_name.startswith("__"):
                        # 警告依赖字段不存在
                        import warnings

                        warnings.warn(
                            f"依赖字段 '{dep_name}' 不存在于表单中，但被字段 '{field_name}' 依赖"
                        )
