from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.urls import reverse

from .base import camel_to_snake


def get_object_display(obj):
    """获取对象的显示值和详情URL

    Args:
        obj: 模型实例对象
    opts = obj._meta

    Returns:
        tuple: (field_name, display_value, detail_url)

    """
    opts = obj._meta
    display_value = None

    # 1. 检查是否有 get_absolute_url
    if hasattr(obj, "get_absolute_url"):
        detail_url = obj.get_absolute_url()
    else:
        try:
            detail_url = reverse(
                f"{camel_to_snake(opts.object_name)}_detail", kwargs={"pk": obj.pk}
            )
        except Exception:
            detail_url = None

    # 2. 检查模型是否指定了显示字段
    if hasattr(obj.__class__, "display_link_field"):
        field_name = getattr(obj.__class__, "display_link_field")
        try:
            # 支持方法、属性和字段
            attr = getattr(obj, field_name)
            display_value = attr() if callable(attr) else attr
            return field_name, str(display_value), detail_url
        except (AttributeError, FieldDoesNotExist):
            pass

    # 3. 查找带 unique 且不为空的自带字段
    field_types = (models.CharField, models.SlugField)
    for is_unique in (True, False):  # 先找唯一字段，再找非唯一字段
        for field in opts.fields:
            if (
                isinstance(field, field_types)
                and not field.blank
                and field.unique == is_unique
            ):
                if value := getattr(obj, field.name):
                    return field.name, str(value), detail_url

    # 4. 查找常用字段
    common_fields = ["name", "title", "label", "code", "slug"]
    for name in common_fields:
        try:
            field = opts.get_field(name)
            display_value = getattr(obj, name)
            return name, str(display_value), detail_url
        except FieldDoesNotExist:
            continue

    # 5. 使用第一个字符字段
    for field in opts.fields:
        if isinstance(field, models.CharField):
            display_value = getattr(obj, field.name)
            return field.name, str(display_value), detail_url

    # 6. 最后使用 __str__
    return None, str(obj), detail_url
