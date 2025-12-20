import re

from dateparser import parse
from mptt.managers import TreeManager
from mptt.models import MPTTModel, TreeForeignKey
from mptt.templatetags.mptt_tags import cache_tree_children

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import (
    Avg,
    Case,
    Count,
    F,
    IntegerField,
    OuterRef,
    Subquery,
    Sum,
    When,
)
from django.db.models.functions import Coalesce, ExtractDay, Now
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dcrm.models.fields import CounterCacheField

from .base import BaseModel
from .choices import (
    ItemInstanceHistoryOperationType,
    ItemInstanceStatus,
)
from .mixins import CustomFieldsMixin, IconMixin
from .tracking import TrackingModelMixin
from .utils import recursive_sort, tag_limit_filter

__all__ = [
    "Warehouse",
    "ItemCategory",
    "InventoryItem",
    "ItemInstance",
    "ItemInstanceHistory",
]


class Warehouse(BaseModel, CustomFieldsMixin, MPTTModel, TrackingModelMixin):
    """仓库 - 公司统一管理的资源"""

    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("关联的数据中心，用于组织管理仓库"),
    )
    parent = TreeForeignKey(
        to="self",
        on_delete=models.CASCADE,
        related_name="children",
        blank=True,
        null=True,
        db_index=True,
        verbose_name=_("父级仓库"),
        help_text=_("仓库的父级仓库，用于分类管理"),
    )
    name = models.CharField(
        max_length=100,
        verbose_name=_("名称"),
        help_text=_("仓库的显示名称，如：主机房备件库、耗材库等"),
    )
    location = models.CharField(
        max_length=200,
        verbose_name=_("位置"),
        help_text=_("仓库的具体物理位置，如：大厦1层101室"),
    )
    code = models.CharField(
        max_length=50,
        verbose_name=_("编码"),
        help_text=_("仓库的唯一编码，用于系统标识，如：WH-001"),
    )
    tags = models.ManyToManyField(
        "dcrm.Tag",
        verbose_name=_("标签"),
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "warehouse"),
        help_text=_("仓库的标签，用于分类管理"),
    )
    _icon = "fa fa-building"
    display_link_field = "name"
    search_fields = [
        "name",
    ]
    objects = TreeManager()

    class Meta:
        verbose_name = _("仓库")
        verbose_name_plural = _("仓库")
        unique_together = ["data_center", "code"]
        indexes = [
            # 新增优化索引
            models.Index(fields=["data_center", "code"]),
            models.Index(fields=["data_center", "name"]),
            models.Index(fields=["parent", "name"]),
        ]

    class MPTTMeta:
        order_insertion_by = ("name",)

    def __str__(self) -> str:
        return self.name

    def clean(self):
        super().clean()

        # An MPTT model cannot be its own parent
        if (
            not self._state.adding
            and self.parent
            and self.parent in self.get_descendants(include_self=True)
        ):
            raise ValidationError(
                {
                    "parent": "Cannot assign self or child {type} as parent.".format(
                        type=self._meta.verbose_name
                    )
                }
            )


