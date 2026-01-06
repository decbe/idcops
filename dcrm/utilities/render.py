import json

from django.db import models
from django.utils.html import format_html

from dcrm.constants import MAX_PAGE_SIZE
from dcrm.models.choices import CustomFieldTypeChoices
from dcrm.utilities.lookup import LookupFields


def render_custom_field_value(custom_field, value):
    """根据提供的 custom_field 和 value 渲染前端显示的值.
    custom_field CustomField instance
    value get_custom_field_value
    """
    # 处理不同类型的自定义字段值
    if value is not None:
        if custom_field.type == CustomFieldTypeChoices.TYPE_BOOLEAN:
            return format_html(
                '<i class="fa fa-{} text-{}"></i>',
                "check-circle" if value else "times-circle",
                "success" if value else "danger",
            )
        elif custom_field.type in (
            CustomFieldTypeChoices.TYPE_SELECT,
            CustomFieldTypeChoices.TYPE_MULTISELECT,
        ):
            choices = (
                json.loads(custom_field.choices)
                if isinstance(custom_field.choices, str)
                else custom_field.choices
            )
            choices_dict = dict(choices)
            if isinstance(value, list):
                return ", ".join(choices_dict.get(v, str(v)) for v in value)
            return choices_dict.get(value, str(value))
        elif custom_field.type in (
            CustomFieldTypeChoices.TYPE_OBJECT,
            CustomFieldTypeChoices.TYPE_MULTIOBJECT,
        ):
            model = custom_field.related_model.model_class()
            if isinstance(value, list):
                objects = model.objects.filter(pk__in=value)
                return ", ".join(str(obj) for obj in objects)
            else:
                try:
                    related_obj = model.objects.get(pk=value)
                    return format_html(
                        '<a href="{}">{}</a>',
                        related_obj.get_absolute_url(),
                        str(related_obj),
                    )
                except model.DoesNotExist:
                    return ""
        return str(value)
    return ""


def render_pagination(total_count, paginate_by):
    if total_count < paginate_by:
        return False
    range_list = [10, 20, 50, min(total_count, MAX_PAGE_SIZE)]
    ranges = "".join(
        [f'<li><a href="?page={page}">每页显示{page}条</a></li>' for page in range_list]
    )
    return ranges


def model_headers_in_table(model):
    """模型所有字段名
    """
    headers = []
    opts = model._meta
    for field in opts.fields:
        headers.append(
            dict(
                name=field.name,
                type=field.get_internal_type(),
                label=field.verbose_name,
            )
        )
    return headers


def render_object_as_html(instance: models.Model, fields: list[str]):
    """不支持自定义字段的渲染
    将模型实例对象渲染成前端
    """
    lookup = LookupFields(instance.__class__, fields, primary_link=False)
    data = []
    for field_name in fields:
        data.append(
            dict(
                name=field_name,
                label=lookup.get_field_label(field_name),
                value=lookup.get_field_value_as_str(instance, field_name),
            )
        )
    return data


def render_objects(queryset, fields, html=True):
    lookup = LookupFields(queryset.model, fields, primary_link=False)
    if html:
        get_value = lookup.get_field_value
    else:
        get_value = lookup.get_field_value_as_str
    # 表头
    yield lookup.get_field_labels()
    for obj in queryset:
        cell = []
        for field_name in fields:
            cell.append(
                {
                    "name": field_name,
                    "label": lookup.get_field_label(field_name),
                    "value": get_value(obj, field_name),
                }
            )
        yield cell
