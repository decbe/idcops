from django import template

register = template.Library()


@register.filter
def get(dictionary, key):
    """获取字典值的过滤器"""
    return dictionary.get(key, "")
