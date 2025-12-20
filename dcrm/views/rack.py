from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from dcrm.forms.rack import RackBaseForm
from dcrm.models.base import LogEntry
from dcrm.models.choices import ChangeActionChoices
from dcrm.models.racks import Rack, RackBulkManager, RackPDU, RackStatus
from dcrm.utilities.serialization import serialize_object

from .mixins.base import BaseRequestMixin
from .mixins.delete import DeleteViewMixin
from .mixins.detail import DetailViewMixin
from .mixins.edit import CreateViewMixin, FieldSet, UpdateViewMixin
from .mixins.list import ListViewMixin


class RackListView(BaseRequestMixin, ListViewMixin, ListView):
    """
    机柜列表视图
    """

    model = Rack
    list_fields = [
        "name",
        "room",
        "status",
        "rack_type",
        "tenant",
        "opening_date",
        "contract_power",
        "space_usage",
        "u_height",
        "pdu_count",
        "tags",
    ]
    stats_fields = ["status", "rack_type"]

    # 定义可用于过滤的日期字段
    date_filter_fields = [
        ("created_at", "创建时间"),
        ("updated_at", "更新时间"),
        ("last_seen", "最后在线"),
    ]

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.with_space_usage()


class RackDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    """机柜详情视图"""

    model = Rack
    template_name = "rack/detail.html"
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": [
                "room",
                "name",
                "rack_type",
                "status",
                "space_usage",
                "tenant",
                "opening_date",
                "contract_power",
                "u_height",
                "pdu_count",
                "pdu_16a_count",
                "description",
                "tags",
            ],
            "description": _("机柜的基本信息，包括名称、类型、状态等"),
        },
        {
            "title": _("电力&尺寸"),
            "fields": [
                "rated_power_kw",
                "rated_current",
                "voltage",
                "depth",
                "width",
                "height",
            ],
            "description": _("机柜的物理规格参数和电力配置"),
        },
    ]


class RackCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    """机柜创建视图"""

    model = Rack
    form_class = RackBaseForm
    template_name = "rack/create.html"

    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "room",
                "rack_type",
                "name",
                "u_height",
                "pdu_count",
                "pdu_16a_count",
                "tags",
            ],
            description=_("机柜名称、高度(U)、类型、PDU数量等"),
            inline_groups=[
                ["room", "rack_type"],
                ["u_height", "pdu_count", "pdu_16a_count"],
            ],
        ),
        FieldSet(
            name=_("功率 & 尺寸"),
            fields=["rated_current", "voltage", "depth", "width", "height"],
            description=_("机柜电力，外观尺寸等信息"),
            inline_groups=[["rated_current", "voltage"], ["depth", "width", "height"]],
        ),
    ]

    def form_valid(self, form):
        """处理表单验证成功的情况"""
        if form.cleaned_data.get("use_regex_pattern") == "1" and form._expanded_names:
            try:
                # 创建基础实例但不保存
                self.object = form.save(commit=False)

                # 保存tags值供后续使用
                tags = form.cleaned_data.get("tags", [])
                exclude_fields = [
                    "data_center",
                    "name",
                    "use_regex_pattern",
                    "room",
                    "tags",
                ]
                # 准备批量创建的实例
                defaults = {
                    field: value
                    for field, value in form.cleaned_data.items()
                    if field not in exclude_fields and value is not None
                }
                defaults["created_by"] = self.request.user
                instances = RackBulkManager.bulk_create_from_regex(
                    pattern=form.cleaned_data["name"],
                    data_center=self.request.user.data_center,
                    room=form.cleaned_data["room"],
                    **defaults,
                )

                # 为每个实例设置tags
                if tags:
                    for instance in instances:
                        instance.tags.set(tags)
                # 记录日志
                for instance in instances:
                    LogEntry.objects.log_action(
                        user=self.request.user,
                        action=ChangeActionChoices.CREATE,
                        object_repr=instance,
                        message=f"{self.success_message}: ({str(instance)})",
                        created_at=timezone.now(),
                        prechange_data={},
                        postchange_data=serialize_object(instance),
                    )

                self.object = instances[0]  # 设置第一个实例作为代表
                return HttpResponseRedirect(self.get_success_url())

            except Exception as e:
                form.add_error(None, str(e))
                return self.form_invalid(form)

        return super().form_valid(form)


class RackUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = Rack
    form_class = RackBaseForm

    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "room",
                "rack_type",
                "name",
                "u_height",
                "pdu_count",
                "pdu_16a_count",
                "tags",
            ],
            description=_("机柜名称、高度(U)、类型、PDU数量等"),
            inline_groups=[
                ["room", "rack_type"],
                ["u_height", "pdu_count", "pdu_16a_count"],
            ],
        ),
        FieldSet(
            name=_("分配信息"),
            fields=["tenant", "status", "contract_power", "opening_date"],
            description=_("分配租户、状态、合同功率等信息"),
            inline_groups=[["tenant", "status"], ["contract_power", "opening_date"]],
        ),
        FieldSet(
            name=_("功率 & 尺寸"),
            fields=["rated_current", "voltage", "depth", "width", "height"],
            description=_("机柜电力，外观尺寸，标签等信息"),
            inline_groups=[["rated_current", "voltage"], ["depth", "width", "height"]],
        ),
    ]


class RackDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """机柜删除视图"""

    model = Rack
    success_message = _("机柜已删除")

    def get_success_url(self):
        return reverse("rack_list")


class RackPDUListView(BaseRequestMixin, ListViewMixin, ListView):
    model = RackPDU
    list_fields = [
        "name",
        "slot_type",
        "rack",
        "status",
    ]


class RackPDUCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = RackPDU
    fields = ["name", "status", "slot_type", "rack"]


class RackPDUUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = RackPDU
    fields = ["name", "status", "slot_type", "rack"]


class RackPDUDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    """机柜 PDU 详情视图"""

    model = RackPDU
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": ["rack", "name", "slot_type", "status"],
            "description": _("PDU 的基本信息"),
        }
    ]


class RackPDUDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """机柜PDU删除视图"""

    model = RackPDU
    success_message = _("机柜PDU已删除")

    def get_success_url(self):
        return reverse("rackpdu_list")


class RackStatusListView(BaseRequestMixin, ListViewMixin, ListView):
    model = RackStatus
    list_fields = [
        "name",
        "description",
        "color_with_html",
        "allowed_mount",
        "shared",
        "tags",
    ]


class RackStatusCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = RackStatus
    fields = ["name", "color", "description", "allowed_mount", "shared", "tags"]


class RackStatusUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = RackStatus
    fields = ["name", "color", "description", "allowed_mount", "shared", "tags"]


class RackStatusDetailView(BaseRequestMixin, DetailViewMixin, DetailView):

    model = RackStatus
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": [
                "name",
                "color",
                "color_with_html",
                "description",
                "allowed_mount",
                "shared",
                "tags",
            ],
            "description": _("机柜状态的基本信息"),
        }
    ]


class RackStatusDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):

    model = RackStatus
    success_message = _("机柜PDU已删除")

    def get_success_url(self):
        return reverse("rack_status_list")
