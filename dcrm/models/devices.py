import logging

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.forms.models import model_to_dict
from django.utils.translation import gettext_lazy as _

from .base import BaseModel, CustomFieldsMixin
from .choices import (
    DeviceHostAuthTypeChoices,
    DeviceHostGroupChoices,
    DeviceHostStatusChoices,
    DevicePortStatusChoices,
    DevicePortTypeChoices,
    DeviceStatusChoices,
)
from .fields import CounterCacheField, DeviceHeightField, RackPositionField
from .mixins import ColorMixin, IconMixin
from .networks import IPAddress
from .tracking import TrackingModelMixin
from .utils import tag_limit_filter

logger = logging.getLogger(__name__)


__all__ = [
    "DeviceType",
    "DeviceModel",
    "Device",
    "OnlineDevice",
    "DevicePort",
    "DeviceHost",
    "DeviceModelOID",
]


class DeviceType(BaseModel, ColorMixin, IconMixin, CustomFieldsMixin):
    """设备角色，例如交换机、路由器、服务器、防火墙等等
    """

    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("设备类型所属的数据中心"),
    )
    name = models.CharField(
        max_length=128,
        verbose_name=_("名称"),
        help_text=_("例如服务器、路由器、交换机等"),
    )
    code = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("类型编码"),
        help_text=_("例如Router、Switch、Server..."),
    )
    description = models.TextField(
        verbose_name=_("描述"),
        blank=True,
        null=True,
        help_text=_("设备类型的详细描述"),
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
        limit_choices_to=tag_limit_filter("dcrm", "devicerole"),
        verbose_name=_("标签"),
        help_text=_("设备类型的标签"),
    )

    _icon = "fa fa-folder-open-o"
    display_link_field = "name"
    search_fields = ["name", "code"]
    supports_import = True

    def __str__(self) -> str:
        return self.name

    class Meta:
        verbose_name = _("设备类型")
        verbose_name_plural = _("设备类型")
        unique_together = (("data_center", "name"), ("data_center", "code"))
        indexes = [
            models.Index(fields=["data_center", "shared", "name"]),
        ]


