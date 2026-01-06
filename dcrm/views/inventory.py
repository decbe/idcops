from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    UpdateView,
)

from dcrm.forms.inventory import BatchItemInstanceFormSet
from dcrm.models.base import LogEntry
from dcrm.models.choices import (
    ChangeActionChoices,
    ItemInstanceHistoryOperationType,
    ItemInstanceStatus,
)
from dcrm.models.codingrule import CodingRule
from dcrm.models.inventory import (
    InventoryItem,
    ItemCategory,
    ItemInstance,
    ItemInstanceHistory,
    Warehouse,
)
from dcrm.utilities.serialization import serialize_object

from .mixins.base import BaseRequestMixin
from .mixins.delete import DeleteViewMixin
from .mixins.detail import DetailViewMixin
from .mixins.edit import CreateViewMixin, FieldSet, UpdateViewMixin
from .mixins.list import ListViewMixin


class WarehouseListView(BaseRequestMixin, ListViewMixin, ListView):
    """仓库列表视图"""

    model = Warehouse
    list_fields = ["name", "location", "code", "tags"]


class WarehouseDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    """仓库详情视图"""

    model = Warehouse
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": ["name", "location", "code", "tags", "parent"],
            "description": _("仓库的基本信息"),
        }
    ]


class WarehouseCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    """仓库创建视图"""

    model = Warehouse
    fields = ["name", "location", "code", "parent", "tags"]


class WarehouseUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    """仓库更新视图"""

    model = Warehouse
    fields = ["name", "location", "code", "parent", "tags"]


class WarehouseDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """仓库删除视图"""

    model = Warehouse
    success_url = reverse_lazy("warehouse_list")


class ItemCategoryListView(BaseRequestMixin, ListViewMixin, ListView):
    """物品类别列表视图"""

    model = ItemCategory
    list_fields = ["name", "unit", "code", "icon_with_html", "tags", "parent", "shared"]


class ItemCategoryDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    """物品类别详情视图"""

    model = ItemCategory
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": [
                "name",
                "unit",
                "code",
                "icon_with_html",
                "description",
                "regex_rules",
                "parent",
                "shared",
                "tags",
            ],
            "description": _("物品类别的基本信息"),
        }
    ]


class ItemCategoryCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    """物品类别创建视图"""

    model = ItemCategory
    fields = [
        "name",
        "unit",
        "code",
        "icon",
        "description",
        "tags",
        "parent",
        "shared",
        "regex_rules",
    ]


class ItemCategoryUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    """物品类别更新视图"""

    model = ItemCategory
    fields = [
        "name",
        "unit",
        "code",
        "icon",
        "description",
        "tags",
        "parent",
        "shared",
        "regex_rules",
    ]


class ItemCategoryDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """物品类别删除视图"""

    model = ItemCategory
    success_url = reverse_lazy("item_category_list")


class InventoryItemListView(BaseRequestMixin, ListViewMixin, ListView):
    """库存物品列表视图"""

    model = InventoryItem
    list_fields = ["name", "category", "manufacturer", "description", "shared", "tags"]

    def get_queryset(self):
        """获取查询集，包含关联对象"""
        queryset = super().get_queryset()
        return queryset.with_related_objects()


class InventoryItemDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    """库存物品详情视图"""

    model = InventoryItem
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": [
                "name",
                "category",
                "manufacturer",
                "description",
                "shared",
                "tags",
            ],
            "description": _("库存物品的基本信息"),
        }
    ]


class InventoryItemCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    """库存物品创建视图"""

    model = InventoryItem
    fields = ["manufacturer", "category", "name", "description", "shared", "tags"]
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "manufacturer",
                "category",
                "name",
                "description",
                "shared",
                "tags",
            ],
            description=_("推荐格式：<三星 16G DDR4 内存条>"),
        ),
    ]


class InventoryItemUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    """库存物品更新视图"""

    model = InventoryItem
    fields = ["manufacturer", "category", "name", "description", "shared", "tags"]
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "manufacturer",
                "category",
                "name",
                "description",
                "shared",
                "tags",
            ],
            description=_("推荐格式：<三星 16G DDR4 内存条>"),
        ),
    ]


class InventoryItemDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """库存物品删除视图"""

    model = InventoryItem
    success_url = reverse_lazy("inventory:inventory_item_list")