class ItemCategory(BaseModel, IconMixin, CustomFieldsMixin, MPTTModel):
    """
    物品类别
        # 创建物品类别
    category = ItemCategory.objects.create(
        data_center=dc,
        name="服务器",
        unit="台",
        code="SERVER"
    )
    MPPT
    """

    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("物品类别所属的数据中心"),
    )
    parent = TreeForeignKey(
        to="self",
        on_delete=models.CASCADE,
        related_name="children",
        blank=True,
        null=True,
        db_index=True,
        verbose_name=_("父级类别"),
        help_text=_("物品类别的父级类别，用于分类管理"),
    )
    name = models.CharField(
        max_length=50,
        verbose_name=_("名称"),
        help_text=_("物品类别的名称，用于分类管理，如：服务器、网络设备、配件等"),
    )
    unit = models.CharField(
        max_length=20,
        verbose_name=_("单位"),
        help_text=_("物品的计量单位，如：块、条、台、米等"),
    )
    code = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        validators=[
            RegexValidator(
                regex=r"^[a-zA-Z0-9_\-\+]+$",
                message=_("只允许使用字母、数字、下划线、加号、减号"),
            ),
            RegexValidator(
                regex=r"__", message=_("不允许使用双下划线"), inverse_match=True
            ),
            RegexValidator(
                regex=r"--", message=_("不允许使用双连字符"), inverse_match=True
            ),
        ],
        verbose_name=_("编码"),
        help_text=_("仅允许字母、数字、下划线和连字符，如：SERVER、SFP+等"),
    )
    regex_rules = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name=_("正则规则"),
        help_text=_("用于智能提取的正则规则，用于提取物品的型号规格等信息"),
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("描述"),
        help_text=_("类别的详细说明，可包含使用范围、管理要求等信息"),
    )
    shared = models.BooleanField(
        default=True,
        blank=True,
        verbose_name=_("是否共享"),
        help_text=_("是否共享给其他数据中心引用"),
    )
    tags = models.ManyToManyField(
        "dcrm.Tag",
        verbose_name=_("标签"),
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "itemcategory"),
        help_text=_(
            "用于智能提取，建立标签的时候最好采用英文，例如：Storage, Memory, CPU, Power, GPU, Optical Module, Power Supply 等"
        ),
    )
    objects = TreeManager()

    _icon = "fa fa-folder-open"
    display_link_field = "name"
    search_fields = [
        "name",
    ]

    class Meta:
        verbose_name = _("物品类别")
        verbose_name_plural = _("物品类别")
        ordering = ["tree_id", "lft"]
        unique_together = [("data_center", "name")]
        indexes = [
            # 新增优化索引
            models.Index(fields=["data_center", "code"]),
            models.Index(fields=["data_center", "name"]),
            models.Index(fields=["parent", "name"]),
            models.Index(fields=["shared", "name"]),
            # 部分索引 - 仅为共享类别
            models.Index(
                fields=["name"],
                condition=models.Q(shared=True),
                name="itemcategory_shared_only",
            ),
        ]

    class MPTTMeta:
        order_insertion_by = ("name",)

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()

        # An MPTT model cannot be its own parent
        if (
            not self._state.adding
            and self.parent
            and self.parent in self.get_descendants(include_self=True)
        ):
            raise ValidationError(
                {
                    "parent": "Cannot assign self or child {type} as parent.".format(
                        type=self._meta.verbose_name
                    )
                }
            )

        # 验证正则规则
        if self.regex_rules:
            try:
                re.compile(self.regex_rules)
            except Exception as e:
                raise ValidationError({"regex_rules": f"正则表达式错误: {str(e)}"})

    @classmethod
    def get_pattern_categories(cls, data_center_id: int = 0):
        query = models.Q()
        if data_center_id:
            query = models.Q(shared=True) | models.Q(data_center_id=data_center_id)
        queryset = cls.objects.filter(query).filter(regex_rules__isnull=False)
        data = list(cls.recursive_node_to_dict(node) for node in queryset)
        return data

    @classmethod
    def recursive_node_to_dict(cls, node):
        result = {
            "id": node.pk,
            "name": node.name,
            "code": node.code,
            "unit": node.unit,
            "regex_rules": node.regex_rules,
            "keywords": cls.get_category_tags(node),
        }
        children = [cls.recursive_node_to_dict(c) for c in node.get_children()]
        if children:
            result["children"] = children
        return result

    @classmethod
    def get_categories(cls, data_center_id: int = 0):
        query = models.Q()
        if data_center_id:
            query = models.Q(shared=True) | models.Q(data_center_id=data_center_id)
        # from django.db.models.functions import Length
        # .order_by(*["tree_id", "lft", Length("name").desc()])
        root_nodes = cache_tree_children(cls.objects.filter(query))
        data = []
        for n in root_nodes:
            data.append(cls.recursive_node_to_dict(n))
        newData = recursive_sort(data)
        return newData

    @classmethod
    def get_category_tags(cls, category):
        """
        获取类别的标签
        """
        queryset = category.get_descendants(include_self=True)
        tags = list(
            queryset.filter(tags__isnull=False).values_list("tags__name", flat=True)
        )
        not_none_filter = lambda x: x is not None  # noqa: E731
        categories = set(
            list(filter(not_none_filter, queryset.values_list("name", flat=True)))
            + list(filter(not_none_filter, queryset.values_list("code", flat=True)))
        )
        category_names = " ".join(categories)
        extra_names = re.findall(r"(\b[a-z0-9]+\W?)", category_names, re.I)
        if extra_names:
            tags.extend([extra_name.strip() for extra_name in extra_names])
        return set(tags)


