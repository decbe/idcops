from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from dcrm.models import Tag

from .mixins.base import BaseRequestMixin
from .mixins.delete import DeleteViewMixin
from .mixins.detail import DetailViewMixin
from .mixins.edit import CreateViewMixin, FieldSet, UpdateViewMixin
from .mixins.list import ListViewMixin


class TagListView(BaseRequestMixin, ListViewMixin, ListView):
    model = Tag
    list_fields = [
        "name",
        "color_with_html",
        "object_types",
        "parent",
        "shared",
        "data_center",
    ]


class TagCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = Tag
    fields = [
        "object_types",
        "name",
        "description",
        "color",
        "shared",
        "parent",
    ]
    fieldsets = [
        FieldSet(
            name="基本信息",
            fields=["object_types", "name", "description", "color", "shared", "parent"],
        ),
    ]


class TagUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = Tag
    fields = [
        "object_types",
        "name",
        "description",
        "color",
        "shared",
        "parent",
    ]
    fieldsets = [
        FieldSet(
            name="基本信息",
            fields=["object_types", "name", "description", "color", "shared", "parent"],
        ),
    ]


class TagDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = Tag
    fields = "__all__"

    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": [
                "name",
                "object_types",
                "color_with_html",
                "description",
                "shared",
                "parent",
            ],
            "description": _(
                "标签的基本信息，包括名称、颜色、描述、共享状态和父级标签"
            ),
        }
    ]


class TagDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    model = Tag
