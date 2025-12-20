from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from dcrm.forms.codingrules import CodingRuleBaseForm
from dcrm.models.codingrule import CodingRule

from .mixins.base import BaseRequestMixin
from .mixins.delete import DeleteViewMixin
from .mixins.detail import DetailViewMixin
from .mixins.edit import CreateViewMixin, FieldSet, UpdateViewMixin
from .mixins.list import ListViewMixin


class CodingRuleListView(BaseRequestMixin, ListViewMixin, ListView):
    model = CodingRule
    list_fields = [
        "name",
        "content_type",
        "to_field",
        "prefix",
        "start_at",
        "suffix",
        "capacity",
        "used_amount",
        "available_next_number",
    ]


class CodingRuleDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = CodingRule
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": [
                "name",
                "content_type",
                "to_field",
                "prefix",
                "start_at",
                "suffix",
                "capacity",
                "used_amount",
                "available_next_number",
            ],
            "description": _("编码规则的基本信息"),
        }
    ]


class CodingRuleCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = CodingRule
    form_class = CodingRuleBaseForm
    fields = [
        "content_type",
        "to_field",
        "name",
        "prefix",
        "start_at",
        "suffix",
        "height",
        "width",
        "description",
    ]
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "content_type",
                "to_field",
                "name",
                "prefix",
                "start_at",
                "suffix",
                "description",
            ],
            description=_("编码规则的基本信息"),
        ),
        FieldSet(
            name=_("打印尺寸"),
            fields=["height", "width"],
            description=_("编码规则的打印尺寸"),
            inline_groups=[
                ["height", "width"],
            ],
        ),
    ]


class CodingRuleUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = CodingRule
    form_class = CodingRuleBaseForm
    fields = [
        "content_type",
        "to_field",
        "name",
        "prefix",
        "start_at",
        "suffix",
        "height",
        "width",
        "description",
    ]
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "content_type",
                "to_field",
                "name",
                "prefix",
                "start_at",
                "suffix",
                "description",
            ],
            description=_("编码规则的基本信息"),
        ),
        FieldSet(
            name=_("打印尺寸"),
            fields=["height", "width"],
            description=_("编码规则的打印尺寸"),
            inline_groups=[
                ["height", "width"],
            ],
        ),
    ]


class CodingRuleDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    model = CodingRule
    success_url = reverse_lazy("coding_rule_list")