class DeviceModel(BaseModel, CustomFieldsMixin):
    """设备型号模型
    """

    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("设备型号所属的数据中心"),
    )
    manufacturer = models.ForeignKey(
        "dcrm.Manufacturer",
        on_delete=models.PROTECT,
        verbose_name=_("制造商"),
        help_text=_("Dell、Huawei、H3C、Cisco等"),
    )
    name = models.CharField(
        max_length=128,
        verbose_name=_("设备型号"),
        help_text=_("PowerEdge R720xd、Cisco C9300等"),
    )
    type = models.ForeignKey(
        DeviceType,
        on_delete=models.PROTECT,
        verbose_name=_("设备类型"),
        help_text=_("如服务器、配线架、交换机、UPS等"),
    )
    height = DeviceHeightField(
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(60)],
        verbose_name=_("高度"),
        help_text=_("设备在机柜中占用的高度单位(U)"),
    )

    # 端口数量字段
    ethernet_port_count = models.PositiveIntegerField(
        default=4,
        validators=[MinValueValidator(0)],
        blank=True,
        null=True,
        verbose_name=_("以太网端口"),
        help_text=_("例如：24口交换机有24个以太网端口数量"),
    )
    fiber_port_count = models.PositiveIntegerField(
        default=2,
        validators=[MinValueValidator(0)],
        blank=True,
        null=True,
        verbose_name=_("光纤端口"),
        help_text=_("例如：48口交换机有48个光纤端口数量"),
    )
    console_port_count = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        blank=True,
        null=True,
        verbose_name=_("Console端口"),
        help_text=_("例如：1台交换机有1个Console端口数量"),
    )
    usb_port_count = models.PositiveIntegerField(
        default=4,
        validators=[MinValueValidator(0)],
        blank=True,
        null=True,
        verbose_name=_("USB端口"),
        help_text=_("例如：1台服务器有6个USB端口数量"),
    )
    power_port_count = models.PositiveIntegerField(
        default=2,
        validators=[MinValueValidator(0)],
        blank=True,
        null=True,
        verbose_name=_("电源端口"),
        help_text=_("例如：1台服务器有2个电源端口数量"),
    )
    mgmt_port_count = models.PositiveIntegerField(
        default=1,
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
        verbose_name=_("管理端口"),
        help_text=_("例如：1台服务器有1个管理端口数量"),
    )
    other_port_count = models.PositiveIntegerField(
        default=0,
        blank=True,
        null=True,
        validators=[MinValueValidator(0)],
        verbose_name=_("其他端口"),
        help_text=_("例如：1台服务器有2个VGA端口数量"),
    )
    # 描述
    description = models.TextField(
        verbose_name=_("描述"),
        blank=True,
        null=True,
        help_text=_("设备型号的详细描述"),
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
        limit_choices_to=tag_limit_filter("dcrm", "devicemodel"),
        verbose_name=_("标签"),
        help_text=_("设备型号的标签"),
    )
    _icon = "fa fa-folder-open-o"
    display_link_field = "name"
    search_fields = ["name"]
    supports_import = True

    def __str__(self) -> str:
        return self.name

    class Meta:
        verbose_name = _("设备型号")
        verbose_name_plural = _("设备型号")
        unique_together = ("data_center", "name")
        indexes = [
            # 原有索引
            models.Index(fields=["data_center", "shared"]),
            # 新增优化索引
            models.Index(
                fields=["manufacturer", "name"], name="idx_devicemodel_mfr_name"
            ),
            models.Index(
                fields=["type", "manufacturer"], name="idx_devicemodel_type_mfr"
            ),
            models.Index(
                fields=["data_center", "type", "manufacturer"],
                name="idx_devicemodel_dc_type_mfr",
            ),
            models.Index(fields=["height"], name="idx_devicemodel_height"),
            # 端口数量查询优化
            models.Index(
                fields=["ethernet_port_count"], name="idx_devicemodel_eth_ports"
            ),
            models.Index(
                fields=["fiber_port_count"], name="idx_devicemodel_fiber_ports"
            ),
            # 部分索引 - 仅为共享型号
            models.Index(
                fields=["name"],
                condition=models.Q(shared=True),
                name="idx_devicemodel_shared_only",
            ),
        ]


class DeviceModelOID(BaseModel):
    """设备型号OID
    """

    device_model = models.ForeignKey(
        "dcrm.DeviceModel",
        on_delete=models.CASCADE,
        verbose_name=_("设备型号"),
        help_text=_("设备型号"),
    )
    name = models.CharField(
        max_length=100,
        verbose_name=_("名称"),
        help_text=_("SNMP OID 名称"),
    )
    oid = models.CharField(
        max_length=128,
        verbose_name=_("OID"),
        help_text=_("设备型号SNMP OID"),
    )
    description = models.TextField(
        verbose_name=_("描述"),
        blank=True,
        null=True,
        help_text=_("设备型号SNMP OID的描述"),
    )
    tags = models.ManyToManyField(
        to="dcrm.Tag",
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "devicemodeloid"),
        verbose_name=_("标签"),
        help_text=_("设备型号SNMP OID的标签"),
    )
    _icon = "fa fa-thumb-tack"
    display_link_field = "oid"
    search_fields = ["oid"]
    supports_import = True

    class Meta:
        verbose_name = _("设备型号OID")
        verbose_name_plural = _("设备型号OID")
        unique_together = ("device_model", "oid")
        indexes = [
            models.Index(fields=["device_model", "oid"]),
        ]


