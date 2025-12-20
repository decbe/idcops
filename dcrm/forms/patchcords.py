from django import forms
from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

from dcrm.models.choices import (
    DevicePortStatusChoices,
    DeviceStatusChoices,
    NodeTypeChoices,
    PortTypeChoices,
)
from dcrm.models.patchcords import PatchCord, PatchCordNode

from .base import BaseModelFormMixin
from .mixins import (
    AutoSequenceMixin,
    BaseInlineFormSetMixin,
    CustomFieldsFormMixin,
    create_inline_formset,
)


class PatchCordNodeForm(CustomFieldsFormMixin, BaseModelFormMixin):
    """跳线节点表单"""

    class Meta:
        model = PatchCordNode
        fields = [
            "sequence",
            "node_type",
            "port_type",
            "color",
            "length",
            "rack",
            "device",
            "port_name",
            "rack_unit",
            "tenant",
        ]
        widgets = {
            "sequence": forms.HiddenInput(),
            "node_type": forms.RadioSelect(),
            "rack": forms.Select(
                attrs={
                    "class": "form-control",
                    "data-placeholder": _("选择机柜..."),
                    "data-url": reverse_lazy("rack_autocomplete"),
                    "data-params": "device__isnull=0",
                }
            ),
            "device": forms.Select(
                attrs={
                    "class": "form-control",
                    "data-placeholder": _("选择设备..."),
                    "data-url": reverse_lazy("online_device_autocomplete"),
                    "data-depends": "node_type,rack",
                }
            ),
            "port_name": forms.Select(
                attrs={
                    "class": "form-control",
                    "data-placeholder": _("选择端口..."),
                    "data-url": reverse_lazy("device_port_autocomplete"),
                    "data-depends": "device",
                    "data-params": "status=disconnected",
                }
            ),
            "rack_unit": forms.TextInput(
                attrs={
                    "class": "form-control",
                    # "readonly": "readonly",
                    "placeholder": _("机柜U位"),
                    "data-depends-select": "device",
                }
            ),
            "tenant": forms.Select(
                attrs={
                    "class": "form-control",
                    "data-placeholder": _("选择租户..."),
                    "data-url": reverse_lazy("tenant_autocomplete"),
                }
            ),
            "port_type": forms.Select(
                attrs={
                    "class": "form-control",
                    "data-placeholder": _("选择端口类型..."),
                },
                choices=PortTypeChoices.choices,
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["node_type"].widget.attrs["class"] = "node-type-radio"
        # 基础查询集过滤
        if hasattr(self, "data_center"):
            rack_qs = (
                self.fields["rack"]
                .queryset.filter(
                    data_center=self.data_center,
                )
                .filter(device__isnull=False)
                .distinct()
            )

            device_qs = self.fields["device"].queryset.filter(
                data_center=self.data_center,
                status__in=[DeviceStatusChoices.MOUNTED, DeviceStatusChoices.MIGRATED],
            )
            if not self.instance or not self.instance.pk:
                port_qs = (
                    self.fields["port_name"]
                    .queryset.filter(
                        data_center=self.data_center,
                    )
                    .filter(status=DevicePortStatusChoices.DISCONNECTED)
                )
            else:
                port_qs = self.fields["port_name"].queryset.filter(
                    data_center=self.data_center, device=self.instance.device
                ) | self.fields["port_name"].queryset.filter(
                    pk=self.instance.port_name.pk
                )
                self.fields["device"].queryset = device_qs.filter(
                    rack=self.instance.rack
                )
                self.fields["tenant"].queryset = self.fields["tenant"].queryset.filter(
                    id=self.instance.tenant.id
                )

            self.fields["rack"].queryset = rack_qs
            self.fields["device"].queryset = device_qs
            self.fields["port_name"].queryset = port_qs

    def clean(self):
        """验证表单数据"""
        cleaned_data = super().clean()

        sequence = cleaned_data.get("sequence")
        if sequence is None or sequence < 0:
            self.add_error("sequence", _("节点序号必须大于或等于0"))

        patch_cord = None
        if self.instance and hasattr(self.instance, "patch_cord"):
            try:
                patch_cord = self.instance.patch_cord
            except ObjectDoesNotExist:
                pass

        node_type = cleaned_data.get("node_type")
        device = cleaned_data.get("device")
        rack = cleaned_data.get("rack")
        port_name = cleaned_data.get("port_name")

        if node_type == NodeTypeChoices.DEVICE:
            if not device:
                self.add_error("device", _("设备端口必须选择设备"))
            if device and device.rack != rack:
                self.add_error("rack", _("机柜必须是设备所在的机柜"))
            if device and device.tenant != cleaned_data.get("tenant"):
                self.add_error("tenant", _("租户必须是设备所属的租户"))
        elif node_type == NodeTypeChoices.PATCH_PANEL:
            if not rack:
                self.add_error("rack", _("配线架端口必须选择机柜"))

        if patch_cord and sequence is not None:
            existing_node = (
                PatchCordNode.objects.filter(patch_cord=patch_cord, sequence=sequence)
                .exclude(
                    pk=self.instance.pk if self.instance and self.instance.pk else None
                )
                .first()
            )

            if existing_node:
                self.add_error(
                    "sequence", _("序号 %(sequence)s 已被使用") % {"sequence": sequence}
                )

            if port_name:
                port_query = PatchCordNode.objects.filter(
                    patch_cord=patch_cord, port_name=port_name
                )

                if node_type == NodeTypeChoices.DEVICE:
                    port_query = port_query.filter(device=device)
                else:
                    port_query = port_query.filter(rack=rack)

                existing_port = port_query.exclude(
                    pk=self.instance.pk if self.instance and self.instance.pk else None
                ).first()

                if existing_port:
                    self.add_error("port_name", _("端口已被其他节点使用"))
        return cleaned_data

    def save(self, commit=True):
        """保存时自动设置数据中心"""
        instance = super().save(commit=False)
        if not instance.data_center_id and self.request:
            instance.data_center = self.request.user.data_center
        if commit:
            instance.save()
        return instance


class PatchCordForm(AutoSequenceMixin, CustomFieldsFormMixin, BaseModelFormMixin):
    """跳线表单"""

    cable_label_mode = forms.ChoiceField(
        choices=[
            (0, _("不自动生成")),
            (1, _("机柜#U位<=flag=>")),
            (2, _("机柜#U位#设备<=flag=>")),
            (3, _("机柜#U位#设备#端口<=flag=>")),
        ],
        initial=1,
        required=False,
        label=_("标签模式"),
        help_text=_("自动根据始终节点生成线缆标签的模式"),
        widget=forms.RadioSelect(),
    )

    class Meta:
        model = PatchCord
        fields = [
            "identifier",
            "status",
            "network_product",
            "bandwidth",
            "cable_label_mode",
            "cable_label",
            "description",
            "tags",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        o = self.instance.pk if self.instance.pk else 0
        self.fields["cable_label"].widget.attrs.update({"data-object-pk": o})


PatchCordNodeFormSet = create_inline_formset(
    parent_model=PatchCord,
    model=PatchCordNode,
    form=PatchCordNodeForm,
    formset=BaseInlineFormSetMixin,
    extra=0,
    min_num=2,
    max_num=10,
    validate_min=True,
    validate_max=True,
    can_delete=True,
    can_delete_extra=True,
)
