from django.db.models import Case, IntegerField, QuerySet, When
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from dcrm.forms.patchcords import PatchCordForm, PatchCordNodeFormSet
from dcrm.models import DevicePort
from dcrm.models.choices import (
    DevicePortStatusChoices,
    DevicePortTypeChoices,
    PatchCordStatusChoices,
    RackTypeChoices,
)
from dcrm.models.patchcords import PatchCord, PatchCordNode
from dcrm.signals.signals import patch_cord_status_changed

from .mixins.base import BaseRequestMixin
from .mixins.delete import DeleteViewMixin
from .mixins.detail import DetailViewMixin
from .mixins.edit import CreateViewMixin, UpdateViewMixin
from .mixins.list import ListViewMixin


class PatchCordListView(BaseRequestMixin, ListViewMixin, ListView):
    """跳线列表视图"""

    model = PatchCord
    template_name = "patchcord/list.html"
    list_fields = [
        "identifier",
        "cable_label",
        "network_product",
        "bandwidth",
        "cable_type",
        "status",
        "length",
        "node_count",
        "full_nodes",
        "tags",
    ]

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().prefetch_related("nodes")


class PatchCordDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    """跳线详情视图"""

    model = PatchCord
    template_name = "patchcord/detail.html"
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": [
                "identifier",
                "full_nodes",
                "network_product",
                "bandwidth",
                "cable_label",
                "cable_type",
                "status",
                "node_count",
                "length",
                "description",
                "tags",
            ],
            "description": _("跳线的基本标识和网络信息"),
        }
    ]

    def get_queryset(self):
        return super().get_queryset().prefetch_related("nodes")

    def get_template_names(self):
        """获取模板名称

        模板查找顺序：
        1. app_label/model_name/detail.html
        2. model_name/detail.html
        3. base/detail.html
        """
        # model_name = camel_to_snake(self.model._meta.object_name)
        return self.template_name

    def get_context_data(self, **kwargs):
        """添加内联表单集到上下文"""
        context = super().get_context_data(**kwargs)
        context["nodes"] = self.object.nodes.all().order_by("sequence")
        return context


class PatchCordCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    """跳线创建视图"""

    model = PatchCord
    form_class = PatchCordForm
    template_name = "patchcord/form.html"

    def get_success_url(self):
        return reverse("patch_cord_detail", kwargs={"pk": self.object.pk})

    def get_pre_add_nodes(self):
        """获取预填充的节点数据"""
        # 从URL获取端口ID列表
        port_ids = self.request.GET.get("ports", "").split(",")
        pre_add = self.request.GET.get("pre_add", None)
        if not port_ids or not port_ids[0]:
            return None

        # 过滤掉非数字的端口ID
        port_ids = [int(pid) for pid in port_ids if pid.isdigit()]
        if not port_ids:
            return None

        # 创建自定义排序条件
        preserved_order = Case(
            *[When(id=pk, then=pos) for pos, pk in enumerate(port_ids)],
            output_field=IntegerField(),
        )

        ports = DevicePort.objects.filter(
            pk__in=port_ids, status=DevicePortStatusChoices.DISCONNECTED
        ).select_related("device__rack", "device__tenant").order_by(preserved_order)

        if not ports or pre_add is None:
            return None

        # 构造formset初始数据
        port_count = len(ports) if len(ports) >= 2 else 2

        formset_data = {
            "nodes-TOTAL_FORMS": str(port_count),
            "nodes-INITIAL_FORMS": "0",
            "nodes-MIN_NUM_FORMS": "2",
            "nodes-MAX_NUM_FORMS": "10",
        }

        # default_color = ColorChoices.get_default_color()

        # 为每个端口构造表单数据
        for index, port in enumerate(ports):
            port_type = (
                "sfp" if port.port_type == DevicePortTypeChoices.FIBER else "rj45"
            )
            node_type = (
                "patch_panel"
                if port.device.rack.rack_type == RackTypeChoices.PATCH_PANEL
                else "device"
            )
            prefix = f"nodes-{index}-"
            formset_data.update(
                {
                    f"{prefix}sequence": str(index),
                    f"{prefix}node_type": node_type,
                    f"{prefix}port_type": port_type,
                    f"{prefix}rack": str(port.device.rack.id),
                    f"{prefix}rack_unit": str(port.device.position),
                    f"{prefix}device": str(port.device.id),
                    f"{prefix}port_name": port,
                    f"{prefix}tenant": str(port.device.tenant.id),
                }
            )
        return formset_data

    def get_context_data(self, **kwargs):
        """添加内联表单集到上下文"""
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["formset"] = PatchCordNodeFormSet(
                self.request.POST, form_kwargs={"request": self.request}
            )
        else:

            formset_data = self.get_pre_add_nodes()
            if formset_data:
                formset = PatchCordNodeFormSet(
                    data=formset_data, form_kwargs={"request": self.request}
                )
            else:
                formset = PatchCordNodeFormSet(form_kwargs={"request": self.request})
            context["formset"] = formset
        context["is_create"] = self.object is None
        return context

    def form_valid(self, form):
        """保存表单和内联表单集"""
        context = self.get_context_data()
        formset = context["formset"]

        if formset.is_valid():
            self.object = form.save(commit=False)
            self.object.node_count = len(formset.cleaned_data) - len(
                formset.deleted_forms
            )
            miss_node = self.object.node_count > 0 and self.object.node_count % 2 != 0

            length = (
                sum([form.get("length", 0) for form in formset.cleaned_data[:-1]]) / 2
                + int(formset.cleaned_data[-1].get("length", 0))
                if miss_node
                else sum([form.get("length", 0) for form in formset.cleaned_data]) / 2
            )
            # 获取节点线缆类型

            cable_type = None
            from dcrm.models.choices import (
                NodePortTypeChoices,
                PatchCordCableTypeChoices,
            )

            cable_map = {
                PatchCordCableTypeChoices.RJ45: [NodePortTypeChoices.RJ45],
                PatchCordCableTypeChoices.USB: [NodePortTypeChoices.USB],
                PatchCordCableTypeChoices.FIBER: [
                    NodePortTypeChoices.QSFP,
                    NodePortTypeChoices.SFP,
                    NodePortTypeChoices.QSFP_PLUS,
                    NodePortTypeChoices.SFP_PLUS,
                ],
                PatchCordCableTypeChoices.OTHER: [NodePortTypeChoices.OTHER],
            }
            nodes_port_types = [
                form.get("port_type")
                for form in formset.cleaned_data
                if form.get("port_type")
            ]
            port_types = set()
            for npt in nodes_port_types:
                for pcct, value in cable_map.items():
                    if npt in value:
                        port_types.add(pcct)
            if len(port_types) > 1:
                cable_type = PatchCordCableTypeChoices.RFMIXIN
            else:
                cable_type = (
                    port_types.pop() if port_types else PatchCordCableTypeChoices.OTHER
                )
            self.object.cable_type = cable_type
            # 设置数据中心
            if not self.object.data_center_id:
                self.object.data_center = self.request.user.data_center
            # 如果节点数大于0且节点数为奇数，则设置为PLANNED
            if miss_node:
                self.object.status = PatchCordStatusChoices.PLANNED
            self.object.length = length
            self.object.save()

            formset.instance = self.object
            formset.save()
            # 变更相关节点的端口连接状态
            patch_cord_status_changed.send(sender=self.model, instance=self.object)
            pre_add = self.request.GET.get("pre_add", None)
            if pre_add:
                # TODO: 删除缓存
                user = self.request.user
                user.notifications.filter(
                    actor_object_id=user.id, verb="预连接"
                ).unread().mark_all_as_read()
                # 删除缓存
                session = self.request.session
                if "pre_add_ports" in session:
                    del session["pre_add_ports"]
                    session.modified = True
            return redirect(self.get_success_url())
        else:
            for error in formset.non_form_errors():
                form.add_error(None, error)
            for form_errors in formset.errors:
                for field, errors in form_errors.items():
                    form.add_error(None, f"{field}: {errors}")
            return self.form_invalid(form)


class PatchCordUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    """跳线编辑视图"""

    model = PatchCord
    form_class = PatchCordForm
    template_name = "patchcord/form.html"

    def get_context_data(self, **kwargs):
        """添加内联表单集到上下文"""
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context["formset"] = PatchCordNodeFormSet(
                self.request.POST,
                instance=self.object,
                form_kwargs={"request": self.request},
            )
        else:
            context["formset"] = PatchCordNodeFormSet(
                instance=self.object, form_kwargs={"request": self.request}
            )
        context["is_create"] = self.object is None
        return context

    def form_valid(self, form):
        """保存表单和内联表单集"""
        context = self.get_context_data()
        formset = context["formset"]
        if formset.is_valid():
            try:
                self.object = form.save(commit=False)
                self.object.node_count = len(formset.cleaned_data) - len(
                    formset.deleted_forms
                )
                miss_node = (
                    self.object.node_count > 0 and self.object.node_count % 2 != 0
                )
                length = (
                    sum([form.get("length", 0) for form in formset.cleaned_data[:-1]])
                    / 2
                    + int(formset.cleaned_data[-1].get("length", 0))
                    if miss_node
                    else sum([form.get("length", 0) for form in formset.cleaned_data])
                    / 2
                )
                # 设置数据中心
                if not self.object.data_center_id:
                    self.object.data_center = self.request.user.data_center
                if self.object.missing_nodes:
                    self.object.status = PatchCordStatusChoices.PLANNED
                self.object.length = length
                self.object.save()

                formset.instance = self.object
                formset.save()
                return redirect(self.get_success_url())
            except Exception as e:
                form.add_error(None, str(e))
                return self.form_invalid(form)
        else:
            for error in formset.non_form_errors():
                form.add_error(None, error)
            for form_errors in formset.errors:
                for field, errors in form_errors.items():
                    form.add_error(None, f"{field}: {errors}")
            return self.form_invalid(form)


class PatchCordDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """跳线删除视图"""

    model = PatchCord
    template_name = "confirm_delete.html"

    def get_success_url(self):
        return reverse("patch_cord_list")

    def get_success_message(self):
        return _("跳线 %(identifier)s 已成功删除") % {
            "identifier": self.object.identifier
        }


class PatchCordNodeListView(BaseRequestMixin, ListViewMixin, ListView):
    """跳线节点列表视图"""

    model = PatchCordNode
    list_fields = [
        "port_name",
        "port_type",
        "patch_cord",
        "color_with_html",
        "rack",
        "rack_unit",
        "device",
    ]


class PatchCordNodeDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    """跳线节点详情视图"""

    model = PatchCordNode
    fields = "__all__"


class PatchCordNodeCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    """跳线节点创建视图"""

    model = PatchCordNode
    fields = [
        "patch_cord",
        "color",
        "rack",
        "rack_unit",
        "device",
        "port_name",
        "port_type",
        "sequence",
    ]


class PatchCordNodeUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    """跳线节点编辑视图"""

    model = PatchCordNode
    fields = [
        "patch_cord",
        "color",
        "rack",
        "rack_unit",
        "device",
        "port_name",
        "port_type",
        "sequence",
    ]


class PatchCordNodeDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """跳线节点删除视图"""

    model = PatchCordNode
    template_name = "confirm_delete.html"