class ItemInstanceListView(BaseRequestMixin, ListViewMixin, ListView):
    """库存物品实例列表视图"""

    model = ItemInstance
    list_fields = [
        "code",
        "tenant",
        "item",
        "quantity",
        "identifier",
        "warehouse",
        "location",
        "status",
        "tags",
        "history_count",
    ]

    # def get_queryset(self) -> QuerySet:
    #     """获取查询集，添加自定义排序字段"""
    #     queryset = super().get_queryset()

    #     # 添加自定义排序字段
    #     queryset = queryset.annotate(
    #         custom_order=Case(
    #             When(status=ItemInstanceStatus.BORROWING, then=Value(1)),
    #             When(status=ItemInstanceStatus.IN_STOCK, then=Value(2)),
    #             When(status=ItemInstanceStatus.USED, then=Value(3)),
    #             When(status=ItemInstanceStatus.SCRAPPED, then=Value(4)),
    #             When(status=ItemInstanceStatus.LOST, then=Value(5)),
    #             default=Value(5),
    #             output_field=IntegerField(),
    #         )
    #     )

    #     # 获取排序列表并在前面插入自定义排序
    #     ordering = self.get_ordering()
    #     if isinstance(ordering, str):
    #         ordering = [ordering]

    #     # 在现有排序前面插入自定义排序
    #     final_ordering = ["custom_order", "-updated_at"] + list(ordering)
    #     queryset = queryset.order_by(*final_ordering)

    #     return queryset


class ItemInstanceDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    """库存物品实例详情视图"""

    model = ItemInstance
    template_name = "inventory/detail.html"
    enable_tabs = False
    enable_create_update = False
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": [
                "code",
                "item",
                "identifier",
                "tenant",
                "warehouse",
                "location",
                "status",
                "quantity",
                "tags",
            ],
            "description": _("库存物品实例的基本信息"),
        }
    ]

    def get_history(self, queryset):
        """返回库存历史
        """
        list_fields = [
            "created_at",
            "created_by",
            "operation_type",
            # "status",
            "quantity",
            "reason",
        ]
        from dcrm.utilities.render import render_objects

        data = render_objects(queryset, list_fields)
        labels = next(data)
        return {"labels": labels, "rows": data}

    def get_context_data(self, **kwargs):
        """添加内联表单集到上下文"""
        context = super().get_context_data(**kwargs)
        history_queryset = self.object.history_records.select_related(
            "created_by"
        ).order_by("-created_at")
        context["history"] = self.get_history(history_queryset)
        return context


class ItemInstanceCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    """库存物品实例创建视图"""

    model = ItemInstance
    template_name = "inventory/item_instance_create.html"
    fields = [
        "code",
        "identifier",
        "item",
        "tenant",
        "warehouse",
        "location",
        "quantity",
        "tags",
    ]
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "code",
                "identifier",
                "tenant",
                "item",
                "warehouse",
                "location",
                "quantity",
                "tags",
            ],
            description=_("库存物品实例的基本信息"),
        ),
    ]


class ItemInstanceUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    """库存物品实例更新视图"""

    model = ItemInstance
    fields = [
        "code",
        "identifier",
        "tenant",
        "item",
        "warehouse",
        "location",
        "tags",
    ]
    fieldsets = [
        FieldSet(
            name=_("基本信息"),
            fields=[
                "code",
                "identifier",
                "tenant",
                "item",
                "warehouse",
                "location",
                "tags",
            ],
            description=_("库存物品实例的基本信息"),
        ),
    ]


class ItemInstanceDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """库存物品实例删除视图"""

    model = ItemInstance
    success_url = reverse_lazy("item_instance_list")


