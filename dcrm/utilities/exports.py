import csv
from itertools import chain
from urllib.parse import quote

from django.http import HttpResponse, StreamingHttpResponse
from django.utils import formats, timezone
from django.utils.text import slugify

from dcrm.constants import DOWNLOAD_ENABLED_STREAMING
from dcrm.models import CustomField

from .lookup import LookupFields


def get_export_queryset(queryset):
    """
    针对常见外键和多对多字段做优化，减少N+1查询。
    可根据实际模型字段调整。
    """
    model = queryset.model
    fk_fields = [
        f.name
        for f in model._meta.fields
        if (f.is_relation and f.many_to_one and not f.auto_created)
    ]
    m2m_fields = [f.name for f in model._meta.many_to_many if not f.auto_created]
    if fk_fields:
        queryset = queryset.select_related(*fk_fields)
    if m2m_fields:
        queryset = queryset.prefetch_related(*m2m_fields)
    return queryset


class CSVBuffer:
    """An object that implements just the write method of the file-like
    interface.
    """

    def write(self, value):
        """Return the string to write."""
        return value


def export_data_with_stream(queryset, data_center, fields=None, charset="utf-8"):
    # 获取queryset的model
    queryset = get_export_queryset(queryset)
    model = queryset.model
    exclude_fields = [
        "_password",
        "password",
        "custom_field_data",
        "metadata",
        "extra_data",
    ]
    # 获取model的fields
    custom_fields = CustomField.objects.none()
    if hasattr(model, "data_center") and hasattr(model, "custom_field_data"):
        custom_fields = CustomField.objects.get_for_model(model, data_center)
    if fields is None:
        fields = [
            field.name
            for field in model._meta.fields + model._meta.many_to_many
            if field.name not in exclude_fields
        ]
        if custom_fields:
            custom_field_names = [f"{field.name}" for field in custom_fields]
            fields += custom_field_names
    # verbose_name
    verbose_name = model._meta.verbose_name
    lookup = LookupFields(
        model, fields, custom_fields, empty_value_display="", primary_link=False
    )
    labels = lookup.get_field_labels()
    time = formats.localize(timezone.template_localtime(timezone.datetime.now()))
    filename = quote("{}{}.csv".format(verbose_name, slugify(time, allow_unicode=True)))
    content_type = f"application/octet-stream; charset={charset}"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-cache",
    }
    if queryset.count() <= DOWNLOAD_ENABLED_STREAMING:
        # 使用 HttpResponse
        response = HttpResponse(content_type=content_type, headers=headers)
        writer = csv.writer(response)
        writer.writerow(labels.values())
        writer.writerow(labels.keys())
        writer.writerows(
            [lookup.get_field_values(item, html=False).values() for item in queryset]
        )
        return response

    # 使用 StreamingHttpResponse
    writer = csv.writer(CSVBuffer())
    _rows = (
        lookup.get_field_values(item, html=False).values()
        for item in queryset.iterator(chunk_size=DOWNLOAD_ENABLED_STREAMING)
    )
    rows = chain([labels.values(), labels.keys()], _rows)
    return StreamingHttpResponse(
        (writer.writerow(row) for row in rows),
        content_type=content_type,
        headers=headers,
    )
