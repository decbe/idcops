import dateparser
from str2bool import str2bool

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from dcrm.models.choices import CustomFieldTypeChoices
from dcrm.utilities.base import get_content_type_by_labeled_name


class CSVModelChoiceField(forms.ModelChoiceField):
    """
    用于CSV导入的ModelChoiceField，支持通过多个字段查找关联对象
    """

    default_error_messages = {
        "invalid_choice": _("未找到匹配的: %(value)s"),
    }

    def __init__(self, *args, **kwargs):
        # 添加search_fields参数，用于指定查找字段
        self.search_fields = kwargs.pop("search_fields", ["name"])
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if not value:
            return None

        if self.queryset.model is ContentType:
            return get_content_type_by_labeled_name(value)

        try:
            # 构建查询条件
            query = Q()
            for field in self.search_fields:
                query |= Q(**{field: value})

            # 尝试查找对象
            obj = self.queryset.filter(query).first()
            if obj:
                return obj

            # 如果找不到对象，尝试通过ID查找
            if value.isdigit():
                return self.queryset.filter(pk=value).first()

            raise self.queryset.model.DoesNotExist()

        except (ValueError, TypeError, self.queryset.model.DoesNotExist):
            raise forms.ValidationError(
                self.error_messages["invalid_choice"],
                code="invalid_choice",
                params={"value": value},
            )


