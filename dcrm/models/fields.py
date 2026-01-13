from ipaddress import (
    AddressValueError,
    IPv4Interface,
    IPv6Interface,
    NetmaskValueError,
    ip_interface,
)
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class NullableFormFieldMixin:
    """表单字段混入类,将空值转换为 None"""

    empty_values = list(forms.Field.empty_values) + [""]

    def to_python(self, value: Any) -> str | None:
        """将输入值转换为Python对象
        空值返回 None
        """
        if value in self.empty_values:
            return None
        return super().to_python(value)


class NullableCharFormField(NullableFormFieldMixin, forms.CharField):
    """可空字符表单字段"""

    pass


class NullableCharFieldMixin:
    """字符字段混入类

    功能:
    - 将空字符串('')转换为null存入数据库
    - 配合unique约束使用

    适用于:
    models.CharField(unique=True, null=True, blank=True)
    """

    _formfield_class = NullableCharFormField

    def get_prep_value(self, value: Any) -> str | None:
        """准备数据库存值"""
        value = super().get_prep_value(value)
        return value or None

    def formfield(self, **kwargs) -> forms.Field:
        """返回表单字段"""
        defaults = {"form_class": self._formfield_class}
        defaults.update(kwargs)
        return super().formfield(**defaults)


class NullableCharField(NullableCharFieldMixin, models.CharField):
    """可空字符字段

    用法:
    class Device(models.Model):
        name = NullableCharField(
            max_length=100,
            unique=True,
            null=True,
            blank=True,
            verbose_name=_('名称')
        )
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("null", True)
        kwargs.setdefault("blank", True)
        super().__init__(*args, **kwargs)


class RackPositionFormField(forms.IntegerField):
    """机柜U位表单字段"""

    def to_python(self, value: Any) -> int | None:
        """将表单值转换为Python对象
        - 空值返回 None
        - 非空值转为整数
        """
        if value in self.empty_values:
            return None

        try:
            value = int(value)
            if value < 0:
                raise ValidationError(_("U位不能为负数"))
            return value
        except (TypeError, ValueError):
            raise ValidationError(_("请输入有效的U位数值"))


class RackPositionField(models.IntegerField):
    """机柜U位字段

    功能:
    - 将空值转换为 None
    - 将数值转为 字符串 zfill(2), 带U符号

    用法:
    class Device(models.Model):
        position = RackPositionField(
            verbose_name=_('机柜U位'),
            help_text=_('设备在机柜中的U位')
        )
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("null", True)
        kwargs.setdefault("blank", True)
        super().__init__(*args, **kwargs)

    def to_python(self, value: Any) -> int | None:
        """将数据库值转换为Python对象
        - 空值返回 None
        - 非空值转为整数
        """
        if value is None:
            return None

        if str(value).upper().endswith("U"):
            value = str(value).replace("U", "")

        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValidationError(_("无效的U位值"))

    def formfield(self, **kwargs) -> forms.Field:
        """返回表单字段"""
        defaults = {"form_class": RackPositionFormField, "help_text": self.help_text}
        defaults.update(kwargs)
        return super().formfield(**defaults)

    def value_to_string(self, obj: models.Model) -> str:
        """序列化值
        转换为带U的字符串格式，例如: 01U

        此方法会在以下情况被调用:
        1. django.core.serializers 序列化时
        2. model_to_dict 转换时
        3. 表单显示时
        """
        value = self.value_from_object(obj)
        if value is None:
            return ""
        # 确保返回的是字符串类型
        return f"{int(value):02d}U"

    def get_prep_value(self, value: Any) -> int | None:
        """准备数据库存储值
        在存储到数据库之前被调用
        """
        if value is None:
            return None

        # 如果是字符串且以U结尾，去掉U
        if isinstance(value, str) and value.upper().endswith("U"):
            value = value[:-1]

        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class DeviceHeightField(models.IntegerField):
    """设备高度字段

    功能:
    - 将空值转换为 None
    - 将数值转为 字符串 zill(2), 不带U符号
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("null", True)
        kwargs.setdefault("blank", True)
        super().__init__(*args, **kwargs)

    def to_python(self, value: Any) -> int | None:
        """将数据库值转换为Python对象
        - 空值返回 None
        - 非空值转为整数
        """
        if value is None:
            return None

        if str(value).upper().endswith("U"):
            value = str(value).replace("U", "")

        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValidationError(_("无效的U位值"))

    def formfield(self, **kwargs) -> forms.Field:
        """返回表单字段"""
        defaults = {"form_class": RackPositionFormField, "help_text": self.help_text}
        defaults.update(kwargs)
        return super().formfield(**defaults)

    def value_to_string(self, obj: models.Model) -> str:
        """序列化值
        转换为带U的字符串格式，例如: 01U

        此方法会在以下情况被调用:
        1. django.core.serializers 序列化时
        2. model_to_dict 转换时
        3. 表单显示时
        """
        value = self.value_from_object(obj)
        if value is None:
            return ""
        # 确保返回的是字符串类型
        return f"{int(value)}U"

    def get_prep_value(self, value: Any) -> int | None:
        """准备数据库存储值
        在存储到数据库之前被调用
        """
        if value is None:
            return None

        # 如果是字符串且以U结尾，去掉U
        if isinstance(value, str) and value.upper().endswith("U"):
            value = value[:-1]

        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class InterfaceIPAddressField(models.Field):
    """支持存储带掩码的IP地址字段(IPv4/IPv6)
    存储格式: IP地址/掩码 (例如: 192.168.1.1/24 或 2001:db8::1/64)
    """

    description = "An IP interface field (IPv4 or IPv6 address with netmask)"
    empty_strings_allowed = False

    def __init__(self, protocol="both", unpack_ipv4=False, *args, **kwargs):
        self.protocol = protocol.lower()
        self.unpack_ipv4 = unpack_ipv4
        kwargs["max_length"] = 45
        if self.protocol not in ("both", "ipv4", "ipv6"):
            raise ValueError("Protocol must be 'both', 'ipv4' or 'ipv6'")

        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.protocol != "both":
            kwargs["protocol"] = self.protocol
        if self.unpack_ipv4:
            kwargs["unpack_ipv4"] = self.unpack_ipv4
        kwargs["max_length"] = 45
        return name, path, args, kwargs

    # def db_type(self, connection):
    #     return 'inet'  # PostgreSQL的inet类型,支持存储IP和掩码

    def to_python(self, value):
        if not value:
            return None

        if isinstance(value, (IPv4Interface, IPv6Interface)):
            return value

        try:
            ip = ip_interface(value)

            # 验证IP版本
            if self.protocol == "ipv4" and not isinstance(ip, IPv4Interface):
                raise ValidationError(_("仅支持IPv4地址"))
            if self.protocol == "ipv6" and not isinstance(ip, IPv6Interface):
                raise ValidationError(_("仅支持IPv6地址"))

            # 是否需要解压缩IPv4映射的IPv6地址
            if isinstance(ip, IPv6Interface) and self.unpack_ipv4:
                if ip.ipv4_mapped:
                    return ip.ipv4_mapped

            return ip

        except (AddressValueError, NetmaskValueError) as e:
            raise ValidationError(
                _("无效的IP地址格式: %(error)s"), params={"error": str(e)}
            )

    def get_prep_value(self, value):
        if not value:
            return None

        if isinstance(value, str):
            value = self.to_python(value)

        return str(value)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        return self.to_python(value)

    def formfield(self, **kwargs):
        # 这里可以自定义表单字段
        defaults = {
            "form_class": forms.CharField,
            "max_length": 45,  # IPv6地址最大长度
        }
        defaults.update(kwargs)
        return super().formfield(**defaults)

    def get_internal_type(self):
        return "GenericIPAddressField"


class NaturalOrderingField(models.CharField):
    """A field which stores a naturalized representation of its target field, to be used for ordering its parent model.

    :param target_field: Name of the field of the parent model to be naturalized
    :param naturalize_function: The function used to generate a naturalized value (optional)
    """

    description = (
        "Stores a representation of its target field suitable for natural ordering"
    )

    def __init__(self, target_field, naturalize_function, *args, **kwargs):
        self.target_field = target_field
        self.naturalize_function = naturalize_function
        super().__init__(*args, **kwargs)

    def pre_save(self, model_instance, add):
        """Generate a naturalized value from the target field
        """
        original_value = getattr(model_instance, self.target_field)
        naturalized_value = self.naturalize_function(
            original_value, max_length=self.max_length
        )
        setattr(model_instance, self.attname, naturalized_value)

        return naturalized_value

    def deconstruct(self):
        kwargs = super().deconstruct()[3]  # Pass kwargs from CharField
        kwargs["naturalize_function"] = self.naturalize_function
        return (
            self.name,
            "utilities.fields.NaturalOrderingField",
            [self.target_field],
            kwargs,
        )


class CounterCacheField(models.BigIntegerField):
    """Counter field to keep track of related model counts.
    """

    def __init__(self, to_model, to_field, *args, **kwargs):
        if not isinstance(to_model, str):
            raise TypeError(
                _(
                    "%s(%r) is invalid. to_model parameter to CounterCacheField must be "
                    "a string in the format 'app.model'"
                )
                % (
                    self.__class__.__name__,
                    to_model,
                )
            )

        if not isinstance(to_field, str):
            raise TypeError(
                _(
                    "%s(%r) is invalid. to_field parameter to CounterCacheField must be "
                    "a string in the format 'field'"
                )
                % (
                    self.__class__.__name__,
                    to_field,
                )
            )

        self.to_model_name = to_model
        self.to_field_name = to_field

        kwargs["default"] = kwargs.get("default", 0)
        kwargs["editable"] = False

        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs["to_model"] = self.to_model_name
        kwargs["to_field"] = self.to_field_name
        return name, path, args, kwargs