class InventoryItemQuerySet(models.QuerySet):
    def with_related_objects(self):
        """预加载 ItemCategory 和 厂家数据"""
        return self.select_related("category", "manufacturer")

    def with_stock_info(self):
        """添加库存相关信息的子查询"""
        total_stock = Subquery(
            ItemInstance.objects.filter(item=OuterRef("pk"), status="in_stock")
            .values("item")
            .annotate(total=Sum("quantity"))
            .values("total"),
            output_field=IntegerField(),
        )

        warehouse_count = Subquery(
            ItemInstance.objects.filter(item=OuterRef("pk"), status="in_stock")
            .values("item")
            .annotate(count=Count("warehouse", distinct=True))
            .values("count"),
            output_field=IntegerField(),
        )

        latest_operation = Subquery(
            OperationDetail.objects.filter(item_instance__item=OuterRef("pk"))
            .order_by("-created_at")
            .values("created_at")[:1]
        )

        return self.annotate(
            total_stock=Coalesce(total_stock, 0),
            warehouse_count=Coalesce(warehouse_count, 0),
            latest_operation=latest_operation,
            has_stock=Case(
                When(total_stock__gt=0, then=True),
                default=False,
                output_field=models.BooleanField(),
            ),
        )


class InventoryItemManager(models.Manager.from_queryset(InventoryItemQuerySet)):
    def get_queryset(self):
        """默认预加载关联对象"""
        return super().get_queryset().with_related_objects()

    def with_full_info(self):
        """获取包含完整信息的查询集"""
        return self.get_queryset().with_stock_info()


class InventoryItem(BaseModel, CustomFieldsMixin):
    """
    物品基本信息
    # 创建物品
    item = InventoryItem.objects.create(
        data_center=dc,
        manufacturer=manufacturer,
        category=category,
        name="服务器",
        model="Dell R730",
        description="Dell R730 服务器"
    )
    """

    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("物品所属的数据中心"),
    )
    manufacturer = models.ForeignKey(
        "dcrm.Manufacturer",
        on_delete=models.PROTECT,
        verbose_name=_("品牌/制造商"),
        help_text=_("物品的生产厂家，如：Dell、Huawei、Other等"),
    )
    category = models.ForeignKey(
        ItemCategory,
        on_delete=models.PROTECT,
        verbose_name=_("类别"),
        help_text=_("物品所属的类别，用于分类管理"),
    )
    name = models.CharField(
        max_length=100,
        verbose_name=_("名称"),
        help_text=_(
            """建议包含型号规格，如：DDR4 16G、单模光纤模块、R730等，"""
            """例如：<三星 16G DDR4 内存条>"""
        ),
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("描述"),
        help_text=_("物品的详细说明，可包含技术参数、使用说明等"),
    )
    shared = models.BooleanField(
        default=True,
        blank=True,
        verbose_name=_("是否共享"),
        help_text=_("是否共享给其他数据中心引用"),
    )
    tags = models.ManyToManyField(
        "dcrm.Tag",
        verbose_name=_("标签"),
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "inventoryitem"),
        help_text=_("物品的标签，用于分类管理"),
    )
    objects = InventoryItemManager()
    _icon = "fa fa-th"
    display_link_field = "name"
    search_fields = [
        "name",
    ]

    class Meta:
        verbose_name = _("物品")
        verbose_name_plural = _("物品")
        unique_together = ["data_center", "category", "manufacturer", "name"]

    def __str__(self):
        if self.manufacturer.name_cn:
            suffix = self.manufacturer.name_cn
        else:
            suffix = self.manufacturer.name
        if self.name not in str(self.category):
            return f"{self.name} {self.category} ({suffix})"
        return f"{self.category} ({suffix})"

    def get_total_stock(self):
        """获取该物品的总库存数量"""
        return (
            ItemInstance.objects.filter(item=self, status="in_stock").aggregate(
                total_quantity=models.Sum("quantity")
            )["total_quantity"]
            or 0
        )

    def get_stock_by_warehouse(self):
        """按仓库获取该物品的库存数量"""
        return (
            ItemInstance.objects.filter(item=self, status="in_stock")
            .values("warehouse__name")
            .annotate(total_quantity=models.Sum("quantity"))
        )

    def to_train_data(self) -> dict:
        """
        返回用于深度学习训练的数据结构
        Returns:
            dict: {
                "category": {"id": int, "name": str},
                "manufacturer": {"id": int, "name": str},
                "name": {"id": int, "name": str},
            }
        """
        return {
            "category": {
                "id": self.category.pk if self.category else -1,
                "name": self.category.name if self.category else "",
            },
            "manufacturer": {
                "id": self.manufacturer.pk if self.manufacturer else -1,
                "name": self.manufacturer.name if self.manufacturer else "",
                "name_cn": self.manufacturer.name_cn if self.manufacturer else "",
            },
            "name": {"id": self.pk, "name": self.name},
        }