class DeviceBulkManager:
    """设备批量管理类
    """

    @staticmethod
    def _generate_port_names(port_count: int, port_type: str) -> list[str]:
        """生成端口名称列表
        ethernet: ethernet0, ethernet1, ethernet2, ...
        fiber: fiber0, fiber1, fiber2, ...
        console: console0, console1, console2, ...
        mgmt: mgmt0, mgmt1, mgmt2, ...
        usb: usb0, usb1, usb2, ...
        power: power0, power1, power2, ...
        other: other0, other1, other2, ...

        Return:
            端口名称列表[str]

        """
        return [f"{port_type}{i}" for i in range(0, port_count)]

    @staticmethod
    def generate_port_names_by_device_model(device_model: DeviceModel) -> list[str]:
        """根据设备型号生成端口名称列表"""
        device_ports = []
        for port_type in DevicePortTypeChoices.values:
            port_count = model_to_dict(device_model).get(port_type + "_port_count", 0)
            device_ports.extend(
                DeviceBulkManager._generate_port_names(port_count, port_type)
            )
        return device_ports


class Device(BaseModel, CustomFieldsMixin, TrackingModelMixin):
    """设备模型
    """

    # 基础信息
    name = models.CharField(
        max_length=128,
        verbose_name=_("名称"),
        help_text=_("例如：自定义编号、主机名等"),
    )
    serial_number = models.CharField(
        max_length=128,
        unique=True,
        blank=True,
        null=True,
        verbose_name=_("序列号"),
        help_text=_("设备的序列号"),
    )
    position = RackPositionField(
        validators=[MinValueValidator(1), MaxValueValidator(60)],
        verbose_name=_("位置"),
        help_text=_("设备在机柜中的位置(U)"),
    )
    # 关联关系
    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("设备所属的数据中心"),
    )
    rack = models.ForeignKey(
        "dcrm.Rack",
        on_delete=models.PROTECT,
        verbose_name=_("机柜"),
        help_text=_("设备所在的机柜"),
    )
    model = models.ForeignKey(
        DeviceModel,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name=_("设备型号"),
        help_text=_("设备型号，如PowerEdge R720xd，选择可快速填充高度和类型"),
    )
    type = models.ForeignKey(
        DeviceType,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        verbose_name=_("设备类型"),
        help_text=_("如服务器、配线架、交换机、UPS等"),
    )
    height = DeviceHeightField(
        validators=[MinValueValidator(0), MaxValueValidator(60)],
        blank=True,
        null=True,
        verbose_name=_("高度"),
        help_text=_("设备在机柜中占用的高度单位(U)"),
    )
    tenant = models.ForeignKey(
        "dcrm.Tenant",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name=_("租户"),
        help_text=_("设备所属的租户"),
    )
    rack_pdus = models.ManyToManyField(
        "dcrm.RackPDU",
        blank=True,
        related_name="rack_pdus",
        verbose_name=_("PDUs"),
        help_text=_("设备所在的机柜PDUs"),
    )
    ips = models.ManyToManyField(
        "dcrm.IPAddress",
        related_name="devices",
        blank=True,
        verbose_name=_("IP地址"),
        help_text=_("设备的所有IP地址"),
    )

    # 状态/标记
    status = models.SlugField(
        choices=DeviceStatusChoices.choices,
        default=DeviceStatusChoices.MOUNTED,
        max_length=128,
        blank=True,
        null=True,
        verbose_name=_("状态"),
        help_text=_("设备的状态"),
    )
    tags = models.ManyToManyField(
        "dcrm.Tag",
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "device"),
        verbose_name=_("标签"),
        help_text=_("设备的其他标签"),
    )

    # 监控和维护信息
    warranty_expiry = models.DateField(
        blank=True, null=True, verbose_name=_("过保日期"), help_text=_("设备保修到期日")
    )
    ports_count = CounterCacheField(
        to_model="dcrm.DevicePort",
        to_field="device",
        verbose_name=_("端口(个)"),
    )
    host_count = CounterCacheField(
        to_model="dcrm.DeviceHost",
        to_field="device",
        verbose_name=_("主机(台)"),
    )

    _icon = "fa fa-server"
    display_link_field = "name"
    search_fields = [
        "name",
    ]
    supports_import = True

    def __str__(self) -> str:
        return self.name

    def natural_key(self):
        return (self.data_center, self.name)

    class Meta:
        verbose_name = _("所有设备")
        verbose_name_plural = _("所有设备")
        unique_together = ("data_center", "name")
        ordering = ["-updated_at"]
        indexes = [
            # 原有索引
            models.Index(fields=["data_center", "name"]),
            models.Index(fields=["status"]),
            # 新增优化索引
            # models.Index(fields=["rack", "position"], name="idx_device_rack_position"),
            models.Index(fields=["model", "status"], name="idx_device_model_status"),
            models.Index(
                fields=["data_center", "status", "updated_at"],
                name="idx_device_dc_status_updated",
            ),
            models.Index(fields=["tenant", "status"], name="idx_device_tenant_status"),
            models.Index(fields=["serial_number"], name="idx_device_serial"),
            models.Index(fields=["type", "status"], name="idx_device_type_status"),
            # 资产管理优化
            models.Index(fields=["warranty_expiry"], name="idx_device_warranty_expiry"),
            # 部分索引 - 仅为活跃设备
            models.Index(
                fields=["name", "updated_at"],
                condition=models.Q(status__in=["mounted", "active", "maintenance"]),
                name="idx_device_active_only",
            ),
        ]

    @property
    def primary_ip(self):
        return self.ips.filter(is_primary=True).first()

    @property
    def oob_ip(self):
        return self.ips.filter(is_management=True).first()

    @property
    def is_online(self):
        # 可以通过SNMP监控状态判断设备在线状态
        return self.status in [
            DeviceStatusChoices.MOUNTED,
            DeviceStatusChoices.MIGRATED,
        ]

    def unmount_related_collections(self):
        """下架设备时收集相关联对象
        1. 机柜U位, （自动完成）
        2. 机柜PDU位，电源端口
        2. IP地址
        3. 跳线端口
        返回字典
        """
        data = {
            "pdus": self.rack_pdus.all(),
            "ips": self.ips.all(),
            "ports": self.ports.all(),
            "patch_cord_nodes": self.patch_cord_nodes.all(),
        }
        return data

    def assign_ip(self, ip: IPAddress):
        """分配IP地址"""
        self.ips.add(ip)

    def remove_ip(self, ip: IPAddress):
        """移除IP地址"""
        self.ips.remove(ip)

    def _sync_ports(self):
        """同步设备端口"""
        # 获取当前所有端口
        current_ports = {port.name: port for port in self.ports.all()}
        port_type_maps = {
            "ethernet": _("以太网口"),
            "fiber": _("光纤口"),
            "console": _("Console口"),
            "usb": _("USB口"),
            "power": _("电源口"),
            "mgmt": _("管理口"),
            "other": _("其他口"),
        }
        # 根据设备型号生成需要的端口
        port_list = []
        for port_type in DevicePortTypeChoices.values:
            port_count = getattr(self.model, f"{port_type}_port_count", 0)
            for i in range(1, port_count + 1):
                port_name = port_type_maps.get(port_type) + str(i).zfill(2)
                if port_name in current_ports:
                    # 端口已存在，从当前端口字典中移除
                    del current_ports[port_name]
                else:
                    # 创建新端口
                    port_list.append(
                        DevicePort(
                            data_center=self.data_center,
                            device=self,
                            name=port_name,
                            port_type=port_type,
                            created_by=self.created_by,
                        )
                    )
        # 批量创建新端口
        if port_list:
            DevicePort.objects.bulk_create(port_list)
        # 删除多余的端口
        # TODO: 需要考虑端口连接状态
        if current_ports:
            DevicePort.objects.filter(
                pk__in=[p.pk for p in current_ports.values()]
            ).delete()

    def save(self, *args, **kwargs):
        """保存设备"""
        is_new = self.pk is None
        if not is_new:
            old_device = Device.objects.get(pk=self.pk)
            model_changed = old_device.model_id != self.model_id
            # 如果设备U位发生变化，改变设备的状态为迁移
            is_merge = (
                (
                    old_device.position != self.position
                    or old_device.rack_id != self.rack_id
                )
                and old_device.status == DeviceStatusChoices.MOUNTED  # 上架设备
                and self.status == DeviceStatusChoices.MOUNTED  # 防止重设状态
            )
            if is_merge:
                self.status = DeviceStatusChoices.MIGRATED
        else:
            model_changed = False
        super().save(*args, **kwargs)
        # 如果设备型号发生变化，则同步端口
        if model_changed:
            self._sync_ports()

    def clean(self):
        """清理设备"""
        # 验证机柜状态，如果机柜状态不在允许上架设备的状态列表中，则不能上架设备
        if self.rack.status and not self.rack.status.allowed_mount:
            if self.status == DeviceStatusChoices.MOUNTED:
                raise ValidationError(
                    {
                        "status": _(
                            f"当前机柜状态为 {self.rack.status} 状态, 不允许上架设备"
                        )
                    }
                )
        if not self.model:
            if not self.type:
                raise ValidationError({"type": _("设备型号和类型必须填写一个")})
            if not self.height:
                raise ValidationError({"height": _("设备型号和高度必须填写一个")})
        if self.serial_number:
            self.serial_number = self.serial_number.upper()

    def get_available_ports(self):
        """获取可用的端口"""
        return self.ports.filter().order_by("name")


