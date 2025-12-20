from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from dcrm.models import Rack
from dcrm.utilities.base import expand_regex_pattern

from .base import BaseModelFormMixin
from .forms import CustomFieldModelForm


class RackBaseForm(CustomFieldModelForm, BaseModelFormMixin):
    """机柜基础表单"""

    # 添加额外的表单字段（这些字段不在模型中）
    use_regex_pattern = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        initial="",
    )

    class Meta:
        model = Rack
        fields = [
            "room",
            "name",
            "u_height",
            "pdu_count",
            "pdu_16a_count",
            "rack_type",
            "tenant",
            "status",
            "opening_date",
            "rated_power_kw",
            "rated_current",
            "voltage",
            "contract_power",
            "depth",
            "width",
            "height",
            "tags",
        ]

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _(
                        "机柜名（正则模式批量创建），正则表达式匹配。例如：3F01-Rack(0[1-9]|1[0-8])"
                    ),
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk is None:
            self.fields["u_height"].initial = self.data_center.get_config(
                "RACK_DEFAULT_HEIGHT", 45
            )
        self.fields["name"].force_help_text = True
        self.fields["name"].help_text = _(
            "机柜名（支持正则模式批量创建），正则表达式匹配。例如：3F01-Rack(0[1-9]|1[0-8])"
        )
        self._expanded_names = None

    def clean(self):
        """表单清理方法，用于处理正则模式的验证"""
        cleaned_data = super().clean()
        name = cleaned_data.get("name")
        use_regex = cleaned_data.get("use_regex_pattern") == "1"

        if use_regex and name:
            try:
                # 验证并展开正则表达式
                names = expand_regex_pattern(name)
                if not names:
                    raise ValidationError(_("正则表达式未匹配到任何结果"))

                # 验证生成的名称是否已存在
                existing_names = set(
                    Rack.objects.filter(
                        name__in=names, data_center=self.request.user.data_center
                    ).values_list("name", flat=True)
                )

                if existing_names:
                    raise ValidationError(
                        _("以下机柜名已存在：%(names)s"),
                        params={"names": ", ".join(existing_names)},
                    )

                # 保存展开的名称供后续使用
                self._expanded_names = names
            except Exception as e:
                raise ValidationError(str(e))

        return cleaned_data


class RackAllocateForm(forms.ModelForm):

    class Meta:
        model = Rack
        fields = ["rack_type", "tenant", "status", "opening_date", "contract_power"]
