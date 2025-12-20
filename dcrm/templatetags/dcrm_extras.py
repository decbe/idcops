from django import template
from django.apps import apps

from dcrm.utilities.render import render_object_as_html

register = template.Library()


@register.filter
def multiply(value, arg):
    """Multiplies the arg and value"""
    return value * arg


@register.filter
def get_item(dictionary, key):
    """通过键获取字典中的值，或列表按索引获取"""
    if dictionary is None:
        return None
    try:
        # 支持列表索引
        if isinstance(dictionary, (list, tuple)) and str(key).isdigit():
            return dictionary[int(key)]
        return dictionary.get(key)
    except Exception:
        return None


@register.filter
def split(value, separator):
    """拆分字符串"""
    if not value or not isinstance(value, str):
        return []
    return value.split(separator)


# 改用 inclusion_tag 的标签直接渲染 html模板
@register.inclusion_tag("generic/object_detail_as_html.html")
def object_as_html(model, instance, fields):
    model = apps.get_model("dcrm", model)
    obj = model.objects.get(pk=int(instance))
    data = render_object_as_html(obj, fields)
    return {"data": data}
