from typing import Any

from django import forms, template

from dcrm.models.customfields import CustomField

register = template.Library()


@register.filter
def startswith(text: str, starts: str) -> bool:
    """检查文本是否以指定字符串开头
    """
    return str(text).startswith(starts)


@register.filter
def get_custom_field_value(obj, field_name: str) -> Any:
    """获取对象的自定义字段值
    """
    return obj.get_custom_field_value(field_name)


@register.filter
def get_custom_field_display(obj, field_name: str) -> str | None:
    """获取对象的自定义字段显示值
    """
    return obj.get_custom_field_display(field_name)


@register.inclusion_tag("customfield/custom_fields_form.html")
def render_custom_fields(form: forms.Form) -> dict[str, list[forms.Field]]:
    """渲染表单中的自定义字段
    """
    return {
        "custom_fields": [
            field for name, field in form.fields.items() if name.startswith("cf_")
        ]
    }


@register.simple_tag
def custom_field_value(obj, field_name: str, default: str = "") -> Any:
    """获取自定义字段值，支持默认值
    """
    return obj.get_custom_field_value(field_name, default)


@register.filter
def custom_field_exists(obj, data_center, field_name: str) -> bool:
    """检查对象是否有指定的自定义字段
    """
    return (
        CustomField.objects.get_for_model(obj.__class__, data_center)
        .filter(name=field_name)
        .exists()
    )


@register.inclusion_tag("customfield/custom_fields_table.html")
def render_custom_fields_table(obj) -> dict[str, list[CustomField]]:
    """渲染对象的所有自定义字段表格
    """
    return {"custom_fields": obj.get_custom_fields()}


@register.filter
def get_custom_field_type(obj, data_center, field_name: str) -> str | None:
    """获取自定义字段的类型
    """
    try:
        cf = CustomField.objects.get_for_model(obj.__class__, data_center).get(
            name=field_name
        )
        return cf.type
    except CustomField.DoesNotExist:
        return None


@register.simple_tag
def custom_field_choices(
    model_class, data_center, field_name: str
) -> list[tuple] | None:
    """获取自定义字段的选项
    """
    return model_class.get_custom_field_choices(data_center, field_name)
