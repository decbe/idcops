from django.core.exceptions import ValidationError
from django.db import models
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .base import BaseModel
from .choices import (
    NodeTypeChoices,
    PatchCordCableTypeChoices,
    PatchCordStatusChoices,
    PortTypeChoices,
)
from .fields import RackPositionField
from .mixins import ColorMixin, CustomFieldsMixin
from .tracking import TrackingModelMixin
from .utils import tag_limit_filter

__all__ = (
    "PatchCordNode",
    "PatchCord",
)


class PatchCordNode(BaseModel, ColorMixin, CustomFieldsMixin, TrackingModelMixin):
    """跳线节点"""

    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("跳线的所有节点必须属于同一个数据中心"),
    )
    tenant = models.ForeignKey(
        "dcrm.Tenant",
        on_delete=models.PROTECT,
        verbose_name=_("租户"),
        help_text=_("跳线节点所属租户"),
    )
    patch_cord = models.ForeignKey(
        "PatchCord",
        on_delete=models.CASCADE,
        related_name="nodes",
        verbose_name=_("跳线"),
        help_text=_("所属的跳线"),
    )
    node_type = models.CharField(
        max_length=20,
        choices=NodeTypeChoices.choices,
        default=NodeTypeChoices.DEVICE,
        verbose_name=_("节点类型"),
        help_text=_("设备端口或配线架端口"),
    )
    device = models.ForeignKey(
        "dcrm.Device",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="patch_cord_nodes",
        verbose_name=_("设备"),
        help_text=_("连接的设备（仅设备类型节点需要）"),
    )
    rack = models.ForeignKey(
        "dcrm.Rack",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="patch_cord_nodes",
        verbose_name=_("机柜"),
        help_text=_("所在机柜（配线架类型节点需要）"),
    )
    rack_unit = RackPositionField(
        null=True,
        blank=True,
        verbose_name=_("机柜U位"),
        help_text=_("U位，配线架类型节点需要"),
    )
    port_name = models.ForeignKey(
        "dcrm.DevicePort",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="patch_cord_nodes",
        verbose_name=_("端口"),
        help_text=_("所在端口（设备端口或配线架端口）"),
    )
    port_type = models.CharField(
        max_length=50,
        choices=PortTypeChoices.choices,
        default=PortTypeChoices.RJ45,
        verbose_name=_("端口类型"),
        help_text=_("如：RJ45、SFP、SFP+、QSFP、QSFP+等"),
    )
    length = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        default=0,
        verbose_name=_("线缆长度(米)"),
        help_text=_("线缆长度，单位：米，精确到小数点后2位"),
    )
    sequence = models.PositiveIntegerField(
        verbose_name=_("顺序序号"),
        default=0,
        help_text=_("节点在跳线中的顺序，从0开始，用于确定连接的先后顺序"),
    )
    tags = models.ManyToManyField(
        "dcrm.Tag",
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "patchcordnode"),
        verbose_name=_("标签"),
        help_text=_("标签，用于分类和管理跳线节点"),
    )
    _icon = "fa fa-dot-circle-o"
    display_link_field = "port_name"
    search_fields = [
        "id",
    ]

    class Meta:
        verbose_name = _("跳线节点")
        verbose_name_plural = _("跳线节点")
        ordering = ["patch_cord", "sequence"]
        unique_together = [
            ["patch_cord", "sequence"],
            ["patch_cord", "device", "port_name"],
            ["patch_cord", "rack", "rack_unit", "port_name"],
        ]

    def __str__(self):
        tenant_name = f"[{self.tenant.name}]" if self.tenant else ""
        if self.node_type == NodeTypeChoices.DEVICE:
            return f"{tenant_name} {self.device.name}-{self.port_name}"
        else:
            return f"{tenant_name} {self.rack.name}-U{self.rack_unit}-{self.port_name}"

    @property
    def get_tenant(self):
        """获取节点关联的租户"""
        if self.node_type == NodeTypeChoices.DEVICE:
            return self.device.tenant if self.device else None
        else:
            return self.rack.tenant if self.rack else None

    def device_is_migrated(self):
        return self.device.rack != self.rack

    device_is_migrated.short_description = _("设备跨机柜迁移")

    def clean(self):
        """验证节点配置"""
        if self.node_type == NodeTypeChoices.DEVICE:
            if not self.device:
                raise ValidationError(_("设备类型节点必须指定设备"))
        else:
            if not self.rack or not self.rack_unit:
                raise ValidationError(_("配线架类型节点必须指定机柜和U位"))

        # 验证U位是否超出机柜高度
        if self.rack and self.rack_unit > self.rack.u_height:
            raise ValidationError(_("U位超出机柜高度"))


