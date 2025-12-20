from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from ..models import LogEntry
from .mixins.base import BaseRequestMixin
from .mixins.delete import DeleteViewMixin
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