class BulkItemInstanceCreateView(BaseRequestMixin, FormView):
    """批量库存物品实例创建视图"""

    model = ItemInstance
    template_name = "inventory/bulk_create.html"
    form_class = BatchItemInstanceFormSet
    success_url = reverse_lazy("item_instance_list")
    success_message: str = _("创建成功")

    def get_form(self, form_class=None):
        """返回用于此视图的表单实例"""
        if form_class is None:
            form_class = self.get_form_class()
        return form_class(form_kwargs={"request": self.request})

    def post(self, request, *args, **kwargs):
        """处理POST请求"""
        formset = BatchItemInstanceFormSet(
            data=request.POST, form_kwargs={"request": request}
        )
        if formset.is_valid():
            return self.form_valid(formset)
        return self.form_invalid(formset)

    def form_valid(self, formset):
        """处理有效的表单集"""
        try:
            with transaction.atomic():
                all_instances = []
                for form in formset:
                    if (
                        form.is_valid()
                        and form.cleaned_data
                        and not form.cleaned_data.get("DELETE", False)
                    ):
                        _identifiers = form.cleaned_data.get("identifier")
                        quantity = form.cleaned_data.get("quantity", 1)

                        # 先用表单save(commit=False)得到基础对象
                        base_instance = form.save(commit=False)

                        if _identifiers:
                            # 有SN号的情况：每个SN创建一个数量为1的实例
                            identifiers = [
                                x.strip() for x in _identifiers.split(",") if x.strip()
                            ]
                            rules = CodingRule.objects.get_for_model(
                                ItemInstance, self.request.user.data_center
                            )
                            rule = rules.filter(to_field="code").first()
                            if not rule:
                                raise ValidationError("未找到可用的编号规则")
                            codes = rule.get_available_codes(limit=len(identifiers))
                            if len(codes) != len(identifiers):
                                raise ValidationError("编号数量与SN数量不符")

                            for sn, code in zip(identifiers, codes):
                                instance = ItemInstance(
                                    item=base_instance.item,
                                    tenant=base_instance.tenant,
                                    warehouse=base_instance.warehouse,
                                    location=base_instance.location,
                                    identifier=sn,
                                    code=code,
                                    quantity=1,
                                    created_by=self.request.user,
                                    data_center=self.request.user.data_center,
                                    metadata=base_instance.metadata,
                                )
                                instance.save()
                                if "tags" in form.cleaned_data:
                                    instance.tags.set(form.cleaned_data["tags"])
                                all_instances.append(instance)
                        else:
                            # 没有SN号的情况：创建一个数量为指定数量的实例
                            if not quantity or quantity < 1:
                                raise ValidationError("无唯一标识时，数量必须大于0")

                            rules = CodingRule.objects.get_for_model(
                                ItemInstance, self.request.user.data_center
                            )
                            rule = rules.filter(to_field="code").first()
                            if not rule:
                                raise ValidationError("未找到可用的编号规则")
                            code = rule.get_available_codes(limit=1)[0]

                            instance = ItemInstance(
                                item=base_instance.item,
                                tenant=base_instance.tenant,
                                warehouse=base_instance.warehouse,
                                location=base_instance.location,
                                code=code,
                                quantity=quantity,  # 使用指定的数量
                                created_by=self.request.user,
                                data_center=self.request.user.data_center,
                                metadata=base_instance.metadata,
                            )
                            instance.save()
                            if "tags" in form.cleaned_data:
                                instance.tags.set(form.cleaned_data["tags"])
                            all_instances.append(instance)

                # 记录日志
                logs = [
                    LogEntry(
                        created_by=self.request.user,
                        created_at=instance.created_at,
                        data_center=instance.data_center,
                        action=ChangeActionChoices.CREATE,
                        action_type="create",
                        object_repr=instance,
                        message=f"{self.success_message}: ({str(instance)})",
                        timestamp=str(int(timezone.now().timestamp() * 1000)),
                        postchange_data=serialize_object(instance),
                    )
                    for instance in all_instances
                ]
                LogEntry.objects.bulk_create(logs)
                # 记录历史库存入库
                history_objs = [
                    ItemInstanceHistory(
                        item_instance=instance,
                        status=ItemInstanceStatus.IN_STOCK,
                        operation_type=ItemInstanceHistoryOperationType.CHECK_IN,
                        created_by=self.request.user,
                        timestamp=str(int(instance.created_at.timestamp() * 1000)),
                        data_center=instance.data_center,
                        quantity=instance.quantity,
                        reason=_("入库"),
                    )
                    for instance in all_instances
                ]
                ItemInstanceHistory.objects.bulk_create(history_objs)
                from dcrm.signals.counters import update_counts

                update_counts(ItemInstance, "history_count", "history_records")
                messages.success(
                    self.request, _(f"创建库存成功，共{len(all_instances)}条")
                )
                return redirect(self.success_url)

        except Exception as e:
            messages.error(self.request, f"创建失败: {str(e)}")
            return self.form_invalid(formset)

    def get_context_data(self, **kwargs):
        """获取上下文数据"""
        context = super().get_context_data(**kwargs)
        if self.request.method == "POST":
            context["formset"] = BatchItemInstanceFormSet(
                data=self.request.POST,
                form_kwargs={"request": self.request},
            )
        else:
            context["formset"] = BatchItemInstanceFormSet(
                form_kwargs={"request": self.request},
            )
        return context


class ItemInstanceHistoryListView(BaseRequestMixin, ListViewMixin, ListView):
    """库存历史记录列表视图"""

    model = ItemInstanceHistory
    list_fields = [
        "timestamp",
        "item_instance",
        "status",
        "created_at",
        "created_by",
        "operation_type",
        "quantity",
        "reason",
        "item_instance__tenant",
        "item_instance__warehouse",
        "item_instance__identifier",
    ]

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.select_related(
            "item_instance", "item_instance__tenant", "item_instance__warehouse"
        )


class ItemInstanceHistoryDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    """库存历史记录详情视图"""

    model = ItemInstanceHistory
    fields = "__all__"
    fieldsets = [
        {
            "title": _("基本信息"),
            "fields": [
                "timestamp",
                "item_instance",
                "operation_type",
                "status",
                "reason",
                "created_by",
                "created_at",
                "related_object_type",
                "related_object_id",
                "extra_data",
            ],
            "description": _("库存历史记录的详细信息"),
        }
    ]


class ItemInstanceHistoryCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    """库存历史记录创建视图"""

    model = ItemInstanceHistory


class ItemInstanceHistoryUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    """库存历史记录更新视图"""

    model = ItemInstanceHistory


class ItemInstanceHistoryDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    """库存历史记录删除视图"""

    model = ItemInstanceHistory
    success_url = reverse_lazy("item_instance_history_list")
