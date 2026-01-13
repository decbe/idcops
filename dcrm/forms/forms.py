import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from dcrm.models import CustomField


class CustomFieldFormField(forms.Field):
    """自定义字段的表单字段"""

    def __init__(self, custom_field, *args, **kwargs):
        self.custom_field = custom_field

        # 根据自定义字段类型设置表单字段类型
        field_type = custom_field.type
        if field_type == "string":
            kwargs["widget"] = forms.TextInput
        elif field_type == "integer":
            kwargs["widget"] = forms.NumberInput
        elif field_type == "boolean":
            kwargs["widget"] = forms.CheckboxInput
        elif field_type == "date":
            kwargs["widget"] = forms.DateInput(attrs={"type": "date"})
        elif field_type == "url":
            kwargs["widget"] = forms.URLInput
        elif field_type == "email":
            kwargs["widget"] = forms.EmailInput
        elif field_type == "choice":
            choices = [(c.strip(), c.strip()) for c in custom_field.choices.split(",")]
            kwargs["widget"] = forms.Select(choices=choices)

        super().__init__(*args, **kwargs)

        # 设置必填属性
        self.required = custom_field.required

        # 设置帮助文本
        if custom_field.help_text:
            self.help_text = custom_field.help_text

    def validate(self, value):
        super().validate(value)

        # 执行自定义字段的验证
        if self.custom_field.validation_regex and value:
            if not re.match(self.custom_field.validation_regex, str(value)):
                raise forms.ValidationError(
                    self.custom_field.validation_error_message
                    or _("Value does not match the required format")
                )


class CustomFieldModelForm(forms.ModelForm):
    """支持自定义字段的ModelForm基类
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_center = self.request.user.data_center
        # 获取该模型的所有自定义字段

        self.custom_fields = CustomField.objects.get_for_model(
            self.Meta.model, self.data_center
        )
        if not self.custom_fields.exists():
            return
        # 添加自定义字段到表单
        for cf in self.custom_fields:
            field_name = f"cf_{cf.name}"
            self.fields[field_name] = cf.to_form_field()
            if self.request and not getattr(self.request.user, "form_help_mode", False):
                field = cf.to_form_field()
                self.fields[field_name].widget.attrs.update(
                    {"placeholder": field.help_text}
                )
            # 如果是编辑表单,设置初始值
            if self.instance and self.instance.pk:
                self.initial[field_name] = self.instance.get_custom_field_value(
                    cf.name, cf
                )

    def clean(self):
        cleaned_data = super().clean()
        # 验证自定义字段
        # custom_fields = CustomField.objects.get_for_model(
        #     self._meta.model, self.data_center
        # )

        for cf in self.custom_fields:
            field_name = f"cf_{cf.name}"
            value = cleaned_data.get(field_name)

            # 如果字段没有值但有默认值，使用默认值
            if value is None and cf.default is not None:
                value = cf.get_default_value()
                _value = cf.serialize(value)

                cleaned_data[field_name] = _value

            try:
                # 验证字段值
                if value is not None or cf.required:
                    cf.validate(value)
                value = cf.serialize(value)

                # 如果是编辑表单，更新实例的自定义字段值
                if self.instance and self.instance.pk:
                    if not hasattr(self.instance, "custom_field_data"):
                        self.instance.custom_field_data = {}
                    if value is not None:
                        self.instance.custom_field_data[cf.name] = value
                    elif cf.name in self.instance.custom_field_data:
                        del self.instance.custom_field_data[cf.name]
                # value = cf.serialize(value)
                cleaned_data[field_name] = value
            except ValidationError as e:
                self.add_error(field_name, e.messages)
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)

        # 保存自定义字段数据
        # custom_fields = CustomField.objects.get_for_model(
        #     self._meta.model, self.data_center
        # )
        for cf in self.custom_fields:
            field_name = f"cf_{cf.name}"
            if field_name in self.cleaned_data:
                instance.set_custom_field_value(
                    cf.name, self.cleaned_data[field_name], self.data_center
                )

        if commit:
            instance.save()
        return instance

    def get_custom_fields(self) -> list[str]:
        """获取表单中的自定义字段
        """
        return [field for name, field in self.fields.items() if name.startswith("cf_")]


class CustomFieldBulkEditForm(forms.Form):
    """用于批量编辑自定义字段的表单
    """

    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)

    def __init__(self, *args, **kwargs):
        model = kwargs.pop("model")
        data_center = kwargs.pop("data_center")
        super().__init__(*args, **kwargs)

        custom_fields = CustomField.objects.get_for_model(model, data_center)
        for cf in custom_fields:
            field_name = f"cf_{cf.name}"
            self.fields[field_name] = cf.to_form_field(
                required=False, help_text=_("留空表示不修改此字段")
            )


class CustomFieldFilterForm(forms.Form):
    """用于过滤自定义字段的表单
    """

    def __init__(self, *args, **kwargs):
        model = kwargs.pop("model")
        data_center = kwargs.pop("data_center")
        super().__init__(*args, **kwargs)

        custom_fields = CustomField.objects.get_for_model(model, data_center)
        for cf in custom_fields:
            field_name = f"cf_{cf.name}"
            self.fields[field_name] = cf.to_form_field(required=False)

            # 为选择类型字段添加"空"选项
            if cf.type in ("select", "multiselect"):
                self.fields[field_name].choices = [("", "---------")] + (
                    self.fields[field_name].choices or []
                )
