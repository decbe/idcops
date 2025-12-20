import math
from typing import Dict, List, Set

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Case, Count, F, IntegerField, OuterRef, Subquery, Sum, When
from django.db.models.functions import Coalesce
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from dcrm.utilities.power import PowerConverter

from .base import DataCenter
from .choices import (
    DeviceStatusChoices,
    PDUSlotChoices,
    RackPDUStatusChoices,
    RackTypeChoices,
)
from .fields import CounterCacheField, DeviceHeightField
from .mixins import BaseModel, ColorMixin, CustomFieldsMixin
from .tracking import TrackingModelMixin
from .utils import tag_limit_filter

__all__ = (
    "Room",
    "RackStatus",
    "Rack",
    "RackPDU",
)


class Room(BaseModel, CustomFieldsMixin, TrackingModelMixin):
    """
    机房房间
    """

    data_center = models.ForeignKey(
        to="dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("房间所属的数据中心"),
    )
    name = models.CharField(
        max_length=64,
        verbose_name=_("名称"),
        help_text=_("房间的名称，例如：3F01、2F-VIP01等"),
    )
    cname = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        verbose_name=_("房间别名"),
        help_text=_("例如：3楼1区、2楼VIP-01机房等"),
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("描述"),
        help_text=_("例如：双面机柜封闭式、下送风、VIP机房，所有机柜都是50个PDU"),
    )
    address = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=_("地址"),
        help_text=_("房间的物理地址"),
    )
    latitude = models.DecimalField(
        verbose_name=_("纬度"),
        max_digits=8,
        decimal_places=6,
        blank=True,
        null=True,
        editable=False,
        help_text=_("GPS坐标,十进制格式(xx.yyyyyy)"),
    )
    longitude = models.DecimalField(
        verbose_name=_("经度"),
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
        editable=False,
        help_text=_("GPS坐标,十进制格式(xx.yyyyyy)"),
    )
    tags = models.ManyToManyField(
        to="dcrm.Tag",
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "room"),
        verbose_name=_("标签"),
        help_text=_("房间的标签"),
    )
    length = models.PositiveIntegerField(
        default=50,
        blank=True,
        null=True,
        verbose_name=_("长度(米)"),
        help_text=_("房间的长度默认为50米，单位为米"),
    )
    width = models.PositiveIntegerField(
        default=30,
        blank=True,
        null=True,
        verbose_name=_("宽度(米)"),
        help_text=_("房间的宽度默认为30米，单位为米"),
    )
    height = models.PositiveIntegerField(
        default=4,
        blank=True,
        null=True,
        verbose_name=_("层高(米)"),
        help_text=_("房间的层高默认为4米，单位为米"),
    )
    default = models.BooleanField(
        default=False,
        verbose_name=_("默认机房"),
        help_text=_("是否设置为默认机房"),
    )
    rows = models.PositiveSmallIntegerField(
        default=40,
        verbose_name=_("行数"),
        help_text=_("房间机柜行数，类似Excel表格，用于布局机柜"),
    )
    cols = models.PositiveSmallIntegerField(
        default=20,
        verbose_name=_("列数"),
        help_text=_("房间机柜列数，类似Excel表格，用于布局机柜"),
    )
    rack_count = CounterCacheField(
        to_model="dcrm.Rack",
        to_field="room",
        verbose_name=_("机柜(个)"),
        help_text=_("房间中的机柜数量"),
    )

    _icon = "fa fa-building-o"
    display_link_field = "name"

    def __str__(self) -> str:
        return self.name

    class Meta:
        verbose_name = _("房间")
        verbose_name_plural = _("机柜房间")
        unique_together = [("data_center", "name")]
        ordering = ["-updated_at"]
        indexes = [
            # 新增优化索引
            models.Index(fields=["data_center", "default"]),
            models.Index(fields=["data_center", "name"]),
            # 地理位置优化
            models.Index(fields=["latitude", "longitude"]),
            # 部分索引 - 仅为默认机房
            models.Index(
                fields=["name"],
                condition=models.Q(default=True),
                name="room_default_only",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.default:
            self.set_default_room(room=self)
        return super().save(*args, **kwargs)

    @staticmethod
    def set_default_room(room):
        Room.objects.filter(data_center=room.data_center).exclude(pk=room.pk).update(
            default=False
        )
        return room


class RackStatus(BaseModel, ColorMixin, CustomFieldsMixin):
    """
    机柜状态
    """

    data_center = models.ForeignKey(
        to="dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("所属的数据中心"),
    )
    name = models.CharField(
        max_length=64,
        verbose_name=_("名称"),
        help_text=_("机柜状态名称，例如：预分配、已使用等"),
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("描述"),
        help_text=_(
            "例如：预留给可能进行机柜扩容的某一个客户（机柜实质是空闲状态，并且未被占用）"
        ),
    )
    # next_status = models.ManyToManyField(
    #     "self",
    #     blank=True,
    #     null=True,
    #     verbose_name=_("允许流转到"),
    #     help_text=_("机柜当前这个状态允许流转下一个哪些状态"),
    # )
    allowed_mount = models.BooleanField(
        default=False,
        verbose_name=_("允许上架"),
        help_text=_("该机柜状态是否允许上架设备"),
    )
    shared = models.BooleanField(
        default=True,
        blank=True,
        verbose_name=_("是否共享"),
        help_text=_("是否共享给其他数据中心引用"),
    )
    tags = models.ManyToManyField(
        to="dcrm.Tag",
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "rackstatus"),
        verbose_name=_("标签"),
        help_text=_("设备类型的标签"),
    )

    _icon = "fa fa-folder-open-o"
    display_link_field = "name"
    search_fields = ["name"]
    supports_import = True

    def __str__(self) -> str:
        return self.name

    class Meta:
        verbose_name = _("机柜状态")
        verbose_name_plural = _("机柜状态")
        unique_together = ("data_center", "name")
        indexes = [
            models.Index(fields=["data_center", "shared", "name"]),
        ]


class RackBulkManager:
    """机柜批量操作管理器"""

    @staticmethod
    def _generate_pdu_names(pdu_16a_count: int, pdu_10a_count: int) -> List[tuple]:
        """
        生成PDU编号列表
        按对创建A、B路PDU，优先创建10A PDU
        例如：2个10A PDU + 2个16A PDU的顺序为：
        [(A01, 10A), (B01, 10A), (A02, 16A), (B02, 16A)]

        Args:
            pdu_16a_count: 16A PDU数量
            pdu_10a_count: 10A PDU数量

        Returns:
            List[tuple]: [(name, slot_type), ...] PDU名称和类型的元组列表
        """
        if pdu_16a_count < 0 or pdu_10a_count < 0:
            return []

        names = []
        # 先处理10A PDU
        pairs_10a = math.ceil(pdu_10a_count / 2)
        for i in range(pairs_10a):
            # 添加A路10A PDU
            if len(names) < pdu_10a_count:
                names.append((f"A{(i+1):02d}", PDUSlotChoices.A10))
            # 添加B路10A PDU
            if len(names) < pdu_10a_count:
                names.append((f"B{(i+1):02d}", PDUSlotChoices.A10))

        # 再处理16A PDU，序号继续递增
        start_num = pairs_10a + 1
        pairs_16a = math.ceil(pdu_16a_count / 2)
        for i in range(pairs_16a):
            # 添加A路16A PDU
            if len(names) < (pdu_16a_count + pdu_10a_count):
                names.append((f"A{(start_num+i):02d}", PDUSlotChoices.A16))
            # 添加B路16A PDU
            if len(names) < (pdu_16a_count + pdu_10a_count):
                names.append((f"B{(start_num+i):02d}", PDUSlotChoices.A16))

        return names

    @classmethod
    def bulk_create_pdus(cls, racks: List["Rack"]) -> None:
        """批量创建PDU"""
        pdus_to_create = []

        for rack in racks:
            # 获取已存在的PDU名称集合
            existing_pdu_names = set(
                RackPDU.objects.filter(rack=rack).values_list("name", flat=True)
            )

            # 生成需要的PDU名称列表
            pdu_names = cls._generate_pdu_names(
                rack.pdu_16a_count, rack.pdu_count - rack.pdu_16a_count  # 10A PDU数量
            )

            # 只创建不存在的PDU
            pdus_to_create.extend(
                [
                    RackPDU(
                        rack=rack,
                        data_center=rack.data_center,
                        name=name,
                        slot_type=slot_type,
                    )
                    for name, slot_type in pdu_names
                    if name not in existing_pdu_names  # 检查是否已存在
                ]
            )

        # 批量创建
        if pdus_to_create:
            RackPDU.objects.bulk_create(pdus_to_create)

    @classmethod
    def bulk_update_pdus(
        cls, old_racks: Dict[int, "Rack"], new_racks: List["Rack"]
    ) -> None:
        """批量更新PDU"""
        pdus_to_create = []
        pdus_to_delete: Set[int] = set()

        for new_rack in new_racks:
            old_rack = old_racks.get(new_rack.pk)
            if not old_rack:
                continue

            # 获取当前机柜的所有PDU，按类型分组
            current_pdus = RackPDU.objects.filter(rack=new_rack)
            current_10a_pdus = {
                pdu.name: pdu
                for pdu in current_pdus
                if pdu.slot_type == PDUSlotChoices.A10
            }
            current_16a_pdus = {
                pdu.name: pdu
                for pdu in current_pdus
                if pdu.slot_type == PDUSlotChoices.A16
            }

            # 计算新旧PDU数量
            old_total = old_rack.pdu_count
            new_total = new_rack.pdu_count
            old_16a = old_rack.pdu_16a_count
            new_16a = new_rack.pdu_16a_count
            old_10a = old_total - old_16a
            new_10a = new_total - new_16a

            # 生成需要的PDU名称列表
            needed_pdu_names = cls._generate_pdu_names(new_16a, new_10a)
            needed_10a_names = {
                name
                for name, slot_type in needed_pdu_names
                if slot_type == PDUSlotChoices.A10
            }
            needed_16a_names = {
                name
                for name, slot_type in needed_pdu_names
                if slot_type == PDUSlotChoices.A16
            }

            # 分别处理10A和16A PDU
            # 处理10A PDU
            pdus_10a_to_remove = [
                pdu
                for name, pdu in current_10a_pdus.items()
                if name not in needed_10a_names
            ]
            if new_10a < old_10a and any(
                p.status == "used" for p in pdus_10a_to_remove
            ):
                raise ValidationError(_("无法减少 10A PDU 数量：一些 PDU 正在使用中"))
            pdus_to_delete.update(p.id for p in pdus_10a_to_remove)

            # 处理16A PDU
            pdus_16a_to_remove = [
                pdu
                for name, pdu in current_16a_pdus.items()
                if name not in needed_16a_names
            ]
            if new_16a < old_16a and any(
                p.status == "used" for p in pdus_16a_to_remove
            ):
                raise ValidationError(_("无法减少 16A PDU 数量：一些 PDU 正在使用中"))
            pdus_to_delete.update(p.id for p in pdus_16a_to_remove)

            # 找出需要新建的PDU
            pdus_to_create.extend(
                [
                    RackPDU(
                        rack=new_rack,
                        data_center=new_rack.data_center,
                        name=name,
                        slot_type=slot_type,
                    )
                    for name, slot_type in needed_pdu_names
                    if (
                        slot_type == PDUSlotChoices.A10 and name not in current_10a_pdus
                    )
                    or (
                        slot_type == PDUSlotChoices.A16 and name not in current_16a_pdus
                    )
                ]
            )

        # 批量执行操作
        with transaction.atomic():
            if pdus_to_delete:
                RackPDU.objects.filter(id__in=pdus_to_delete).delete()
            if pdus_to_create:
                RackPDU.objects.bulk_create(pdus_to_create)

    @staticmethod
    def _check_pdus_in_use_bulk(rack: "Rack", slot_type: str, count: int) -> bool:
        """
        批量检查指定类型PDU使用情况

        Args:
            rack: 机柜实例
            slot_type: PDU类型 (10A/16A)
            count: 要检查的数量

        Returns:
            bool: 是否有PDU在使用中
        """
        return (
            RackPDU.objects.filter(
                rack=rack,
                slot_type=slot_type,
                status__in=[RackPDUStatusChoices.USED, RackPDUStatusChoices.FAULT],
                # is_used=True
            )
            .order_by("-name")[:count]
            .exists()
        )

    @staticmethod
    def expand_regex_pattern(pattern: str) -> List[str]:
        """展开正则表达式模式为所有可能的具值

        Args:
            pattern: 正则表达式模式，例如：
                    "3F01-[A-E][01-18]"
                    "R[1-9][0-9]"
                    "RACK-[A-C](0[1-9]|1[0-2])"

        Returns:
            List[str]: 所有匹配该模式的具体字符串列表
        """
        import exrex  # 需要安装: pip install exrex

        try:
            # 使用exrex库展开正则表达式
            return list(exrex.generate(pattern))
        except Exception as e:
            raise ValueError(f"无效的正则表达式模式: {str(e)}")

    @classmethod
    def bulk_create_from_regex(
        cls, pattern: str, data_center: "DataCenter", room: "Room", **defaults
    ) -> List["Rack"]:
        """根据正则表达式模式批量创建机柜

        Args:
            pattern: 正则表达式模式
            data_center: 数据中心实例
            room: 机房实例
            **defaults: 其他机柜默认参数
        """

        # 展开正则表达式获取所有机柜名称
        rack_names = cls.expand_regex_pattern(pattern)

        # 准备批量创建的机柜列表
        racks_to_create = [
            Rack(name=name, data_center=data_center, room=room, **defaults)
            for name in rack_names
        ]

        # 批量创建机柜
        return Rack.objects.bulk_create(racks_to_create)


class RackQuerySet(models.QuerySet):
    def with_space_usage(self):
        """
        预加载计算空间使用率所需的所有数据
        """
        from .devices import OnlineDevice

        # 子查询：统计每个机柜的设备占用U位总和
        device_subquery = (
            OnlineDevice.objects.filter(rack=OuterRef("pk"))
            .select_related("model")
            .values("rack")  # 按机柜分组
            .annotate(total_u=Sum("model__height"))  # 计算每个机柜的设备高度总和
            .values("total_u")  # 只获取总高度
        )

        # 返回预加载了使用率数据的查询集
        return self.annotate(
            total_u=F("u_height"),
            used_u=Coalesce(Subquery(device_subquery), 0),  # 使用Coalesce处理NULL值
        ).select_related("data_center")


class RackManager(models.Manager.from_queryset(RackQuerySet)):
    """机柜管理器"""

    def bulk_create(self, objs: List["Rack"], **kwargs) -> List["Rack"]:
        """重写批量创建方法"""
        # 在入库前为每个机柜根据电压自动补全额定功率/电流
        converter = PowerConverter()
        for obj in objs:
            if obj.rated_power_kw and not obj.rated_current:
                obj.rated_current = converter.kw_to_ampere(
                    float(obj.rated_power_kw), float(obj.voltage)
                )
            elif obj.rated_current and not obj.rated_power_kw:
                obj.rated_power_kw = converter.ampere_to_kw(
                    float(obj.rated_current), float(obj.voltage)
                )

        racks = super().bulk_create(objs, **kwargs)
        RackBulkManager.bulk_create_pdus(racks)
        # 批量创建完成后，统一刷新房间机柜计数
        from dcrm.signals.counters import update_counts  # 延迟导入以避免循环依赖

        update_counts(Room, "rack_count", "rack")
        return racks

    def bulk_update(self, objs: List["Rack"], fields: List[str], **kwargs) -> None:
        """重写批量更新方法"""
        # 获取更新前的实例
        old_racks = {
            rack.pk: rack for rack in self.filter(pk__in=[obj.pk for obj in objs])
        }

        # 执行批量更新
        super().bulk_update(objs, fields, **kwargs)

        # 如果涉及PDU数量的变化，更新相关记录
        if "pdu_count" in fields or "pdu_16a_count" in fields:
            RackBulkManager.bulk_update_pdus(old_racks, objs)


class Rack(BaseModel, CustomFieldsMixin, TrackingModelMixin):
    """机柜"""

    data_center = models.ForeignKey(
        to="dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("机柜所属的数据中心"),
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.PROTECT,
        verbose_name=_("房间"),
        help_text=_("机柜所在的房间"),
    )
    name = models.CharField(
        max_length=128, verbose_name=_("名称"), help_text=_("机柜名，例如：3F01-A01")
    )
    description = models.TextField(
        verbose_name=_("描述"), blank=True, null=True, help_text=_("机柜的详细描述")
    )
    u_height = DeviceHeightField(
        verbose_name=_("高度(U)"),
        blank=False,
        null=False,
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        default=45,
        help_text=_("机柜的U位数, 1U = 44.45mm"),
    )
    pdu_count = models.IntegerField(
        verbose_name=_("PDU总数"),
        validators=[MinValueValidator(0), MaxValueValidator(60)],
        default=30,
        help_text=_("机柜中所有PDU的总数量"),
    )
    pdu_16a_count = models.IntegerField(
        verbose_name=_("PDU数量(16A)"),
        validators=[MinValueValidator(0), MaxValueValidator(60)],
        default=0,
        blank=True,
        null=True,
        help_text=_("机柜中16A PDU的总数量"),
    )
    rack_type = models.SlugField(
        choices=RackTypeChoices.choices,
        default=RackTypeChoices.EXCLUSIVE,
        verbose_name=_("类型"),
        help_text=_("机柜的类型"),
    )
    status = models.ForeignKey(
        RackStatus,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name=_("状态"),
        help_text=_("机柜的状态, 空闲、占用、已使用等"),
    )
    rated_power_kw = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("额定功率(kW)"),
        help_text=_("额定电流乘以额定电压，20A * 220v = 4.4kw, 单位: 千瓦"),
    )
    rated_current = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("额定电流(A)"),
        help_text=_("额定功率除以额定电压, 4.4kw / 220v = 20A, 单位: 安培"),
    )
    voltage = models.IntegerField(
        default=220, verbose_name=_("电压(V)"), help_text=_("机柜的电压, 单位: 伏特")
    )
    tenant = models.ForeignKey(
        to="dcrm.Tenant",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name=_("租户"),
        help_text=_("机柜的租户"),
    )
    opening_date = models.DateField(
        verbose_name=_("开通日期"),
        blank=True,
        null=True,
        help_text=_("机柜租户合同的开通日期"),
    )
    contract_power = models.IntegerField(
        verbose_name=_("合同功率(A)"),
        blank=True,
        null=True,
        help_text=_("机柜和租户的合同功率, 单位: 安培"),
    )
    depth = models.PositiveIntegerField(
        default=120,
        blank=True,
        null=True,
        validators=[MinValueValidator(20), MaxValueValidator(130)],
        verbose_name=_("外观深度(cm)"),
        help_text=_("机架的深度，单位为厘米，通常为120 cm"),
    )
    width = models.PositiveIntegerField(
        default=60,
        blank=True,
        null=True,
        validators=[MinValueValidator(20), MaxValueValidator(120)],
        verbose_name=_("外观宽度(cm)"),
        help_text=_("机架的宽度，单位为厘米，标准为60 cm"),
    )
    height = models.PositiveIntegerField(
        default=200,
        blank=True,
        null=True,
        validators=[MinValueValidator(40), MaxValueValidator(250)],
        verbose_name=_("外观高度(cm)"),
        help_text=_("机架的高度，单位为厘米，通常为180~200 cm"),
    )
    tags = models.ManyToManyField(
        to="dcrm.Tag",
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "rack"),
        verbose_name=_("标签"),
        help_text=_("机柜的标签"),
    )
    position_x = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        blank=True,
        null=True,
        editable=False,
        verbose_name=_("X坐标"),
        help_text=_("机柜在房间中的X轴位置"),
    )
    position_y = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        blank=True,
        null=True,
        editable=False,
        verbose_name=_("Y坐标"),
        help_text=_("机柜在房间中的Y轴位置"),
    )
    position_z = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        blank=True,
        null=True,
        editable=False,
        verbose_name=_("Z坐标"),
        help_text=_("机柜在房间中的Z轴位置"),
    )
    row = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        editable=False,
        default=None,
        verbose_name=_("行号"),
    )
    col = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        editable=False,
        default=None,
        verbose_name=_("列号"),
    )
    device_count = CounterCacheField(
        to_model="dcrm.Device",
        to_field="rack",
        verbose_name=_("设备(台)"),
        help_text=_("含历史在线的设备总数"),
    )
    patchcord_count = CounterCacheField(
        to_model="dcrm.PatchCordNode",
        to_field="rack",
        verbose_name=_("跳线节点(个)"),
        help_text=_("含历史的跳线节点总数"),
    )

    objects = RackManager()

    _icon = "fa fa-building"
    display_link_field = "name"

    def __str__(self) -> str:
        return self.name

    class Meta:
        verbose_name = _("机柜")
        verbose_name_plural = _("机柜信息")
        unique_together = [("room", "name"), ("room", "row", "col")]
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["data_center", "status", "rack_type"]),
        ]

    def save(self, *args, **kwargs):
        """保存单个机柜"""
        is_new = self.pk is None

        if not is_new:
            old_instance = Rack.objects.get(pk=self.pk)
            old_pdu_count = old_instance.pdu_count

        # 使用事务确保数据一致性
        with transaction.atomic():
            # 保存机柜本身
            super().save(*args, **kwargs)

            if is_new:
                # 新建机柜：创建所有PDU
                RackBulkManager.bulk_create_pdus([self])
            else:
                # 更新机柜：根据变化更新PDU
                pdu_changed = any(
                    [
                        self.pdu_count != old_pdu_count,
                        self.pdu_16a_count != old_instance.pdu_16a_count,
                    ]
                )
                if pdu_changed:
                    RackBulkManager.bulk_update_pdus({self.pk: old_instance}, [self])

        # 更新房间中的机柜数量
        # self.update_room_rack_count()

        # 保存时自动转换功率和电流
        converter = PowerConverter()

        # 如果设置了额定功率，自动计算额定电流
        if self.rated_power_kw and not self.rated_current:
            self.rated_current = converter.kw_to_ampere(
                float(self.rated_power_kw), float(self.voltage)
            )

        # 如果设置了额定电流，自动计算额定功率
        elif self.rated_current and not self.rated_power_kw:
            self.rated_power_kw = converter.ampere_to_kw(
                float(self.rated_current), float(self.voltage)
            )

    def clean(self):
        """验证机柜数据"""
        super().clean()

        # 验证合同电力
        if self.contract_power and self.contract_power > self.rated_current:
            raise ValidationError({"contract_power": _("合同功率不能超过额定功率")})

        # 验证机柜类型, 跳线面板机柜不能有PDUs.
        # if self.rack_type == RackTypeChoices.PATCH_PANEL:
        #     if self.pdu_count > 0:
        #         raise ValidationError({"pdu_count": _("配线架机柜不能有PDUs")})
        #     if self.pdu_16a_count > 0:
        #         raise ValidationError({"pdu_16a_count": _("配线架机柜不能有16A PDUs")})

        # 验证PDU数量
        if self.pdu_count < 0:
            raise ValidationError({"pdu_count": _("PDU 计数不能为负数")})

        # 验证16A PDU数量不能超过数
        if self.pdu_16a_count > self.pdu_count:
            raise ValidationError({"pdu_16a_count": _("16A PDU 计数不能超过总计数")})

        # 如果是更新操作，验证PDU的减少是否安全
        if self.pk:
            old_instance = Rack.objects.get(pk=self.pk)
            old_total = old_instance.pdu_count
            old_16a = old_instance.pdu_16a_count
            old_10a = old_total - old_16a
            new_10a = self.pdu_count - self.pdu_16a_count

            # 检查16A PDU的减少
            if self.pdu_16a_count < old_16a:
                if (
                    RackPDU.objects.filter(
                        rack=self,
                        slot_type=PDUSlotChoices.A16,
                        status__in=[
                            RackPDUStatusChoices.USED,
                            RackPDUStatusChoices.FAULT,
                        ],
                        # is_used=True
                    )
                    .order_by("-name")[: old_16a - self.pdu_16a_count]
                    .exists()
                ):
                    raise ValidationError(
                        {"pdu_16a_count": _("不能减少 16A PDU 计数:一些PDUs正在使用")}
                    )

            # 检查10A PDU的减少
            if new_10a < old_10a:
                if (
                    RackPDU.objects.filter(
                        rack=self,
                        slot_type=PDUSlotChoices.A10,
                        status__in=[
                            RackPDUStatusChoices.USED,
                            RackPDUStatusChoices.FAULT,
                        ],
                        # is_used=True
                    )
                    .order_by("-name")[: old_10a - new_10a]
                    .exists()
                ):
                    raise ValidationError(
                        {"pdu_count": _("不能减少 10A PDU 计数:一些PDUs正在使用")}
                    )

    def update_room_rack_count(self):
        """
        更新机房机柜数量
        """
        if self.room:
            self.room.rack_count = Rack.objects.filter(room=self.room).count()
            self.room.save(update_fields=["rack_count"])

    @cached_property
    def units(self):
        """
        获取当前机柜U位
        """
        return range(self.u_height, 0, -1)

    @property
    def unit_devices(self):
        """
        获取每个U位对应的设备，并标记设备的起始位置

        Yields:
            Tuple[int, Optional[Device], bool]: (U位号, 设备对象, 是否为设备起始位置) 的元组
            - U位号: 机柜的U位编号（从上到下）
            - 设备对象: 该U位对应的设备，如果没有设备则为None
            - 是否为设备起始位置: True表示这是设备的第一个U位，用于判断是否需要合并显示
        """
        # 创建设备位置映射，记录设备和是否为起始位置
        device_map = {}
        for device in self.mounted_devices:  # mounted_devices已按position降序排序
            device_height = device.model.height
            # position是设备的最低点，需要计算出最高点
            end_position = device.position + device_height - 1
            # 从上到下遍历设备占用的U位（较大的U位到较小的U位）
            for u in range(end_position, device.position - 1, -1):
                device_map[u] = (device, u == end_position)

        # 从上到下遍历每个U位（大到小）
        for u in self.units:  # units返回的是从上到下的顺序（如45到1）
            if u in device_map:
                device, is_start = device_map[u]
                yield u, device, is_start
            else:
                yield u, None, False

    @cached_property
    def mounted_devices(self) -> models.QuerySet:
        """
        获取当前在架的所有设备
        """
        from dcrm.models import OnlineDevice

        devices = (
            OnlineDevice.objects.filter(rack=self)
            .select_related("model")
            .order_by("-position")
        )
        return devices

    @cached_property
    def unmounted_devices(self):
        """获取当前未在架的所有设备"""
        from dcrm.models import Device

        return list(
            Device.objects.filter(
                rack=self,
                position__isnull=True,
                status__in=[DeviceStatusChoices.UNMOUNTED, DeviceStatusChoices.DRAFT],
            ).select_related(
                "model",
            )
        )

    @cached_property
    def occupied_units(self) -> Set[int]:
        """
        获取所有已占用的U位集合
        使用cached_property缓存结果
        """
        occupied = set()
        for device in self.mounted_devices:
            for u in range(device.position, device.position + device.model.height):
                occupied.add(u)
        return occupied

    def get_occupied_units(self, exclude_id: int = None) -> Set[int]:
        """
        获取已占用的U位集合，支持排除指定设备

        Args:
            exclude_id: 需要排除的设备ID

        Returns:
            已占用的U位集合
        """
        if not exclude_id:
            return self.occupied_units

        # 如果需要排除设备，重新计算占用情况
        occupied = set()
        for device in self.mounted_devices:
            if device.id != exclude_id:
                for u in range(device.position, device.position + device.model.height):
                    occupied.add(u)
        return occupied

    @cached_property
    def available_units_map(self) -> Dict[int, List[int]]:
        """
        生成可用U位映射表
        key: 需要的U位数量
        value: 可用的起始位置列表
        """
        available_map = {}

        # 预计算1U到机柜最大高度的可用位置
        for height in range(1, self.u_height + 1):
            available = []
            for position in range(1, self.u_height + 1):
                # 检查从position开始的height个U位是否都可用
                is_available = True
                for u in range(position, min(position + height, self.u_height + 1)):
                    # 上架后设备会溢出机柜高度
                    overflow = (position + height) > (self.u_height + 1)
                    if u in self.occupied_units or overflow:
                        is_available = False
                        break

                if is_available:
                    available.append(position)

            available_map[height] = available

        return available_map

    def available_pdus(self, exclude_id: int = None) -> List[str]:
        pdus = self.get_available_pdus(self)
        # [{p.id: p.name} for p in pdus]
        return list(pdus.values("pk", "name"))

    def get_available_units(
        self, u_height: int = 1, exclude_id: int = None
    ) -> List[int]:
        """
        获取可用的U位起始位置列表

        Args:
            u_height: 需要的U位数量
            exclude_id: 需要排除的设备ID

        Returns:
            可用的U位起始位置列表
        """
        if not exclude_id:
            # 使用缓存的结果
            return self.available_units_map.get(u_height, [])

        # 如果需要排除设备，重新计算可用位置
        occupied_units = self.get_occupied_units(exclude_id)
        available = []

        for position in range(1, self.u_height + 1):
            is_available = True
            for u in range(position, min(position + u_height, self.u_height + 1)):
                if position == self.u_height and u_height > 1 or u in occupied_units:
                    is_available = False
                    break

            if is_available:
                available.append(position)

        return available

    def check_device_position(
        self, position: int, height: int, exclude_id: int = None
    ) -> bool:
        """
        检查设备是否可以放置在指定位置

        Args:
            position: 设备起始U位
            height: 设备高度
            exclude_id: 需要排除的设备ID

        Returns:
            位置是否可用
        """
        # 检查位置是否在机柜范围内
        if position < 1 or position + height - 1 > self.u_height:
            return False

        # 获取已占用的U位
        occupied_units = self.get_occupied_units(exclude_id)

        # 检查是否与其他设备冲突
        return not any(u in occupied_units for u in range(position, position + height))

    def refresh_from_db(self, *args, **kwargs):
        """从数据库重新加载实例时，清除所有缓存属性"""
        super().refresh_from_db(*args, **kwargs)

        # 清除所有缓存的属性
        cached_properties = ["mounted_devices", "occupied_units", "available_units_map"]

        for prop in cached_properties:
            if prop in self.__dict__:
                del self.__dict__[prop]

    def get_space_usage(self) -> dict:
        """
        获取空间使用情况，计算机柜可用空间和PDU数量。
        设备之间预留1U间隔，即：
        - 4U设备实际占用5U空间（4U + 1U间隔）
        - 2U设备实际占用3U空间（2U + 1U间隔）
        - 1U设备实际占用2U空间（1U + 1U间隔）

        Returns:
            dict: {
                'total_u': 机柜总U数,
                'used_u': 已使用U数,
                'free_u': 剩余U数,
                'continuous_spaces': 连续空间列表 [{'start': 起始U位, 'size': 连续U数}, ...],
                'available_pdus': {'10A': 可用10A PDU数, '16A': 可用16A PDU数},
                'device_capacity': {
                    '1U': 可安装1U设备数量,
                    '2U': 可安装2U设备数量,
                    '4U': 可安装4U设备数量
                }
            }
        """
        # 获取机柜总U数和已占用的U位
        total_u = self.u_height
        occupied_units = self.get_occupied_units()
        used_u = len(occupied_units)
        free_u = total_u - used_u

        # 计算连续空间
        continuous_spaces = []
        current_start = None
        current_size = 0

        for u in range(1, total_u + 1):
            if u not in occupied_units:
                if current_start is None:
                    current_start = u
                current_size += 1
            else:
                # 遇到已占用U位，记录当前连续空间段
                if current_start is not None:
                    continuous_spaces.append(
                        {"start": current_start, "size": current_size}
                    )
                    current_start = None
                    current_size = 0

        # 处理最后一段连续空间（如果存在）
        if current_start is not None:
            continuous_spaces.append({"start": current_start, "size": current_size})

        # 计算可用PDU数量
        available_pdus = self.pdus.filter(status=RackPDUStatusChoices.EMPTY).aggregate(
            A10=Count(
                Case(
                    When(slot_type=PDUSlotChoices.A10, then=1),
                    output_field=IntegerField(),
                )
            ),
            A16=Count(
                Case(
                    When(slot_type=PDUSlotChoices.A16, then=1),
                    output_field=IntegerField(),
                )
            ),
        )
        # 定义设备类型和所需空间的映射
        device_specs = {
            "4U": {"required_space": 5, "height": 4},
            "2U": {"required_space": 3, "height": 2},
            "1U": {"required_space": 2, "height": 1},
        }

        # 初始化容量字典
        device_capacity = {size: 0 for size in device_specs}

        # 获取PDU限制（一次性查询）
        pdu_limit = self.pdus.count() // 2

        # 计算每种设备的可安装数量
        for space in continuous_spaces:
            # 减去预留空间后的实际可用空间
            available_space = space["size"] - 1  # 预留1U间隔
            if available_space <= 0:
                continue

            # 一次性计算所有设备类型的容量
            for size, specs in device_specs.items():
                if available_space >= specs["required_space"]:
                    capacity = available_space // specs["required_space"]
                    device_capacity[size] += min(capacity, pdu_limit)

        return {
            "total_u": total_u,
            "used_u": used_u,
            "free_u": free_u,
            "continuous_spaces": continuous_spaces,
            "available_pdus": available_pdus,
            "device_capacity": device_capacity,
        }

    @cached_property
    def space_usage(self):
        """获取空间使用情况"""
        percentage = self.space_usage_percentage()
        # 定义为类属性，方便统一管理
        WARN_RATE = self.data_center.get_config("WARN_RACK_SPACE_USED", 50)
        USAGE_COLOR_THRESHOLDS = {
            70: "danger",
            WARN_RATE: "warning",
            30: "success",
            0: "info",
        }
        # 找到第一个小于等于当前百分比的阈值对应的颜色
        color = next(
            f"progress-bar-{color}"
            for threshold, color in sorted(USAGE_COLOR_THRESHOLDS.items(), reverse=True)
            if percentage >= threshold
        )

        progress = """
        <div class="progress no-padding" style="margin-top: 0;">
            <div title="机柜U位使用率 {used_u}%" class="progress-bar {color}" role="progressbar" 
                 aria-valuenow="{used_u}" aria-valuemin="0" aria-valuemax="100" style="width: {used_u}%">
                <span style="color: #333;">{used_u}%</span>
            </div>
        </div>
        """
        return format_html(progress, used_u=percentage, color=color)

    space_usage.short_description = _("使用率")

    def space_usage_percentage(self):
        """获取空间使用情况"""
        # 优先使用预加载的数据
        if hasattr(self, "used_u") and hasattr(self, "total_u"):
            used_u = self.used_u or 0
            total_u = self.total_u
        else:
            # 回退到原有的计算方式
            total_u = self.u_height
            occupied_units = self.get_occupied_units()
            used_u = len(occupied_units)

        percentage = round(used_u / total_u * 100, 1) if total_u else 0
        return percentage

    def get_power_usage(self) -> dict:
        """获取功率使用情况"""
        converter = PowerConverter()

        # 获取当前电流
        current_metrics = self.get_current_metrics()
        current_a = current_metrics.get("power_a", 0)
        current_b = current_metrics.get("power_b", 0)

        # 计算当前功率
        power_a = converter.ampere_to_kw(current_a, self.voltage)
        power_b = converter.ampere_to_kw(current_b, self.voltage)

        return {
            "current": {"a": current_a, "b": current_b, "total": current_a + current_b},
            "power": {"a": power_a, "b": power_b, "total": power_a + power_b},
            "utilization": round(
                (
                    ((power_a + power_b) / float(self.rated_power_kw)) * 100
                    if self.rated_power_kw
                    else 0
                ),
                2,
            ),
        }

    def get_available_patch_ports(self):
        """获取可用的配线架端口"""
        from dcrm.models import DevicePort

        from .choices import DeviceTypeChoices

        # 获取机柜中的配线架设备
        patch_panels = self.mounted_devices.filter(
            model__type=DeviceTypeChoices.PATCH_PANEL
        )
        # 获取所有配线架设备的可用端口
        available_ports = DevicePort.objects.none()
        for panel in patch_panels:
            available_ports = available_ports | panel.get_available_ports()
        return available_ports.order_by("name")

    def allow_add_devices(self):
        """
        根据机柜状态，分配的租户情况，返回机柜是否可以添加设备的信息
        Return:
            bool, str
        """
        if self.status and self.status.allowed_mount:
            if self.tenant_id and self.rack_type != RackTypeChoices.PATCH_PANEL:
                check = True, _(f"添加设备")
            elif self.rack_type == RackTypeChoices.SHARED:
                check = True, _(f"添加设备时请选择散U租户")
            elif self.rack_type == RackTypeChoices.PATCH_PANEL:
                check = True, _(f"添加配线设备")
            else:
                check = False, _("请分配租户后，再添加设备")
        else:
            status = self.status if self.status else "未设置"
            check = False, _(f"机柜{status}状态, 请先分配租户")
        return check

    @classmethod
    def get_available_pdus(cls, rack: "Rack"):
        """获取可用的PDU"""
        return RackPDU.objects.filter(rack=rack, status=RackPDUStatusChoices.EMPTY)