class PatchCord(BaseModel, CustomFieldsMixin):
    """网络跳线"""

    data_center = models.ForeignKey(
        to="dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("所属数据中心，跳线的所有节点必须属于同一个数据中心"),
    )
    identifier = models.CharField(
        max_length=50,
        verbose_name=_("编号"),
        help_text=_("跳线的唯一编号，用于标识和管理跳线，如：PC001、JX-A-001等"),
    )
    # 网络产品相关字段
    network_product = models.ForeignKey(
        "dcrm.NetworkProduct",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name=_("网络产品"),
        help_text=_("网络产品类型"),
    )
    bandwidth = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("带宽(Mbps)"),
        help_text=_("带宽大小(MB)，如：100表示100MB，1000表示1000MB"),
    )
    cable_label = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=_("线缆标签"),
        help_text=_("线缆标签，用于现场标识，可以是编号或其他标识信息"),
    )
    cable_type = models.CharField(
        max_length=50,
        choices=PatchCordCableTypeChoices.choices,
        blank=True,
        null=True,
        verbose_name=_("线缆类型"),
        help_text=_("例如：网线、光纤、堆叠线、网线光纤混合等"),
    )
    length = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name=_("线缆长度(米)"),
        help_text=_("线缆长度，单位：米，精确到小数点后2位"),
    )
    status = models.CharField(
        max_length=20,
        choices=PatchCordStatusChoices.choices,
        default=PatchCordStatusChoices.ACTIVE,
        verbose_name=_("状态"),
        help_text=_(
            "跳线状态，如：使用中(Active)、计划中(Planned)、已回收(Recycled)等"
        ),
    )
    node_count = models.PositiveIntegerField(
        default=0,
        editable=False,
        blank=True,
        null=True,
        verbose_name=_("节点数量"),
        help_text=_("跳线包含的节点数量"),
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("描述"),
        help_text=_("跳线的补充说明，可以记录用途、变更历史等信息"),
    )
    tags = models.ManyToManyField(
        "dcrm.Tag",
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "patchcord"),
        verbose_name=_("标签"),
        help_text=_("标签，用于分类和管理跳线"),
    )

    _icon = "fa fa-chain"
    display_link_field = "identifier"
    search_fields = [
        "identifier",
    ]

    class Meta:
        verbose_name = _("跳线")
        verbose_name_plural = _("跳线信息")
        ordering = ["-updated_at"]
        unique_together = ["data_center", "identifier"]

    @property
    def bandwidth_display(self):
        """格式化显示带宽"""
        if not self.bandwidth:
            return "未指定带宽"

        if self.bandwidth >= 1000:
            return f"{self.bandwidth/1000:.1f}Gbps"
        return f"{self.bandwidth}Mbps"

    def __str__(self):
        return f"{self.identifier} [{self.bandwidth_display}]"

    def get_start_node(self):
        """获取跳线起始节点"""
        return self.nodes.order_by("sequence").first()

    def get_end_node(self):
        """获取跳线结束节点"""
        return self.nodes.order_by("-sequence").first()

    @property
    def missing_nodes(self):
        """获取跳线缺失的节点"""
        missing = self.nodes.count() % 2 == 1 and self.nodes.count() > 0
        return missing

    def full_nodes(self):
        """是否节点完整"""
        if self.missing_nodes:
            return format_html('<span class="label label-danger">{}</span>', _("否"))
        return format_html('<span class="label label-success">{}</span>', _("是"))

    full_nodes.short_description = _("节点完整")

    def connect_to(self, other_patch_cord):
        """连接到另一条跳线"""
        pass

    def clean(self):
        """验证跳线配置"""
        # 如果是新创建的记录，跳过节点数量检查
        if not self.pk:
            return

        nodes = self.nodes.all()
        if nodes.count() < 2:
            raise ValidationError(_("跳线至少需要包含两个连接节点"))

        # 验证端口兼容性
        self._validate_port_compatibility(nodes)

    def _validate_port_compatibility(self, nodes):
        """验证端口兼容性"""
        compatible_types = {
            PortTypeChoices.RJ45: [PortTypeChoices.RJ45],
            PortTypeChoices.SFP: [PortTypeChoices.SFP, PortTypeChoices.SFP_PLUS],
            PortTypeChoices.SFP_PLUS: [PortTypeChoices.SFP, PortTypeChoices.SFP_PLUS],
            PortTypeChoices.QSFP: [PortTypeChoices.QSFP, PortTypeChoices.QSFP_PLUS],
            PortTypeChoices.QSFP_PLUS: [
                PortTypeChoices.QSFP,
                PortTypeChoices.QSFP_PLUS,
            ],
            PortTypeChoices.OTHER: [PortTypeChoices.OTHER],
        }

        # for i in range(len(nodes) - 1):
        #     if nodes[i+1].port_type not in compatible_types.get(nodes[i].port_type, []):
        #         raise ValidationError(_("相邻节点的端口类型不兼容"))

    def get_tenants(self):
        """获取跳线涉及的所有租户"""
        return set(node.tenant for node in self.nodes.all() if node.tenant)
