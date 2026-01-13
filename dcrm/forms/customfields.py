import json
import re

from django import forms
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from dcrm.models import CustomField, CustomFieldTypeChoices
from dcrm.utilities.lookup import get_cf_models_queryset

from .base import BaseModelFormMixin


class ChoicesWidget(forms.Textarea):
    """Render each key-value pair of a dictionary on a new line within a textarea for easy editing.
    """

    def format_value(self, value):
        if not value:
            return None
        if type(value) is list:
            return "\n".join([f"{k}:{v}" for k, v in value])
        return value


class CustomFieldBaseForm(BaseModelFormMixin):
    choices = forms.CharField(
        widget=ChoicesWidget(attrs={"hidden": True}),
        required=False,
        label=_("选项"),
        help_text=mark_safe(
            _("每行输入一个选项，可以在每个选项使用冒号来指定显示内容。例如：3a:AAA")
        ),
    )
    default = forms.CharField(
        required=False,
        label=_("默认值"),
        help_text=_('字段的默认值，例如：0、"now"、true、"3a"'),
    )
    filter_params = forms.CharField(
        widget=forms.Textarea(attrs={"hidden": True}),
        required=False,
        label=_("过滤参数"),
        help_text=_(
            '用于过滤关联对象的参数，格式: {"tenant": "1"}，适用于字段类型为对象或多对象'
        ),
    )

    class Meta:
        model = CustomField
        fields = (
            "type",
            "name",
            "label",
            "ui_visible",
            "description",
            "required",
            "unique",
            "default",
            "validation_regex",
            "validation_minimum",
            "validation_maximum",
            "choices",
            "related_model",
            "filter_params",
            "object_types",
            "order",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        initial = kwargs.get("initial", {})
        self.fields["object_types"].queryset = get_cf_models_queryset()
        if self.instance.pk is None:
            field_type = initial.get("type", "text")
            self.fields["type"].widget.attrs.update(
                {
                    "hx-get": "/custom-fields/add/",
                    "hx-trigger": "change",
                    "hx-target": "#edit-form",
                    "hx-swap": "innerHTML",
                    "hx-include": '[name="type"]',
                    "hx-push-url": "true",
                }
            )
        else:
            field_type = initial.get("type", self.instance.type)
        if "choices" in self.initial and self.initial["choices"]:
            origin_choices = self.initial["choices"]
            choices = []
            if isinstance(origin_choices, str):
                _choices = json.loads(origin_choices)
            else:
                _choices = origin_choices
            for choice in _choices:
                choice = (choice[0].replace(":", "\\:"), choice[1].replace(":", "\\:"))
                choices.append(choice)
            self.initial["choices"] = choices

        initial_hidden_fields = [
            "validation_minimum",
            "validation_maximum",
            "validation_regex",
            "choices",
            "related_model",
            "filter_params",
        ]
        for hidden_fieldname in initial_hidden_fields:
            self.fields[hidden_fieldname].widget.attrs.update({"hidden": True})
        # 根据 field_type 来初始化表单，默认text文本
        if field_type in [
            CustomFieldTypeChoices.TYPE_DECIMAL,
            CustomFieldTypeChoices.TYPE_INTEGER,
        ]:
            # 显示最大最小值，隐藏其他
            self.fields["validation_minimum"].widget.attrs["hidden"] = False
            self.fields["validation_maximum"].widget.attrs["hidden"] = False
        elif field_type in [
            CustomFieldTypeChoices.TYPE_TEXT,
            CustomFieldTypeChoices.TYPE_LONGTEXT,
            CustomFieldTypeChoices.TYPE_URL,
        ]:
            self.fields["validation_regex"].widget.attrs["hidden"] = False
        elif field_type in [
            CustomFieldTypeChoices.TYPE_MULTISELECT,
            CustomFieldTypeChoices.TYPE_SELECT,
        ]:
            self.fields["choices"].widget.attrs["hidden"] = False
        elif field_type in [
            CustomFieldTypeChoices.TYPE_OBJECT,
            CustomFieldTypeChoices.TYPE_MULTIOBJECT,
        ]:
            # 显示关联模型，和过滤参数，隐藏其他
            self.fields["related_model"].widget.attrs["hidden"] = False
            self.fields["filter_params"].widget.attrs["hidden"] = False

    def clean_choices(self):
        """清理choices选项内容，规范为json格式数据
        """
        data = []
        for line in self.cleaned_data["choices"].splitlines():
            try:
                value, label = re.split(r"(?<!\\):", line, maxsplit=1)
                value = value.replace("\\:", ":")
                label = label.replace("\\:", ":")
            except ValueError:
                value, label = line, line
            data.append([value.strip(), label.strip()])
        return data
