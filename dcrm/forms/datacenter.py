from django import forms
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from dcrm.models.base import DataCenter, DataCenterGroup


class DataCenterForm(forms.ModelForm):
    group = forms.CharField(
        label=_("分组"),
        required=False,
        help_text=_("数据中心所属的分组, 例如: 华南区、华北区、华东区等"),
        widget=forms.Select(
            attrs={
                "class": "form-control select",
                "data-create-option": "true",
            }
        ),
    )

    class Meta:
        model = DataCenter
        fields = [
            "name",
            "group",
            "security_level",
            "duty_type",
            "description",
            "physical_address",
            "shipping_address",
            "contact_name",
            "contact_phone",
            "contact_email",
        ]

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        empty_label = ("", "---------")
        self.fields["group"].widget.choices = [
            empty_label,
            *list(DataCenterGroup.objects.values_list("id", "name")),
        ]
        for field_name, field in self.fields.items():
            if field.required:
                field.label = format_html(
                    '{}<span class="text-red" style="margin-left: 5px;">*</span>',
                    field.label or field_name.title(),
                )

            field.widget.attrs.update(
                {
                    "class": "form-control",
                    "autocomplete": "off",
                    "placeholder": field.help_text,
                }
            )
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
            if isinstance(field.widget, forms.widgets.Textarea):
                self.fields[field_name].widget.attrs.update({"rows": "3"})

    def clean_group(self):
        value = self.cleaned_data["group"]
        try:
            if value.isdigit():
                return DataCenterGroup.objects.get(id=value)
            else:
                group, created = DataCenterGroup.objects.get_or_create(
                    name=value,
                    defaults={
                        "created_by": self.request.user,
                        "description": _("从选择框中创建"),
                    },
                )

                return group
        except (DataCenterGroup.DoesNotExist, ValueError):
            raise forms.ValidationError(_("无效的数据中心组"))
