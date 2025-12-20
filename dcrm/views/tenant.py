from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from dcrm.models import Contact, ContactRole, Manufacturer, Tenant

from .mixins.base import BaseRequestMixin
from .mixins.delete import DeleteViewMixin
from .mixins.detail import DetailViewMixin
from .mixins.edit import CreateViewMixin, FieldSet, UpdateViewMixin
from .mixins.list import ListViewMixin


class TenantListView(BaseRequestMixin, ListViewMixin, ListView):
    model = Tenant
    list_fields = [
        "name",
        "type",
        "icon_with_html",
        "description",
        "address",
        "website",
        "tags",
    ]


class TenantDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = Tenant
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": [
                "name",
                "icon_with_html",
                "description",
                "type",
                "website",
                "tags",
            ],
            "description": _("租户的基本信息"),
        },
        {
            "title": _("联系信息"),
            "fields": ["address", "contacts", "latitude", "longitude"],
            "description": _("租户的联系方式和地址信息"),
        },
    ]


class TenantCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = Tenant
    fields = [
        "name",
        "type",
        "description",
        "address",
        "contacts",
        "website",
        "icon",
        "tags",
    ]
    fieldsets = (
        FieldSet(
            name=_("基本信息"),
            description=_("租户名称、类型、描述等信息"),
            fields=["name", "type", "description", "tags"],
        ),
        FieldSet(
            name=_("联系&标识"),
            description=_("租户联系人、地址、网址等信息"),
            fields=["address", "contacts", "website", "icon"],
        ),
    )


class TenantUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = Tenant
    fields = [
        "name",
        "type",
        "description",
        "address",
        "contacts",
        "website",
        "icon",
        "tags",
    ]
    fieldsets = (
        FieldSet(
            name=_("基本信息"),
            description=_("租户名称、类型、描述等信息"),
            fields=["name", "type", "description", "tags"],
        ),
        FieldSet(
            name=_("联系&标识"),
            description=_("租户联系人、地址、网址等信息"),
            fields=["address", "contacts", "website", "icon"],
        ),
    )


class TenantDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """租户删除视图"""

    model = Tenant
    success_message = _("租户已删除")

    def get_success_url(self):
        return reverse("tenant_list")


# Contact Views
class ContactListView(BaseRequestMixin, ListViewMixin, ListView):
    model = Contact
    list_fields = ["name", "phone", "email", "address", "role"]


class ContactDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = Contact
    fields = "__all__"
    fieldsets = [
        {
            "title": _("联系人信息"),
            "fields": ["name", "role", "phone", "email", "address", "tags"],
            "description": _("联系人的基本信息"),
        }
    ]


class ContactCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = Contact
    fields = ["name", "phone", "email", "address", "role", "tags"]
    fieldsets = (
        FieldSet(
            name=_("基本信息"),
            fields=["name", "phone", "email", "address", "role", "tags"],
        ),
    )


class ContactUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = Contact
    fields = ["name", "phone", "email", "address", "role", "tags"]
    fieldsets = (
        FieldSet(
            name=_("基本信息"),
            fields=["name", "phone", "email", "address", "role", "tags"],
        ),
    )


class ContactDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """联系人删除视图"""

    model = Contact
    success_message = _("联系人已删除")

    def get_success_url(self):
        return reverse("contact_list")


# Manufacturer Views
class ManufacturerListView(BaseRequestMixin, ListViewMixin, ListView):
    model = Manufacturer
    list_fields = [
        "name",
        "name_cn",
        "icon_with_html",
        "description",
        "website",
        "shared",
        "data_center",
    ]


class ManufacturerDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = Manufacturer
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": ["name", "name_cn", "icon_with_html", "description"],
            "description": _("制造商的基本信息"),
        },
        {
            "title": _("其他信息"),
            "fields": ["website", "shared", "tags"],
            "description": _("制造商的其他信息"),
        },
    ]


class ManufacturerCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = Manufacturer
    fields = ["name", "name_cn", "description", "website", "shared", "tags", "icon"]
    fieldsets = (
        FieldSet(
            name=_("基本信息"),
            fields=[
                "name",
                "name_cn",
                "description",
                "website",
                "shared",
                "tags",
                "icon",
            ],
        ),
    )


class ManufacturerUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = Manufacturer
    fields = ["name", "name_cn", "description", "website", "shared", "tags", "icon"]
    fieldsets = (
        FieldSet(
            name=_("基本信息"),
            fields=[
                "name",
                "name_cn",
                "description",
                "website",
                "shared",
                "tags",
                "icon",
            ],
        ),
    )


class ManufacturerDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """制造商删除视图"""

    model = Manufacturer
    success_message = _("制造商已删除")

    def get_success_url(self):
        return reverse("manufacturer_list")


# ContactRole Views
class ContactRoleListView(BaseRequestMixin, ListViewMixin, ListView):
    model = ContactRole
    list_fields = ["name", "description", "contact_count", "tags"]


class ContactRoleDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = ContactRole
    fields = "__all__"
    fieldsets = [
        {
            "title": _("联系人角色信息"),
            "fields": ["name", "description", "contact_count", "tags"],
            "description": _("联系人角色的基本信息"),
        }
    ]


class ContactRoleCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = ContactRole
    fields = ["name", "description", "tags"]
    fieldsets = (FieldSet(name=_("基本信息"), fields=["name", "description", "tags"]),)


class ContactRoleUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = ContactRole
    fields = ["name", "description", "tags"]
    fieldsets = (
        FieldSet(
            name=_("基本信息"),
            fields=["name", "description", "tags"],
        ),
    )


class ContactRoleDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """联系人角色删除视图"""

    model = ContactRole
    success_message = _("联系人角色已删除")

    def get_success_url(self):
        return reverse("contactrole_list")