class OnlineDeviceManager(models.Manager):
    def get_queryset(self) -> models.QuerySet:
        queryset = super().get_queryset()
        return queryset.filter(
            status__in=[DeviceStatusChoices.MOUNTED, DeviceStatusChoices.MIGRATED]
        )


class OnlineDevice(Device):
    objects = OnlineDeviceManager()

    class Meta:
        proxy = True
        verbose_name = _("在线设备")
        verbose_name_plural = _("在线设备")


class DevicePort(BaseModel, CustomFieldsMixin, TrackingModelMixin):
    """设备端口模型
    用于描述设备型号的端口信息
    """

    # 基础信息
    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("设备端口所属的数据中心"),
    )
    connected_to = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        limit_choices_to={"app_label": "dcrm", "model__in": ["rackpdu", "deviceport"]},
        blank=True,
        null=True,
        verbose_name=_("连接到"),
        help_text=_("连接的对象类型"),
    )
    connected_object_id = models.PositiveIntegerField(
        blank=True, null=True, verbose_name=_("连接对象ID"), help_text=_("连接的对象ID")
    )
    connected_object = GenericForeignKey(
        "connected_to",
        "connected_object_id",
    )
    connected_object.short_description = _("连接对象")
    device = models.ForeignKey(
        Device,
        on_delete=models.CASCADE,
        related_name="ports",
        verbose_name=_("设备"),
        help_text=_("设备端口所属的设备"),
    )
    name = models.CharField(
        max_length=128,
        verbose_name=_("名称"),
        help_text=_("端口名称, 例如: eth0, em1, Port48 等"),
    )
    port_type = models.CharField(
        choices=DevicePortTypeChoices.choices,
        default=DevicePortTypeChoices.ETHERNET,
        max_length=128,
        verbose_name=_("类型"),
        help_text=_("设备端口的类型, 如以太网、光纤、Console、USB、电源端口等"),
    )
    status = models.SlugField(
        choices=DevicePortStatusChoices.choices,
        default=DevicePortStatusChoices.DISCONNECTED,
        verbose_name=_("连接状态"),
        help_text=_("设备端口的连接状态，当有效跳线连接时为已连接，否则为未连接"),
    )
    description = models.TextField(
        blank=True, null=True, verbose_name=_("描述"), help_text=_("设备端口的详细描述")
    )
    tags = models.ManyToManyField(
        to="dcrm.Tag",
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "deviceport"),
        verbose_name=_("标签"),
        help_text=_("设备端口的标签"),
    )

    _icon = "fa fa-plug"
    display_link_field = "name"
    search_fields = ["name"]
    supports_import = True

    def __str__(self) -> str:
        return self.name

    def natural_key(self):
        return (self.name, self.port_type)

    class Meta:
        verbose_name = _("设备端口")
        verbose_name_plural = _("设备端口")
        ordering = ["-updated_at"]
        unique_together = ("device", "name")
        indexes = [
            # 原有索引
            models.Index(fields=["device", "status", "port_type"]),
            # 新增优化索引
            models.Index(fields=["device", "name"]),
            models.Index(fields=["status", "port_type"]),
            models.Index(fields=["device", "port_type", "status"]),
            # 连接状态优化
            models.Index(fields=["connected_to", "connected_object_id"]),
            # 部分索引 - 仅为可用端口
            models.Index(
                fields=["device", "port_type"],
                condition=models.Q(status="available"),
                name="deviceport_available_only",
            ),
        ]

    def get_pre_connected(self, user):
        """是否预连接"""
        cache_key = f"pre_connected_{self.pk}_{user.pk}"
        return cache.get(cache_key, False)

    def set_pre_connected(self, user):
        """设置预连接"""
        cache_key = f"pre_connected_{self.pk}_{user.pk}"
        cache.set(cache_key, True)

    def clear_pre_connected(self, user):
        """清除预连接"""
        cache_key = f"pre_connected_{self.pk}_{user.pk}"
        cache.delete(cache_key)

    def is_pre_connected(self):
        """是否预连接，不进行用户判断，直接从缓存中获取"""
        # 注意：此方法依赖于缓存后端的实现，如果使用不支持模式匹配的缓存后端可能无法工作
        try:
            # 尝试使用django-redis的scan_iter方法（如果可用）
            from django_redis import get_redis_connection

            redis_client = get_redis_connection("default")
            pattern = f"pre_connected_{self.pk}_*"
            # 使用SCAN而不是KEYS，避免阻塞Redis
            return bool(list(redis_client.scan_iter(match=pattern, count=1)))
        except (ImportError, AttributeError):
            # 如果django-redis不可用，回退到简单检查
            # 注意：这种方法不够准确，但至少不会崩溃
            logger.warning(
                "django-redis not available, is_pre_connected may not work correctly"
            )
            return False

    is_pre_connected.short_description = _("已连接")

    def is_pre_connected_by_user(self, user):
        """是否预连接，根据用户判断"""
        return self.get_pre_connected(user)

    is_pre_connected_by_user.short_description = _("已连接")

    def get_pre_connected_by_user(self, user):
        """获取用户所有预连接端口ID"""
        # 使用Django缓存框架的标准API
        try:
            from django_redis import get_redis_connection

            redis_client = get_redis_connection("default")
            pattern = f"pre_connected_*_{user.pk}"
            # 使用SCAN而不是KEYS，避免阻塞Redis
            # 提取端口ID（从缓存键中解析）
            port_ids = []
            for key in redis_client.scan_iter(match=pattern, count=100):
                # 缓存键格式: pre_connected_{port_id}_{user_id}
                # 提取端口ID
                key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                parts = key_str.split("_")
                if len(parts) >= 3:
                    try:
                        port_id = int(parts[2])
                        port_ids.append(port_id)
                    except (ValueError, IndexError):
                        continue
            return port_ids
        except (ImportError, AttributeError):
            logger.warning(
                "django-redis not available, get_pre_connected_by_user may not work correctly"
            )
            return []

    def save(self, *args, **kwargs):
        # DevicePort 保存时不需要检查设备型号的端口数量变化
        # 端口数量变化应该在 DeviceModel.save() 中通过信号处理
        super().save(*args, **kwargs)

    def clean(self):
        """清理设备端口"""
        if self.device.ports.filter(name=self.name).exclude(pk=self.pk).exists():
            raise ValidationError(_("端口名称已存在"))