class CSVChoiceField(forms.ChoiceField):
    """
    用于CSV导入的ChoiceField，处理选项字段
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.choices = self.choices

    def to_python(self, value):
        if not isinstance(value, str):
            raise forms.ValidationError(_("无效的值: {value}").format(value=value))
        value = value.strip()
        if not value:
            return None
        value_to_key_map = {c[1]: c[0] for c in self.choices}
        if value in value_to_key_map.keys():
            return value_to_key_map.get(value)
        elif value in value_to_key_map.values():
            return value
        else:
            raise forms.ValidationError(_("无效的值: {value}").format(value=value))


class CSVMultipleChoiceField(forms.MultipleChoiceField):
    """
    用于CSV导入的MultipleChoiceField，支持逗号分隔的多选值
    """

    def to_python(self, value):
        if not value:
            return []
        if not isinstance(value, str):
            raise forms.ValidationError(_("无效的值: {value}").format(value=value))
        return value.split(",")


class CSVModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    """
    用于CSV导入的ModelMultipleChoiceField，支持逗号分隔的多个关联对象
    """

    default_error_messages = {
        "invalid_choice": _("未找到匹配的: %(value)s"),
    }

    def __init__(self, *args, **kwargs):
        self.search_fields = kwargs.pop("search_fields", ["name"])
        self.rack_filter = kwargs.pop("rack_filter", None)  # 用于限制在特定rack下查找
        super().__init__(*args, **kwargs)

    def to_python(self, value, rack=None):
        """
        将CSV值转换为对象列表

        Args:
            value: CSV中的值（字符串，逗号分隔）
            rack: 可选的Rack对象，用于限制查找范围（用于rack_pdus字段）
        """
        if not value:
            return []

        values = value.split(",") if isinstance(value, str) else value
        objects = []

        if self.queryset.model is ContentType:
            for val in values:
                objects.append(get_content_type_by_labeled_name(val))
            return objects

        # 如果提供了rack参数，限制查找范围
        queryset = self.queryset
        if rack is not None:
            queryset = queryset.filter(rack=rack)

        for val in values:
            try:
                # 构建查询条件
                query = Q()
                for field in self.search_fields:
                    query |= Q(**{field: val.strip()})

                # 尝试查找对象（在限制的queryset中）
                obj = queryset.filter(query).first()
                if obj:
                    objects.append(obj)
                    continue

                # 如果找不到对象，尝试通过ID查找（也在限制的queryset中）
                if val.strip().isdigit():
                    obj = queryset.filter(pk=val.strip()).first()
                    if obj:
                        objects.append(obj)
                        continue

                raise self.queryset.model.DoesNotExist()

            except (ValueError, TypeError, self.queryset.model.DoesNotExist):
                raise forms.ValidationError(
                    self.error_messages["invalid_choice"],
                    code="invalid_choice",
                    params={"value": val},
                )

        return objects


class CSVRackPDUField(CSVModelMultipleChoiceField):
    """
    专门用于rack_pdus字段的CSV导入字段
    限制查找范围在当前行的rack下
    """

    default_error_messages = {
        "invalid_choice": _(
            "未找到匹配的PDU: %(value)s（请确保PDU名称在当前行的机柜下存在）"
        ),
    }

    def to_python(self, value, rack=None):
        """
        将CSV值转换为RackPDU对象列表
        必须在指定的rack下查找

        Args:
            value: CSV中的值（字符串，逗号分隔，如 "A01, B02"）
            rack: Rack对象，必须提供，用于限制查找范围
        """
        if not value:
            return []

        if rack is None:
            raise forms.ValidationError(
                _("rack_pdus字段需要先确定rack值，请确保CSV中包含rack字段")
            )

        # 调用父类方法，传入rack参数
        return super().to_python(value, rack=rack)


def convert_custom_field_value(custom_field, value, request):
    """
    将CSV中的自定义字段值转换为Python对象

    Args:
        custom_field: CustomField 实例
        value: CSV中的原始值（字符串）
        request: 请求对象（用于获取data_center等）

    Returns:
        转换后的值

    Raises:
        ValidationError: 如果值无效
    """
    import json

    if not value or value.strip() == "":
        return None

    value = value.strip()

    try:
        # 根据字段类型转换值
        if custom_field.type == CustomFieldTypeChoices.TYPE_TEXT:
            return value

        elif custom_field.type == CustomFieldTypeChoices.TYPE_LONGTEXT:
            return value

        elif custom_field.type == CustomFieldTypeChoices.TYPE_INTEGER:
            try:
                return int(value)
            except ValueError:
                raise ValidationError(_("值必须是整数"))

        elif custom_field.type == CustomFieldTypeChoices.TYPE_DECIMAL:
            try:
                from decimal import Decimal

                return Decimal(value)
            except (ValueError, Exception):
                raise ValidationError(_("值必须是数字"))

        elif custom_field.type == CustomFieldTypeChoices.TYPE_BOOLEAN:
            try:
                return str2bool(value, raise_exc=True)
            except ValueError:
                raise ValidationError(_("值必须是布尔类型 (true/false)"))

        elif custom_field.type == CustomFieldTypeChoices.TYPE_DATE:
            if value.lower() == "now":
                from datetime import date

                return date.today()
            parsed = dateparser.parse(value)
            if parsed:
                return parsed.date()
            raise ValidationError(_("日期格式无效，应为 YYYY-MM-DD"))

        elif custom_field.type == CustomFieldTypeChoices.TYPE_DATETIME:
            if value.lower() == "now":
                from datetime import datetime

                return datetime.now()
            parsed = dateparser.parse(value)
            if parsed:
                return parsed
            raise ValidationError(_("日期时间格式无效"))

        elif custom_field.type == CustomFieldTypeChoices.TYPE_URL:
            from django.core.validators import URLValidator

            validator = URLValidator()
            try:
                validator(value)
                return value
            except ValidationError:
                raise ValidationError(_("URL格式无效"))

        elif custom_field.type == CustomFieldTypeChoices.TYPE_JSON:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                raise ValidationError(_("JSON格式无效"))

        elif custom_field.type == CustomFieldTypeChoices.TYPE_SELECT:
            # 解析选项
            choices = (
                json.loads(custom_field.choices)
                if isinstance(custom_field.choices, str)
                else custom_field.choices
            )
            if not choices:
                raise ValidationError(_("字段没有定义选项"))
            valid_values = [c[0] for c in choices]
            # 尝试匹配显示值或值
            value_to_key_map = {c[1]: c[0] for c in choices}
            if value in value_to_key_map:
                return value_to_key_map[value]
            elif value in valid_values:
                return value
            else:
                raise ValidationError(_("选项值无效: {value}").format(value=value))

        elif custom_field.type == CustomFieldTypeChoices.TYPE_MULTISELECT:
            # 逗号分隔的多选值
            values = [v.strip() for v in value.split(",") if v.strip()]
            choices = (
                json.loads(custom_field.choices)
                if isinstance(custom_field.choices, str)
                else custom_field.choices
            )
            if not choices:
                raise ValidationError(_("字段没有定义选项"))
            valid_values = [c[0] for c in choices]
            value_to_key_map = {c[1]: c[0] for c in choices}
            result = []
            for v in values:
                if v in value_to_key_map:
                    result.append(value_to_key_map[v])
                elif v in valid_values:
                    result.append(v)
                else:
                    raise ValidationError(_("选项值无效: {value}").format(value=v))
            return result

        elif custom_field.type == CustomFieldTypeChoices.TYPE_OBJECT:
            # 通过名称查找关联对象
            if not custom_field.related_model:
                raise ValidationError(_("字段没有定义关联模型"))
            model = custom_field.related_model.model_class()
            queryset = model.objects.all()
            # 应用过滤参数
            if custom_field.filter_params:
                filter_params = (
                    json.loads(custom_field.filter_params)
                    if isinstance(custom_field.filter_params, str)
                    else custom_field.filter_params
                )
                queryset = queryset.filter(**filter_params)
            # 使用 search_fields 查找
            search_fields = getattr(model, "search_fields", ["name"])
            query = Q()
            for field in search_fields:
                query |= Q(**{field: value})
            obj = queryset.filter(query).first()
            if not obj and value.isdigit():
                obj = queryset.filter(pk=value).first()
            if not obj:
                raise ValidationError(
                    _("未找到匹配的 {model}: {value}").format(
                        model=model._meta.verbose_name, value=value
                    )
                )
            return obj

        elif custom_field.type == CustomFieldTypeChoices.TYPE_MULTIOBJECT:
            # 逗号分隔的多个关联对象
            if not custom_field.related_model:
                raise ValidationError(_("字段没有定义关联模型"))
            model = custom_field.related_model.model_class()
            queryset = model.objects.all()
            # 应用过滤参数
            if custom_field.filter_params:
                filter_params = (
                    json.loads(custom_field.filter_params)
                    if isinstance(custom_field.filter_params, str)
                    else custom_field.filter_params
                )
                queryset = queryset.filter(**filter_params)
            # 使用 search_fields 查找
            search_fields = getattr(model, "search_fields", ["name"])
            values = [v.strip() for v in value.split(",") if v.strip()]
            objects = []
            for val in values:
                query = Q()
                for field in search_fields:
                    query |= Q(**{field: val})
                obj = queryset.filter(query).first()
                if not obj and val.isdigit():
                    obj = queryset.filter(pk=val).first()
                if not obj:
                    raise ValidationError(
                        _("未找到匹配的 {model}: {value}").format(
                            model=model._meta.verbose_name, value=val
                        )
                    )
                objects.append(obj)
            return objects

        else:
            # 默认返回字符串
            return value

    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(_("值转换失败: {error}").format(error=str(e)))
