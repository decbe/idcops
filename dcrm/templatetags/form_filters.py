from django import template
from django.forms import BooleanField, BoundField, DateInput, Select

register = template.Library()


@register.filter
def is_select_field(field):
    return isinstance(field.field.widget, Select)


@register.filter
def is_date_field(field):
    return isinstance(field.field.widget, DateInput)


@register.filter
def is_boolean_field(field):
    return isinstance(field.field, BooleanField)


@register.filter
def fieldtype(field):
    """返回字段类型名称作为字符串"""
    return field.field.__class__.__name__


@register.filter
def normal_field_count(form):
    """计算非按钮组类型字段的数量"""
    return sum(
        1 for field in form if not getattr(field.field, "is_button_group", False)
    )


@register.filter
def get_field(form, field_name: str) -> BoundField:
    """获取表单字段"""
    try:
        return form[field_name]
    except KeyError:
        return None