class ItemInstanceQuerySet(models.QuerySet):
    def with_related_objects(self):
        """预加载相关对象"""
        return self.select_related(
            "tenant",
            "item",
            "item__category",
            "item__manufacturer",
        )

    def with_operation_info(self):
        """添加操作相关信息的子查询"""
        latest_operation = Subquery(
            OperationDetail.objects.filter(item_instance=OuterRef("pk"))
            .order_by("-created_at")
            .values("operation__operation_type")[:1],
            output_field=models.CharField(),
        )

        operation_count = Subquery(
            OperationDetail.objects.filter(item_instance=OuterRef("pk"))
            .values("item_instance")
            .annotate(count=Count("id"))
            .values("count"),
            output_field=IntegerField(),
        )

        return self.annotate(
            latest_operation_type=Coalesce(latest_operation, ""),
            total_operations=Coalesce(operation_count, 0),
            days_in_stock=Case(
                When(status="in_stock", then=ExtractDay(Now() - F("created_at"))),
                default=0,
                output_field=IntegerField(),
            ),
        )


class ItemInstanceManager(models.Manager.from_queryset(ItemInstanceQuerySet)):
    def get_queryset(self):
        """默认预加载关联对象"""
        return super().get_queryset().with_related_objects()

    def with_full_info(self):
        """获取包含完整信息的查询集"""
        return self.get_queryset().with_operation_info()

    def get_stock_status(self, warehouse=None):
        """获取库存状态汇总"""
        query = self.get_queryset()
        if warehouse:
            query = query.filter(warehouse=warehouse)

        return query.values("item__category__name", "item__name", "status").annotate(
            total_quantity=Sum("quantity"),
            warehouse_count=Count("warehouse", distinct=True),
            avg_days_in_stock=Avg(
                Case(
                    When(status="in_stock", then=ExtractDay(Now() - F("created_at"))),
                    default=0,
                    output_field=IntegerField(),
                )
            ),
        )


