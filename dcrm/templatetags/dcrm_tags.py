from django import template

register = template.Library()


@register.filter
def startswith(value, arg):
    """
    检查字符串是否以特定字符开始
    用法: {% if value|startswith:"<table" %}
    """
    return str(value).startswith(str(arg))