class DeviceHost(BaseModel, CustomFieldsMixin, TrackingModelMixin):
    """设备主机模型
    用于管理设备上的主机系统信息
    """

    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("主机所属的数据中心"),
    )
    # 基础信息
    name = models.CharField(
        max_length=128, verbose_name=_("名称"), help_text=_("主机名称")
    )
    hostname = models.CharField(
        max_length=128, verbose_name=_("主机名"), help_text=_("系统主机名")
    )

    # 系统信息
    os_type = models.CharField(
        max_length=64,
        verbose_name=_("OS类型"),
        help_text=_("如 Linux、Windows、AIX、HP-UX、Unix、Solaris 等"),
    )
    os_version = models.CharField(
        max_length=64,
        verbose_name=_("操作系统"),
        help_text=_("如 CentOS 7.9、Windows Server 2019 等"),
    )
    kernel_version = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        verbose_name=_("内核版本"),
        help_text=_("操作系统内核版本"),
    )

    # 硬件资源
    cpu_cores = models.PositiveIntegerField(
        blank=True, null=True, verbose_name=_("CPU核心数"), help_text=_("CPU逻辑核心数")
    )
    memory_size = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name=_("内存大小(GB)"),
        help_text=_("物理内存大小，单位GB"),
    )
    disk_size = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name=_("磁盘大小(GB)"),
        help_text=_("总磁盘大小，单位GB"),
    )

    # 关联关系
    device = models.ForeignKey(
        "Device",
        on_delete=models.CASCADE,
        related_name="hosts",
        verbose_name=_("所属设备"),
        help_text=_("主机所在的物理设备"),
    )
    # IP地址
    ips = models.ManyToManyField(
        "dcrm.IPAddress",
        related_name="hosts",
        blank=True,
        verbose_name=_("IP地址"),
        help_text=_("主机的IP地址"),
    )

    # 状态信息
    status = models.SlugField(
        max_length=128,
        choices=DeviceHostStatusChoices.choices,
        default=DeviceHostStatusChoices.ONLINE,
        verbose_name=_("状态"),
        help_text=_("主机运行状态"),
    )
    group = models.SlugField(
        max_length=128,
        choices=DeviceHostGroupChoices.choices,
        default=DeviceHostGroupChoices.TEST,
        verbose_name=_("分组"),
        help_text=_("如测试机系统、内部OA系统、开发环境等"),
    )
    # 标签
    tags = models.ManyToManyField(
        "dcrm.Tag",
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "devicehost"),
        verbose_name=_("标签"),
        help_text=_("主机标签"),
    )

    # 描述
    description = models.TextField(
        blank=True, null=True, verbose_name=_("描述"), help_text=_("主机描述信息")
    )

    # 用户认证信息
    username = models.CharField(
        max_length=64,
        default="root",
        verbose_name=_("用户名"),
        help_text=_("登录用户名，默认为root"),
    )
    _password = models.CharField(
        max_length=256,
        blank=True,
        null=True,
        verbose_name=_("密码"),
        help_text=_("登录密码，使用加密存储"),
    )
    ssh_port = models.PositiveIntegerField(
        default=22, verbose_name=_("SSH端口"), help_text=_("SSH服务端口，默认22")
    )
    ssh_key = models.TextField(
        blank=True, null=True, verbose_name=_("SSH密钥"), help_text=_("SSH私钥内容")
    )

    # 认证方式选择
    auth_type = models.SlugField(
        max_length=128,
        choices=DeviceHostAuthTypeChoices.choices,
        default=DeviceHostAuthTypeChoices.PASSWORD,
        verbose_name=_("认证方式"),
        help_text=_("主机登录认证方式"),
    )

    _icon = "fa fa-desktop"
    display_link_field = "name"
    supports_import = True
    search_fields = [
        "name",
    ]

    def __str__(self) -> str:
        return self.name

    class Meta:
        verbose_name = _("设备主机")
        verbose_name_plural = _("设备主机")
        unique_together = ("device", "name")
        indexes = [
            models.Index(fields=["data_center"]),
            models.Index(fields=["status"]),
            models.Index(fields=["hostname"]),
        ]

    @property
    def primary_ip(self):
        """获取主IP地址"""
        return self.ips.filter(is_primary=True).first()

    def encrypt_value(self, value: str) -> str:
        """加密值"""
        if not value:
            return value
        try:
            encrypted = signing.dumps(value, salt=settings.SECRET_KEY[:32])
            return f"$encrypted${encrypted}"
        except signing.BadSignature:
            return value

    def decrypt_value(self, value: str) -> str:
        """解密值"""
        if not value or not value.startswith("$encrypted$"):
            return value
        try:
            encrypted = value[11:]
            return signing.loads(encrypted, salt=settings.SECRET_KEY[:32])
        except signing.BadSignature:
            return value

    def password(self) -> str:
        """获取密码"""
        real_password = self.decrypt_value(self._password)
        if not real_password:
            return "******"
        # 显示前2位和后2位，中间用星号替代
        hide = "*" * (len(real_password) - 4)  # 中间的星号数量 = 总长度 - 前2位 - 后2位
        return f"{real_password[:2]}{hide}{real_password[-2:]}"

    password.short_description = _("密码")

    def save(self, *args, **kwargs):
        """保存时加密敏感信息"""
        if self._password and not self._password.startswith("$encrypted$"):
            self._password = self.encrypt_value(self._password)

        if self.ssh_key and not self.ssh_key.startswith("$encrypted$"):
            self.ssh_key = self.encrypt_value(self.ssh_key)

        super().save(*args, **kwargs)

    def get_password(self) -> str:
        """获取解密后的密码"""
        # 直接解密 _password 字段，而不是 password 属性（password属性返回的是掩码后的值）
        return self.decrypt_value(self._password)

    def get_ssh_key(self) -> str:
        """获取解密后的SSH密钥"""
        return self.decrypt_value(self.ssh_key)

    def get_connection_params(self) -> dict:
        """获取连接参数"""
        # 获取IP地址字符串
        primary_ip = self.primary_ip
        if primary_ip and primary_ip.address:
            # address 是 IPv4Interface 或 IPv6Interface 对象
            hostname = str(primary_ip.address.ip)
        else:
            first_ip = self.ips.first()
            if first_ip and first_ip.address:
                hostname = str(first_ip.address.ip)
            else:
                hostname = None

        params = {
            "hostname": hostname,
            "port": self.ssh_port,
            "username": self.username,
        }

        if self.auth_type == DeviceHostAuthTypeChoices.PASSWORD:
            params["password"] = self.get_password()
        else:
            # SSH密钥需要写入临时文件，因为大多数SSH库期望文件路径而不是内容
            # 注意：这里返回密钥内容，调用者需要负责创建临时文件
            # 或者可以在这里创建临时文件并返回路径
            ssh_key = self.get_ssh_key()
            if ssh_key:
                import os
                import tempfile

                # 创建临时文件
                with tempfile.NamedTemporaryFile(
                    mode="w", delete=False, suffix=".key"
                ) as f:
                    f.write(ssh_key)
                    temp_key_file = f.name
                # 设置适当的权限
                os.chmod(temp_key_file, 0o600)
                params["key_filename"] = temp_key_file
            else:
                params["key_filename"] = None

        return params