class RackPDU(BaseModel, CustomFieldsMixin):
    """机柜PDU"""

    data_center = models.ForeignKey(
        to="dcrm.DataCenter",
        on_delete=models.CASCADE,
        verbose_name=_("数据中心"),
        help_text=_("数据中心"),
    )
    rack = models.ForeignKey(
        Rack,
        on_delete=models.CASCADE,
        related_name="pdus",
        verbose_name=_("机柜"),
        help_text=_("PDU所属的机柜"),
    )
    name = models.CharField(
        max_length=128, verbose_name=_("名称"), help_text=_("PDU的名称")
    )
    slot_type = models.SlugField(
        max_length=128,
        choices=PDUSlotChoices.choices,
        default=PDUSlotChoices.A10,
        verbose_name=_("插槽类型"),
        help_text=_("PDU插槽的类型, 10A 插槽和 16A 插槽"),
    )
    status = models.CharField(
        max_length=100,
        choices=RackPDUStatusChoices.choices,
        default=RackPDUStatusChoices.EMPTY,
        verbose_name=_("PDU状态"),
        help_text=_("机柜PDU状态，使用中，空闲，故障"),
    )

    _icon = "fa fa-plug"
    display_link_field = "name"
    search_fields = ["name"]
    supports_import = False

    def __str__(self) -> str:
        if self.slot_type == PDUSlotChoices.A10:
            return f"{self.name}"
        return f"{self.name} ({self.slot_type})"

    def get_natural_name(self) -> str:
        """获取自然名称"""
        return f"{self.rack.name}[{self.name}]"

    class Meta:
        verbose_name = _("机柜PDU")
        verbose_name_plural = _("机柜PDU")
        ordering = ["pk"]
        unique_together = [("rack", "name")]
        indexes = [
            models.Index(fields=["data_center", "status"]),
        ]