class ItemInstance(BaseModel, CustomFieldsMixin, TrackingModelMixin):
    """
    物品实例 - 支持一物一码（有SN）和批量管理（无SN）
    """

    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("实例所属的数据中心"),
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        verbose_name=_("父级库存"),
    )
    code = models.CharField(
        max_length=64,
        verbose_name=_("物品编号"),
        help_text=_("物品编号，可以自动生成"),
    )
    tenant = models.ForeignKey(
        "dcrm.Tenant",
        on_delete=models.PROTECT,
        verbose_name=_("租户"),
        help_text=_("物品所属的租户，用于多租户管理"),
    )
    item = models.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        verbose_name=_("物品"),
        help_text=_("关联的物品基本信息"),
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        verbose_name=_("仓库"),
        help_text=_("物品存放的仓库"),
    )
    identifier = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        db_index=True,
        verbose_name=_("唯一标识/SN"),
        help_text=_("如有SN/资产编号则一物一码，无则留空"),
    )
    quantity = models.PositiveIntegerField(
        default=1,
        verbose_name=_("当前数量"),
        help_text=_("有SN时只能为1，无SN时可大于1"),
    )
    warning_quantity = models.PositiveIntegerField(
        default=1,
        blank=True,
        null=True,
        verbose_name=_("预警数量"),
        help_text=_(
            "当库存数量低于该值时，系统将触发库存预警。建议根据实际消耗和补货周期合理设置。"
        ),
    )
    status = models.CharField(
        max_length=20,
        choices=ItemInstanceStatus.choices,
        default=ItemInstanceStatus.IN_STOCK,
        verbose_name=_("状态"),
        help_text=_("物品的当前状态，影响物品是否可用于领用出库"),
    )
    location = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("存放位置"),
        help_text=_("如货架号、格子编号等，可参考菜鸟驿站来规划"),
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("元数据"),
        help_text=_("物品的格式化JSON文本，用于记录自动识别的结构化数据信息"),
    )
    tags = models.ManyToManyField(
        "dcrm.Tag",
        verbose_name=_("标签"),
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "iteminstance"),
        help_text=_("物品的标签，用于分类管理"),
    )
    history_count = CounterCacheField(
        to_model="dcrm.ItemInstanceHistory",
        to_field="item_instance",
        verbose_name=_("历史(条)"),
    )
    _icon = "fa fa-cubes"
    display_link_field = "code"
    search_fields = ["code"]

    objects = ItemInstanceManager()

    class Meta:
        verbose_name = _("库存")
        verbose_name_plural = _("库存")
        ordering = ["status", "-updated_at"]
        unique_together = [("data_center", "identifier")]
        indexes = [
            # 新增优化索引
            models.Index(fields=["warehouse", "item"]),
            models.Index(fields=["data_center", "status"]),
            models.Index(fields=["item", "status"]),
            models.Index(fields=["warehouse", "status"]),
            models.Index(fields=["code"]),
            models.Index(fields=["identifier"]),
            # 数量和状态优化
            models.Index(fields=["status", "quantity"]),
            models.Index(fields=["item", "quantity"]),
            # 时间序列优化 - 移除不存在的字段
            # models.Index(fields=["purchase_date"], name="idx_iteminstance_purchase_date"),
            # models.Index(fields=["warranty_end_date"], name="idx_iteminstance_warranty_end"),
            # 部分索引 - 仅为有库存的物品
            models.Index(
                fields=["item", "warehouse"],
                condition=models.Q(quantity__gt=0),
                name="iteminstance_in_stock_only",
            ),
        ]

    def __str__(self) -> str:
        return self.code

    @property
    def image(self):
        return self.metadata.get("image", None)

    @property
    def raw_text(self):
        return self.metadata.get("raw_text", None)

    @classmethod
    def get_low_stock_items(cls, min_quantity=10):
        """获取库存低于指定数量的物品"""
        return cls.objects.filter(
            status="in_stock", quantity__lt=min_quantity
        ).select_related("item", "warehouse")

    @classmethod
    def get_stock_summary(cls, warehouse=None):
        """获取库存汇总信息"""
        query = cls.objects.filter(status="in_stock")
        if warehouse:
            query = query.filter(warehouse=warehouse)

        return query.values("item__category__name", "item__name").annotate(
            total_quantity=models.Sum("quantity"),
            locations=models.Count("warehouse", distinct=True),
        )

    def check_availability(self, required_quantity=1):
        """检查是否有足够的库存可用"""
        return self.status == "in_stock" and self.quantity >= required_quantity

    def is_below_warning(self):
        """
        判断当前库存是否低于预警线
        Returns:
            bool: True 表示低于预警线
        """
        return self.status == "in_stock" and self.quantity < self.warning_quantity

    @classmethod
    def get_warning_items(cls):
        """
        获取所有低于预警线的库存实例
        Returns:
            QuerySet: 低于预警线的库存实例
        """
        return cls.objects.filter(
            status="in_stock", quantity__lt=models.F("warning_quantity")
        )

    def to_train_data(self) -> dict:
        """
        返回用于深度学习训练的数据结构
        Returns:
            dict: {
                "raw_text": str,  # 从 metadata 中提取
                "category": {"id": int, "name": str},
                "manufacturer": {"id": int, "name": str},
                "name": {"id": int, "name": str},
                "tags": [str, ...] # 可能有多个
            }
        """
        item_data = (
            self.item.to_train_data()
            if self.item
            else {
                "category": {"id": -1, "name": ""},
                "manufacturer": {"id": -1, "name": ""},
                "name": {"id": -1, "name": ""},
                "tags": [],
            }
        )

        # 获取 raw_text
        meta = self.metadata or {}
        raw_text = meta.get("raw_text", "")

        # 合并数据
        return {
            "raw_text": raw_text,
            **item_data,  # 包含 category, manufacturer, name
            "tags": list(self.tags.values_list("name", flat=True)),
        }


