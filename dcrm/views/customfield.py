from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from dcrm.forms.customfields import CustomFieldBaseForm
from dcrm.models import CustomField

from .mixins.base import BaseRequestMixin
from .mixins.delete import DeleteViewMixin
from .mixins.detail import DetailViewMixin
from .mixins.edit import CreateViewMixin, FieldSet, UpdateViewMixin
from .mixins.list import ListViewMixin


class CustomFieldListView(BaseRequestMixin, ListViewMixin, ListView):
    model = CustomField
    list_fields = [
        "name",
        "label",
        "description",
        "type",
        "required",
        "unique",
        "ui_visible",
        "is_active",
    ]


class CustomFieldDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = CustomField
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": ["name", "label", "type", "required"],
            "description": _("自定义字段的基本信息"),
        },
        {
            "title": _("字段配置"),
            "fields": ["description", "default", "choices"],
            "description": _("字段的详细配置信息"),
        },
        {
            "title": _("验证配置"),
            "fields": [
                "unique",
                "validation_minimum",
                "validation_maximum",
                "validation_regex",
            ],
            "description": _("字段的验证配置信息"),
        },
        {
            "title": _("关联信息"),
            "fields": ["object_types", "ui_visible"],
            "description": _("字段的关联对象类型和UI显示设置"),
        },
    ]


class CustomFieldCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = CustomField
    form_class = CustomFieldBaseForm
    fields = [
        "name",
        "label",
        "type",
        "required",
        "description",
        "default",
        "choices",
        "unique",
        "validation_minimum",
        "validation_maximum",
        "validation_regex",
        "object_types",
        "ui_visible",
        "related_model",
        "filter_params",
        "order",
    ]
    fieldsets = (
        FieldSet(
            name=_("基本信息"),
            fields=[
                "object_types",
                "type",
                "name",
                "label",
                "description",
                "ui_visible",
                "order",
            ],
        ),
        FieldSet(
            name=_("字段验证配置"),
            fields=[
                "required",
                "unique",
                "validation_minimum",
                "validation_maximum",
                "validation_regex",
                "related_model",
                "filter_params",
                "choices",
                "default",
            ],
        ),
    )


class CustomFieldUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = CustomField
    form_class = CustomFieldBaseForm
    fields = [
        "name",
        "label",
        "type",
        "required",
        "description",
        "default",
        "choices",
        "unique",
        "validation_minimum",
        "validation_maximum",
        "validation_regex",
        "object_types",
        "ui_visible",
        "related_model",
        "filter_params",
        "order",
    ]
    fieldsets = (
        FieldSet(
            name=_("基本信息"),
            fields=[
                "object_types",
                "type",
                "name",
                "label",
                "description",
                "ui_visible",
                "order",
            ],
        ),
        FieldSet(
            name=_("字段验证配置"),
            fields=[
                "required",
                "unique",
                "validation_minimum",
                "validation_maximum",
                "validation_regex",
                "related_model",
                "filter_params",
                "choices",
                "default",
            ],
        ),
    )


class CustomFieldDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    model = CustomField
    success_message = _("自定义字段已删除")

    def get_success_url(self):
        return reverse("custom_field_list")
