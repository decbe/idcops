from django.views.generic import (
    DetailView,
    ListView,
)

from ..models import LogEntry
from .mixins.base import BaseRequestMixin
from .mixins.detail import DetailViewMixin
from .mixins.list import ListViewMixin


class LogEntryListView(BaseRequestMixin, ListViewMixin, ListView):
    model = LogEntry
    list_fields = [
        "timestamp",
        "created_at",
        "created_by",
        "action",
        "content_type",
        "message",
    ]


class LogEntryDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = LogEntry
    fields = "__all__"