class ItemInstanceHistoryManager(models.Manager):
    """库存历史记录管理器"""

    def get_user_history(self, user):
        """获取用户的操作历史"""
        return self.filter(created_by=user).order_by("-created_at")

    def get_item_history(self, item_instance):
        """获取设备的历史记录"""
        return self.filter(item_instance=item_instance).order_by("-created_at")

    def with_item_instance(self):
        return self.select_related("item_instance", "item_instance__tenant")


class ItemInstanceHistory(BaseModel, CustomFieldsMixin, TrackingModelMixin):
    """
    库存历史记录 - 记录物品的完整生命周期
    支持从入库到报废的完整状态追踪，包括借用、维护、安装等所有操作
    """

    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("记录所属的数据中心"),
    )
    timestamp = models.SlugField(
        editable=False,
        blank=True,
        null=True,
        verbose_name=_("时间戳"),
        help_text=_("时间戳代表对象在系统中的创建时间，区别于对象业务开始时间"),
    )
    created_at = models.DateTimeField(
        default=timezone.datetime.now,
        editable=True,
        verbose_name=_("操作时间"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_created",
        verbose_name=_("操作人"),
    )
    item_instance = models.ForeignKey(
        ItemInstance,
        on_delete=models.CASCADE,
        verbose_name=_("库存实例"),
        help_text=_("关联的库存物品实例"),
        related_name="history_records",
    )
    status = models.CharField(
        max_length=20,
        choices=ItemInstanceStatus.choices,
        default=ItemInstanceStatus.USED,
        verbose_name=_("状态"),
        help_text=_("记录操作后的物品状态"),
    )
    operation_type = models.CharField(
        max_length=20,
        choices=ItemInstanceHistoryOperationType.choices,
        default=ItemInstanceHistoryOperationType.CHECK_OUT,
        verbose_name=_("操作类型"),
        help_text=_("具体的操作类型，如借用、归还、维护等"),
    )
    reason = models.TextField(
        blank=True,
        verbose_name=_("操作原因"),
        help_text=_("操作原因或目的，如更换硬盘、租户上下架等"),
    )
    quantity = models.IntegerField(
        blank=True,
        null=True,
        verbose_name=_("操作数量"),
        help_text=_("本次操作的数量"),
    )
    related_object_type = models.ForeignKey(
        ContentType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        limit_choices_to={"app_label": "dcrm"},
        verbose_name=_("关联对象类型"),
        help_text=_("关联对象的类型，如租户、机柜、设备、维修商等"),
    )
    related_object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("关联对象ID"),
        help_text=_("关联对象的主键ID"),
    )
    extra_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("附加数据"),
        help_text=_("用于存储与操作相关的额外信息、扩展属性等"),
    )

    objects = ItemInstanceHistoryManager()

    _icon = "fa fa-history"
    display_link_field = "timestamp"
    search_fields = ["reason"]
    supports_import = False

    class Meta:
        verbose_name = _("库存历史")
        verbose_name_plural = _("库存历史")
        indexes = [
            models.Index(fields=["item_instance", "created_at"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["operation_type", "created_at"]),
            models.Index(fields=["created_by", "created_at"]),
            models.Index(fields=["data_center", "status"]),
        ]

    def __str__(self):
        return f"{self.item_instance} - {self.get_operation_type_display()} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"

    def save(self, *args, **kwargs):
        if not self.timestamp:
            self.timestamp = str(int(self.created_at.timestamp() * 1000))
        super().save(*args, **kwargs)

    def get_related_object_display(self):
        """获取关联对象的显示信息"""
        if self.related_object_type and self.related_object_id:
            try:
                obj = self.related_object_type.get_object_for_this_type(
                    id=self.related_object_id
                )
                return str(obj)
            except:
                return _("对象已删除")
        return ""

    def get_location_display(self):
        """获取位置显示信息"""
        return (
            self.extra_data.get("to_location")
            or self.extra_data.get("from_location")
            or ""
        )

    def is_overdue(self):
        """检查是否逾期"""

        extra_data = self.extra_data
        expected_return_date = parse(extra_data.get("expected_return_date"))
        actual_return_date = parse(extra_data.get("actual_return_date"))
        if expected_return_date and not actual_return_date:
            return timezone.now() > expected_return_date
        return False

    def get_overdue_days(self):
        """获取逾期天数"""
        if self.is_overdue():
            return (timezone.now() - self.expected_return_date).days
        return 0
