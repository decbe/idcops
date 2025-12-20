from django.contrib import messages
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
    View,
)

from dcrm.forms.datacenter import DataCenterForm
from dcrm.models import DataCenter

from .mixins.base import BaseRequestMixin
from .mixins.delete import DeleteViewMixin
from .mixins.detail import DetailViewMixin
from .mixins.edit import CreateViewMixin, FieldSet, UpdateViewMixin
from .mixins.list import ListViewMixin


class DataCenterListView(BaseRequestMixin, ListViewMixin, ListView):
    model = DataCenter
    list_fields = [
        "name",
        "description",
        "duty_type",
        "group",
        "is_active",
        "physical_address",
        "shipping_address",
        "latitude",
        "longitude",
        "contact_name",
        "contact_phone",
        "contact_email",
        "security_level",
    ]


class DataCenterDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = DataCenter
    fields = "__all__"


class DataCenterCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = DataCenter
    form_class = DataCenterForm
    success_url = reverse_lazy("index")
    fields = [
        "name",
        "group",
        "security_level",
        "duty_type",
        "description",
        "physical_address",
        "shipping_address",
        "contact_name",
        "contact_phone",
        "contact_email",
    ]
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            description=("该数据中心的基本信息"),
            fields=["name", "group", "security_level", "duty_type", "description"],
        ),
        FieldSet(
            name=_("位置&联系信息"),
            description=_("数据中心的地理位置与联系信息"),
            fields=[
                "physical_address",
                "shipping_address",
                "contact_name",
                "contact_phone",
                "contact_email",
            ],
        ),
    ]

    def form_valid(self, form):
        user = self.request.user
        form.instance.created_by = user
        datacenter = form.save()
        # 切换到新数据中心
        user.data_center = datacenter
        user.data_centers.add(datacenter)
        user.save(update_fields=["data_center"])
        messages.success(self.request, _("恭喜你，成功创建了一个新的数据中心"))
        return super().form_valid(form)


class DataCenterUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = DataCenter
    form_class = DataCenterForm
    success_url = reverse_lazy("index")
    fields = [
        "name",
        "group",
        "security_level",
        "duty_type",
        "description",
        "physical_address",
        "shipping_address",
        "contact_name",
        "contact_phone",
        "contact_email",
    ]
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            description=("该数据中心的基本信息"),
            fields=["name", "group", "security_level", "duty_type", "description"],
        ),
        FieldSet(
            name=_("位置&联系信息"),
            description=_("数据中心的地理位置与联系信息"),
            fields=[
                "physical_address",
                "shipping_address",
                "contact_name",
                "contact_phone",
                "contact_email",
            ],
        ),
    ]


class DataCenterDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    model = DataCenter
    success_url = reverse_lazy("index")
