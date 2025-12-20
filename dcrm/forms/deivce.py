from django import forms
from django.db.models.fields import BLANK_CHOICE_DASH
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from dcrm.models import Device, DeviceModel, DeviceType, IPAddress, Manufacturer, Rack

from .base import BaseModelFormMixin
from .fields import DeviceModelChoiceField, DeviceRackChoiceField
from .forms import CustomFieldModelForm
from .mixins import AutoSequenceMixin
from .widget import DeviceModelSelect


class DeviceBaseForm(AutoSequenceMixin, CustomFieldModelForm, BaseModelFormMixin):
    """设备创建表单"""

    created_at = forms.DateField(
        label=_("上架时间"),
        widget=forms.DateInput(
            format="%Y/%m/%d", attrs={"data-date": "true", "type": "date"}
        ),
    )

    class Meta:
        model = Device
        fields = [
            "rack",
            "created_at",
            "position",
            "serial_number",
            "name",
            "tenant",
            "model",
            "type",
            "height",
            "rack_pdus",
            "ips",
            "warranty_expiry",
            "tags",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 修改 model 字段的显示
        model_field = self.fields["model"]
        original_queryset = model_field.queryset.select_related("type")

        # 替换原有的 model 字段
        self.fields["model"] = DeviceModelChoiceField(
            queryset=original_queryset,
            required=True,
            widget=DeviceModelSelect(
                attrs={
                    "class": "form-control select",
                    "style": "width: 100%",
                    "data-width": "100%",
                }
            ),
            help_text=model_field.help_text,
            label=format_html(
                '{}<span class="text-red" style="margin-left: 5px;">*</span>',
                model_field.label or model_field.name.title(),
            ),
        )

        # 替换原有的 rack 字段
        rack_field = self.fields["rack"]
        original_rack_queryset = rack_field.queryset.select_related("tenant")
        self.fields["rack"] = DeviceRackChoiceField(
            queryset=original_rack_queryset,
            required=rack_field.required,
            widget=forms.Select(
                attrs={
                    "class": "form-control select",
                    "style": "width: 100%",
                    "data-width": "100%",
                }
            ),
            help_text=rack_field.help_text,
            label=rack_field.label,
        )

    def clean(self):
        """
        表单验证:
        1. 执行通用的unique_together验证
        2. 验证position的特定规则
        """
        cleaned_data = super().clean()
        # 转换position为整数
        position = cleaned_data.get("position")
        if position:
            try:
                position = int(position)
                cleaned_data["position"] = position
            except (TypeError, ValueError):
                self.add_error("position", "请选择有效的U位")
                return cleaned_data

        if position == "":
            self.add_error("position", "设备U位信息不能为空")

        if position:
            if int(position) <= 0:
                self.add_error("position", "请选择有效的U位")
                return cleaned_data

            # 验证U位是否可用
            rack = cleaned_data.get("rack")
            device_height = cleaned_data.get("height")
            if rack:
                # 获取可用U位列表
                if self.instance is not None:
                    available_units = rack.get_available_units(
                        u_height=int(device_height), exclude_id=self.instance.id
                    )
                else:
                    available_units = rack.get_available_units(
                        u_height=int(device_height)
                    )
                if position not in available_units:
                    self.add_error("position", f"{position}U 不在可用U位列表中")
                    return cleaned_data

        # 3. 验证serial_number的唯一性
        serial_number = cleaned_data.get("serial_number")
        if serial_number:
            # 移除多余的空格
            serial_number = serial_number.strip()
            cleaned_data["serial_number"] = serial_number

            # 验证唯一性
            exists = self.Meta.model.objects.filter(
                serial_number=serial_number, data_center_id=self.data_center_id
            )
            if self.instance.pk:
                exists = exists.exclude(pk=self.instance.pk)

            if exists.exists():
                self.add_error("serial_number", _("此序列号已存在"))

        return cleaned_data


class DeviceCreateForm(DeviceBaseForm):
    """设备创建表单"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request or not hasattr(self.request.user, "data_center"):
            raise ValueError("用户未登录或未设置数据中心")
        self.data_center_id = self.request.user.data_center
        post_rack_id = kwargs.get("data", {}).get("rack", None)
        self.rack_id = kwargs.get("initial", {}).get("rack", post_rack_id)
        self.rack = Rack.objects.filter(pk=self.rack_id).first()
        self.fields["created_at"].initial = timezone.now().date()

        self.fields["rack"].queryset = self.fields["rack"].queryset.filter(
            status__allowed_mount=True
        )

        # 初始化U位选择
        choices = BLANK_CHOICE_DASH.copy()  # 默认选项
        if self.rack:
            available_units = self.rack.get_available_units()
            choices.extend([(u, f"{u:02d}U") for u in available_units])
            # 获取机柜可用PDU
            self.fields["rack_pdus"].queryset = Rack.get_available_pdus(self.rack)
            self.tenant = getattr(self.rack, "tenant", None)
            if self.tenant:
                # 设置租户
                self.fields["tenant"].initial = self.tenant
                # 设置IP地址
                self.fields["ips"].queryset = IPAddress.get_available_ips_for_tenant(
                    self.tenant
                ).filter(status__in=["reserved", "allocated"])
        else:
            # 默认显示1-50U
            # choices.extend([(i, f"{i:02d}U") for i in range(1, 50)])
            # 设置PDU和IP地址为空
            self.fields["tenant"].queryset = self.fields["tenant"].queryset.none()
            self.fields["model"].queryset = self.fields["model"].queryset.none()
            self.fields["rack_pdus"].queryset = self.fields["rack_pdus"].queryset.none()
            self.fields["ips"].queryset = self.fields["ips"].queryset.none()
            self.fields["tags"].queryset = self.fields["ips"].queryset.none()
        self.fields["position"] = forms.ChoiceField(
            choices=choices,
            widget=forms.Select(
                attrs={
                    "class": "form-control select",
                    "style": "width: 100%",
                    "hx-get": "/devices/online/add/",
                    "hx-trigger": "change",
                    "hx-target": "#device-form",
                    "hx-swap": "innerHTML",
                    "hx-include": '[name="rack"],[name="position"]',  # 包含rack字段的值
                    "hx-params": "*",  # 发送所有参数
                    "hx-push-url": "true",
                }
            ),
            help_text=self.fields["position"].help_text,
            required=self.fields["position"].required,
            label=self.fields["position"].label,
        )
        self.fields["rack"].widget.attrs.update(
            {
                "hx-get": "/devices/online/add/",
                "hx-trigger": "change",
                "hx-target": "#device-form",
                "hx-swap": "innerHTML",
                "hx-include": '[name="rack"],[name="position"]',  # 包含rack字段的值
                # "hx-params": "*",  # 发送所有参数
                "hx-push-url": "true",
            }
        )


class DeviceUpdateForm(DeviceBaseForm):
    """设备更新表单"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request or not hasattr(self.request.user, "data_center"):
            raise ValueError("用户未登录或未设置数据中心")
        self.data_center_id = self.instance.data_center_id
        self.rack_id = kwargs.get("initial", {}).get("rack", 0)
        self.cross_rack = int(self.rack_id) != int(self.instance.rack.id)

        # 设置该租户可以挂载的机柜
        self.fields["rack"].queryset = self.fields["rack"].queryset.filter(
            status__allowed_mount=True, tenant=self.instance.tenant
        )
        # 初始化U位选择
        choices = BLANK_CHOICE_DASH.copy()  # 默认选项
        choices.extend([(i, f"{i:02d}U") for i in range(1, 50)])
        if self.cross_rack:
            # 查询当前机柜的可用U位和PDU
            rack = Rack.objects.filter(pk=self.rack_id).first()
            available_units = rack.get_available_units()
            self.fields["rack_pdus"].queryset = Rack.get_available_pdus(rack)
        else:
            # 移动到其他机柜
            self.fields["rack_pdus"].queryset = (
                Rack.get_available_pdus(self.instance.rack)
                | self.instance.rack_pdus.all()
            )
            available_units = self.instance.rack.get_available_units(
                u_height=self.instance.height, exclude_id=self.instance.id
            )
        # 设置U位选择
        choices = BLANK_CHOICE_DASH.copy()  # 默认选项
        choices.extend([(u, f"{u:02d}U") for u in available_units])

        self.fields["position"] = forms.ChoiceField(
            choices=choices,
            widget=forms.Select(
                attrs={
                    "class": "form-control select",
                    "style": "width: 100%",
                    "hx-get": f"/devices/online/{self.instance.id}/edit/",
                    "hx-trigger": "change",
                    "hx-target": "#device-form",
                    "hx-swap": "innerHTML",
                    "hx-include": '[name="rack"],[name="position"]',  # 包含rack字段的值
                    "hx-params": "*",  # 发送所有参数
                    "hx-push-url": "true",
                }
            ),
            help_text=self.fields["position"].help_text,
            required=self.fields["position"].required,
            label=self.fields["position"].label,
        )

        # 设置该设备可以挂载的IP地址
        self.fields["ips"].queryset = (
            IPAddress.get_available_ips_for_tenant(self.instance.tenant).filter(
                status__in=["reserved", "allocated"]
            )
            | self.instance.ips.all()
        )

        self.fields["rack"].widget.attrs.update(
            {
                "hx-get": f"/devices/online/{self.instance.id}/edit/",
                "hx-trigger": "change",
                "hx-target": "#device-form",
                "hx-swap": "innerHTML",
                "hx-include": '[name="rack"],[name="position"]',  # 包含rack字段的值
                "hx-params": "*",  # 发送所有参数
                "hx-push-url": "true",
            }
        )


class DeviceMigrateForm(BaseModelFormMixin):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 设置该租户可以挂载的机柜
        self.fields["rack"].queryset = self.fields["rack"].queryset.filter(
            status__allowed_mount=True, tenant=self.instance.tenant
        )

        # 设置该设备可以挂载的IP地址
        self.fields["ips"].queryset = (
            IPAddress.get_available_ips_for_tenant(self.instance.tenant).filter(
                status__in=["reserved", "allocated"]
            )
            | self.instance.ips.all()
        )
        self.fields["rack_pdus"].queryset = (
            Rack.get_available_pdus(self.instance.rack) | self.instance.rack_pdus.all()
        )


class DeviceModelForm(CustomFieldModelForm, BaseModelFormMixin):
    type = forms.CharField(
        label=_("设备类型"),
        required=True,
        help_text=_("如服务器、配线架、交换机、UPS等"),
        widget=forms.Select(
            attrs={
                "class": "form-control select",
                "data-create-option": "true",
            }
        ),
    )

    class Meta:
        model = DeviceModel
        fields = [
            "manufacturer",
            "type",
            "name",
            "height",
            "ethernet_port_count",
            "fiber_port_count",
            "console_port_count",
            "usb_port_count",
            "power_port_count",
            "mgmt_port_count",
            "other_port_count",
            "description",
            "shared",
            "tags",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        empty_label = ("", "---------")
        self.fields["type"].widget.choices = [
            empty_label,
            *list(DeviceType.objects.values_list("id", "name")),
        ]

    def clean_type(self):
        value = self.cleaned_data["type"]
        try:
            if value.isdigit():
                return DeviceType.objects.get(id=value)
            else:
                instance, created = DeviceType.objects.get_or_create(
                    name=value,
                    defaults={
                        "created_by": self.request.user,
                        "data_center": self.request.user.data_center,
                        "description": _("从选择框中创建"),
                    },
                )
                return instance
        except (DeviceType.DoesNotExist, ValueError):
            raise forms.ValidationError(_("无效的设备类型"))
