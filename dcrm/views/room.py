from collections import namedtuple

from django.contrib import messages
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    TemplateView,
    UpdateView,
)

from dcrm.models import Rack, Room
from dcrm.models.choices import ColorChoices, RackTypeChoices

from .mixins.base import BaseRequestMixin
from .mixins.delete import DeleteViewMixin
from .mixins.detail import DetailViewMixin
from .mixins.edit import CreateViewMixin, FieldSet, UpdateViewMixin
from .mixins.list import ListViewMixin


class RoomListView(BaseRequestMixin, ListViewMixin):
    """
    房间列表视图
    """

    model = Room
    list_fields = [
        "name",
        "cname",
        "rack_count",
        "default",
        "rows",
        "cols",
        "tags",
        "length",
        "width",
        "height",
    ]
    extra_urls = [
        {
            "name": "room_rack_maps",
            "label": "平面图",
            "url": reverse_lazy("room_rack_maps"),
            "icon": "fa fa-th",
            "next_url": reverse_lazy("room_list"),
        },
    ]


class RoomCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = Room
    fields = [
        "name",
        "cname",
        "description",
        "length",
        "width",
        "height",
        "default",
        "rows",
        "cols",
        "address",
        "tags",
    ]

    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "name",
                "cname",
                "description",
                "address",
                "tags",
            ],
            description=_("房间名称、描述、地址、标签等"),
        ),
        FieldSet(
            name=_("布局&面积"),
            fields=[
                "default",
                "rows",
                "cols",
                "length",
                "width",
                "height",
            ],
            description=_("机柜布局，机房的长宽高（米）信息"),
            inline_groups=[["rows", "cols"], ["length", "width", "height"]],
        ),
    ]


class RoomUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = Room
    fields = [
        "name",
        "cname",
        "description",
        "length",
        "width",
        "height",
        "default",
        "rows",
        "cols",
        "address",
        "tags",
    ]

    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "name",
                "cname",
                "description",
                "address",
                "tags",
            ],
            description=_("房间名称、描述、地址、标签等"),
        ),
        FieldSet(
            name=_("布局&面积"),
            fields=[
                "default",
                "rows",
                "cols",
                "length",
                "width",
                "height",
            ],
            description=_("机柜布局，机房的长宽高（米）信息"),
            inline_groups=[["rows", "cols"], ["length", "width", "height"]],
        ),
    ]


class RoomDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = Room
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": [
                "name",
                "cname",
                "rack_count",
                "address",
                "description",
                "default",
                "rows",
                "cols",
                "tags",
            ],
            "description": _("机房的基本信息"),
        },
        {
            "title": _("布局&面积"),
            "fields": ["length", "width", "height", "latitude", "longitude"],
            "description": _("机房的长宽高（米），位置信息"),
        },
    ]


class RoomDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    model = Room
    success_message = _("机房已删除")

    def get_success_url(self):
        return reverse("room_list")


