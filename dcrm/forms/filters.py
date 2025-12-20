from django import forms
from django.utils.translation import gettext_lazy as _


class MultipleChoiceFilterWidget(forms.SelectMultiple):
    """多选下拉框"""

    def __init__(self, attrs=None):
        default_attrs = {
            "class": "form-control select2",
            "data-placeholder": _(" 请选择..."),
            "multiple": "multiple",
            "style": "width: 100%",
            "data-width": "100%",
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)


class DateRangeWidget(forms.TextInput):
    """日期范围选择器"""

    def __init__(self, attrs=None):
        default_attrs = {"class": "form-control daterangepicker", "autocomplete": "off"}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)


class DateFieldFilterWidget(forms.MultiWidget):
    """日期字段过滤组件"""

    def __init__(self, date_fields, attrs=None):
        widgets = [
            forms.Select(
                attrs={"class": "form-control"},
                choices=[("", "选择字段")]
                + [(field, label) for field, label in date_fields],
            ),
            forms.TextInput(
                attrs={
                    "class": "form-control daterangepicker",
                    "autocomplete": "off",
                    "placeholder": "选择日期范围",
                }
            ),
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if value:
            return value.split("::")
        return [None, None]


class DateFieldFilterField(forms.MultiValueField):
    """日期字段过滤表单字段"""

    def __init__(self, date_fields, **kwargs):
        fields = [
            forms.ChoiceField(
                choices=[("", "选择字段")]
                + [(field, label) for field, label in date_fields],
                required=False,
            ),
            forms.CharField(required=False),
        ]
        super().__init__(
            fields=fields,
            widget=DateFieldFilterWidget(date_fields),
            required=False,
            **kwargs,
        )

    def compress(self, data_list):
        if data_list and all(data_list):
            return "::".join(data_list)
        return None


class ButtonCheckboxFilterWidget(forms.CheckboxSelectMultiple):
    """按钮式复选框筛选组件"""

    template_name = "widgets/button_checkbox_filter.html"

    def __init__(self, attrs=None) -> None:
        default_attrs = {"class": "hidden"}  # 隐藏原始复选框
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)


class FilterForm(forms.Form):
    """过滤表单基类"""

    def __init__(self, *args, **kwargs):
        self.model = kwargs.pop("model", None)
        super().__init__(*args, **kwargs)

        # 为所有字段添加样式
        for field in self.fields.values():
            if not isinstance(
                field.widget, (MultipleChoiceFilterWidget, DateRangeWidget)
            ):
                field.widget.attrs.update({"class": "form-control"})


class FilterModelForm(forms.ModelForm):
    """过滤表单模型类"""

    model = None
    exclude = []
    filter_fields = []
    exclude_filter_fields = [
        "custom_field_data",
        "id",
        "created_at",
        "updated_at",
        "data_center",
        "lft",
        "rght",
        "tree_id",
        "level",
        "parent_id",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        opts = self.model._meta
        fields = [
            f.name
            for f in opts.fields + opts.many_to_many
            if f.name not in self.exclude
        ]
        for field in fields:
            self.fields[field].widget.attrs.update({"class": "form-control"})