class RoomRackMapsView(BaseRequestMixin, TemplateView):
    model = Room
    template_name = "rack/room_maps.html"
    is_ajax = False
    mode = "show"
    object = None
    stats_fields = ["rack_type", "status"]
    draggable = "false"

    def dispatch(self, request, *args, **kwargs):
        """请求分发处理"""
        if not request.user.is_authenticated:
            return self.handle_authentication()

        # 检查数据中心
        if not request.user.data_center:
            response = self.handle_no_datacenter(request)
            if response:
                return response

        self.mode = request.GET.get("mode", "show")
        if self.mode == "setup" and request.method == "GET":
            self.draggable = "true"
            messages.info(request, _("请拖拽机柜进行布局"))
        self.is_ajax = request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest"
        if not self.get_rooms.exists():
            messages.warning(request, _("请先新建机柜房间"))
            return redirect(reverse("room_create"))
        self.get_default_room()
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def get_rooms(self):
        """
        返回当前机房的所有房间，用于tabs
        """
        data_center = self.request.user.data_center
        return Room.objects.filter(data_center=data_center).order_by("-default", "name")

    @cached_property
    def get_room_racks(self):
        """
        获取当前机房房间下的所有机柜查询集
        """
        defer_fields: list[str] = [
            f"{f.name}__{field}"
            for f in Rack._meta.fields
            if f.is_relation and f.many_to_one
            for field in [
                "created_by",
                "updated_by",
                "data_center",
                "custom_field_data",
                "updated_at",
                "created_at",
                "longitude",
                "latitude",
            ]
            if hasattr(f.related_model, field)
        ]
        return (
            Rack.objects.with_space_usage()
            .filter(room=self.object)
            .select_related("tenant", "room", "status")
            .defer(*defer_fields)
        )

    def get_outcell_racks(self):
        """
        返回未布局的机柜查询集，row 或 col 数据未设置的集合
        """
        query = Q(col__isnull=True) | Q(row__isnull=True)
        return self.get_room_racks.filter(query)

    def get_incell_racks(self):
        query = Q(col__isnull=False) & Q(row__isnull=False)
        return self.get_room_racks.filter(query)

    def get_default_room(self):
        room_id = int(self.request.GET.get("id", 0))
        if room_id:
            self.object = self.get_rooms.filter(pk=room_id).first()
        else:
            self.object = self.get_rooms.filter(default=True).first()
        if not self.object:
            messages.warning(self.request, _("该数据中心还未创建机柜房间"))
        return self.object

    def get_stats_fields(self) -> list[str]:
        """获取需要统计的字段列表"""
        if not self.stats_fields:
            return [f.name for f in self.opts.fields if f.choices]
        return self.stats_fields

    def none_position_racks_cells(self):
        max_col = self.object.cols
        max_row = self.object.rows

        query = models.Q(col__isnull=True) | models.Q(row__isnull=True)
        none_position_racks = self.get_room_racks.filter(query).values(
            "id", "name", "row", "col"
        )
        racks = []
        start_row = max_row + 2
        col = 0
        for rack in none_position_racks:
            col += 1
            if col >= (max_col - 1):
                start_row += 1
                col = 0
            rack.update(dict(row=start_row, col=col, draggable=self.draggable))
            racks.append(rack)
        return racks

    def get_field_stats(self, queryset) -> dict:
        """
        获取字段统计信息
        返回格式:
        {
            'field_name': {
                'choices': [(value, label), ...],
                'stats': {value: count, ...},
                'total': total_count
            },
            ...
        }
        """
        opts = queryset.model._meta
        stats = []

        if not self.stats_fields:
            return stats

        for field_name in self.stats_fields:
            try:
                field = opts.get_field(field_name)
                if not getattr(field, "choices", None):
                    continue
                choices = field.choices
                # 使用 annotate 和 values 进行分组统计
                field_stats = (
                    queryset.values(field_name)
                    .annotate(count=models.Count("id"))
                    .order_by(field_name)
                )
                # 转换为字典格式，包含所有可能的选项（即使计数为0）
                stats_dict = {choice[0]: 0 for choice in choices}

                labels_map = {choice[0]: choice[1] for choice in choices}
                colors = {}
                choices_class = (
                    getattr(field.default, "__class__", None) if field.default else None
                )
                if choices_class and hasattr(choices_class, "get_color"):
                    colors = {
                        val[0]: choices_class.get_color(val[0]) for val in choices
                    }

                field_item = []
                total = 0

                # 更新实际的计数
                for stat in field_stats:
                    value = stat[field_name]
                    count = stat["count"]
                    stats_dict[value] = count
                    field_item.append(
                        dict(
                            name=value,
                            label=labels_map[value],
                            count=stat["count"],
                            color=colors[value],
                        )
                    )
                    total += count
                field_item.insert(
                    0,
                    {"name": "total", "label": "总数", "count": total, "color": "blue"},
                )
                stats.append(
                    {
                        "name": field_name,
                        "verbose_name": field.verbose_name,
                        "stats": field_item,
                    }
                )
            except FieldDoesNotExist:
                continue

        status = list(
            queryset.values("status", "status__color", "status__name")
            .annotate(
                name=models.F("status"),
                label=models.F("status__name"),
                count=models.Count("id"),
                color=models.F("status__color"),
            )
            .values("name", "label", "count", "color")
            .order_by("status")
        )
        for i in status:
            if list(i.values()).count(None) == 3:
                i.update({"name": "0", "label": "未设置", "color": "gray"})
        stats.append({"name": "status", "verbose_name": "状态", "stats": status})
        return stats

    def post(self, request, *args, **kwargs):
        if not self.is_ajax or self.mode != "setup":
            return JsonResponse({"message": "不允许的访问方式"}, status=403)
        rack_id = request.POST.get("rack_id", None)
        row = request.POST.get("row", None)
        col = request.POST.get("col", None)
        verify = all([rack_id, row, col])
        if not verify:
            return JsonResponse({"message": "请求数据验证有误"}, status=400)
        try:
            instance = self.get_room_racks.filter(pk=int(rack_id)).first()
            self.get_room_racks.filter(pk=int(rack_id)).update(
                row=int(row),
                col=int(col),
                updated_by=request.user,
            )
            return JsonResponse({"message": f"更新成功, {instance.name}"})
        except Exception as e:
            return JsonResponse({"message": f"更新错误，{e}"}, status=500)

    def get_racks_tenant(self):
        """
        按机柜租户的统计
        """
        queryset = (
            self.get_room_racks.filter(tenant__isnull=False)
            .values("tenant_id", "tenant__name")
            .annotate(id=models.F("tenant_id"), name=models.F("tenant__name"))
            .values("id", "name")
            .order_by("id")
            .distinct()
        )
        return queryset

    def get_room_cells(self):
        """
        根据 self.mode 进行机房房间画布渲染
        """
        cell = namedtuple(
            "Cell", ["row", "col", "rack", "scolor", "tcolor", "draggable"]
        )
        rack_cells = {
            f"{rack.row}-{rack.col}": rack
            for rack in self.get_room_racks.filter(row__isnull=False, col__isnull=False)
        }
        cells = []
        for row in range(self.object.rows):
            for col in range(self.object.cols):
                key = f"{row}-{col}"
                rack = rack_cells.get(key, None)
                status_color = ""
                type_color = ""
                if rack:
                    if rack.status:
                        status_color = ColorChoices.to_hex_color(rack.status.color)
                    else:
                        status_color = ColorChoices.to_hex_color("gray")
                    type_color = ColorChoices.to_hex_color(
                        RackTypeChoices.get_color(rack.rack_type)
                    )
                cells.append(
                    cell(row, col, rack, status_color, type_color, self.draggable)
                )
        return cells

    def get_queryset(self):
        return self.get_room_racks

    def get_context_data(self, **kwargs):
        """扩展上下文数据"""
        context = super().get_context_data(**kwargs)
        extra = dict(
            object=self.object,
            rooms=self.get_rooms,
            statistics=self.get_field_stats(self.get_room_racks),
            cells=self.get_room_cells(),
            tenants=self.get_racks_tenant(),
            none_position_racks_cells=self.none_position_racks_cells(),
        )
        context.update(extra)
        return context
