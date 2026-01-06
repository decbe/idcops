import logging
import re
import time
from ipaddress import (
    IPv4Address,
    IPv4Interface,
    IPv4Network,
    IPv6Address,
    IPv6Network,
    ip_address,
    ip_interface,
    ip_network,
)
from urllib.parse import urlparse

import requests
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from mptt.models import MPTTModel, TreeForeignKey

from .base import BaseModel, CustomFieldsMixin
from .choices import (
    ColorChoices,
    IPAddressStatusChoices,
    IPAddressTypeChoices,
    ProxyTypeChoices,
    SNMPAuthProtocolChoices,
    SNMPPrivacyProtocolChoices,
    SNMPVersionChoices,
    SubnetStatusChoices,
)
from .fields import InterfaceIPAddressField
from .mixins import ColorMixin
from .tracking import TrackingModelMixin
from .utils import get_network_info, tag_limit_filter

logger = logging.getLogger(__name__)


__all__ = [
    "Subnet",
    "VLAN",
    "IPAddress",
    "NetworkProduct",
    "SNMP",
    "Proxy",
]


class NetworkValidationMixin:
    def validate_tenant_consistency(self):
        """验证租户一致性"""
        if self.subnet and self.subnet.tenant and self.tenant != self.subnet.tenant:
            raise ValidationError(_("必须分配给子网所属的租户"))

    def validate_datacenter_consistency(self):
        """验证数据中心一致性"""
        pass
        # if self.subnet and self.subnet.data_center_id != self.data_center_id:
        #     raise ValidationError(_("必须属于同一数据中心"))


class NetworkInheritanceMixin:
    def inherit_network_attributes(self):
        """继承网络属性"""
        if hasattr(self, "subnet") and self.subnet:
            if not self.data_center_id:
                self.data_center_id = self.subnet.data_center_id
            if not self.tenant and self.subnet.tenant:
                self.tenant = self.subnet.tenant


class NetworkStatisticsMixin:
    def get_ip_count(self):
        """获取IP地址数量"""
        return self.ip_addresses.count()

    def get_subnet_count(self):
        """获取子网数量"""
        return self.subnets.count()

    def get_utilization_stats(self):
        """获取利用率统计"""
        total_ips = self.total_ips
        used_ips = self.used_ips
        return {
            "total": total_ips,
            "used": used_ips,
            "available": total_ips - used_ips,
            "utilization_rate": (
                round((used_ips / total_ips * 100), 2) if total_ips else 0
            ),
        }


class AddressValidationMixin:
    def validate_ip_address(self, address):
        """验证IP地址"""
        try:
            return ip_interface(str(address))
        except ValueError as e:
            raise ValidationError(str(e))

    def is_address_in_range(self, address):
        """检查地址是否在范围内"""
        if not hasattr(self, "start_address") or not hasattr(self, "end_address"):
            return False

        address = ip_interface(str(address))
        return (
            self.start_address.ip <= address.ip <= self.end_address.ip
            and address.network == self.network.network
        )


class NetworkProduct(BaseModel, ColorMixin, CustomFieldsMixin):
    """网络产品类型"""

    data_center = models.ForeignKey(
        to="dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("所属数据中心，网络产品类型必须属于同一个数据中心"),
    )
    name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name=_("产品名称"),
        help_text=_("产品名称，如：BGP多线、电信单线等"),
    )
    code = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        verbose_name=_("产品代码"),
        help_text=_("产品代码，如：bgp、ct等"),
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("描述"),
        help_text=_("产品说明，如：线路特点、SLA等"),
    )
    shared = models.BooleanField(
        default=True,
        blank=True,
        verbose_name=_("是否共享"),
        help_text=_("是否共享给其他数据中心引用"),
    )
    tags = models.ManyToManyField(
        "dcrm.Tag",
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "networkproduct"),
        verbose_name=_("标签"),
        help_text=_("标签，用于分类和管理网络产品类型"),
    )
    _icon = "fa fa-wifi"
    display_link_field = "name"

    class Meta:
        verbose_name = _("网络产品")
        verbose_name_plural = _("网络产品")
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name


class Subnet(
    MPTTModel, BaseModel, CustomFieldsMixin, NetworkStatisticsMixin, TrackingModelMixin
):
    """子网模型 - 使用MPTT管理网络层级关系

    功能：
    1. 自动组织网络层级关系
    2. 支持网络合并和分割
    3. 支持IPv4和IPv6
    4. 提供网络使用统计
    """

    data_center = models.ForeignKey(
        to="dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("所属数据中心"),
    )
    tenant = models.ForeignKey(
        to="dcrm.Tenant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="subnets",
        verbose_name=_("租户"),
        help_text=_("分配租户"),
    )
    vlan = models.ForeignKey(
        to="dcrm.VLAN",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="subnets",
        verbose_name=_("VLAN"),
        help_text=_("所属VLAN"),
    )
    network_product = models.ForeignKey(
        to="dcrm.NetworkProduct",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("网络产品"),
        help_text=_("所属网络产品"),
    )
    vrf = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_("VRF"),
        help_text=_("所属VRF"),
    )
    name = models.CharField(
        max_length=100, verbose_name=_("子网名称"), help_text=_("子网名称")
    )
    network = InterfaceIPAddressField(
        verbose_name=_("网络地址"),
        help_text=_("网络地址，格式：192.168.1.0/24 或 2001:db8::/64"),
    )
    start_address = InterfaceIPAddressField(
        verbose_name=_("起始地址"),
        help_text=_("子网可用地址范围的起始地址"),
        null=True,
        blank=True,
    )
    end_address = InterfaceIPAddressField(
        verbose_name=_("结束地址"),
        help_text=_("子网可用地址范围的结束地址"),
        null=True,
        blank=True,
    )
    description = models.TextField(blank=True, null=True, verbose_name=_("描述"))
    parent = TreeForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("父级子网"),
        help_text=_("父级子网"),
    )
    is_scan = models.BooleanField(
        default=False,
        verbose_name=_("是否扫描"),
        help_text=_("是否扫描这个网络"),
    )
    status = models.CharField(
        max_length=120,
        choices=SubnetStatusChoices.choices,
        default=SubnetStatusChoices.EMPTY,
        verbose_name=_("状态"),
        help_text=_("子网分配状态"),
    )
    subnet_count = models.PositiveIntegerField(
        default=0,
        editable=False,
        verbose_name=_("子网数量"),
        help_text=_("已划分的子网数量"),
    )
    total_ips = models.BigIntegerField(
        default=0,
        editable=False,
        verbose_name=_("总IP数"),
        help_text=_("网段中的总IP地址数"),
    )
    allocated_ips = models.BigIntegerField(
        default=0,
        editable=False,
        verbose_name=_("已分配IP数"),
        help_text=_("已分配的IP地址数, IPv4不包括网络地址和广播地址"),
    )
    gateway = InterfaceIPAddressField(
        null=True,
        blank=True,
        verbose_name=_("网关地址"),
        help_text=_("子网的默认网关地址"),
    )
    dns_servers = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_("DNS服务器"),
        help_text=_("DNS服务器列表，例如: ['8.8.8.8', '8.8.4.4']"),
    )
    tags = models.ManyToManyField(
        to="dcrm.Tag",
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "subnet"),
        verbose_name=_("标签"),
        help_text=_("标签"),
    )

    _icon = "fa fa-sitemap"
    display_link_field = "network"
    search_fields = ["name", "network"]

    class Meta:
        verbose_name = _("子网")
        verbose_name_plural = _("子网管理")
        ordering = ["tree_id", "lft"]
        indexes = [
            # 原有索引
            models.Index(fields=["network"], name="idx_network"),
            # 新增优化索引
            models.Index(fields=["data_center", "tenant"]),
            models.Index(fields=["data_center", "status"]),
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["vlan", "network"]),
            models.Index(fields=["parent", "network"]),
            # 网络统计优化 - 移除不存在的字段
            # models.Index(fields=["total_ips", "used_ips"], name="idx_subnet_ip_stats"),
            # 部分索引 - 仅为已分配子网
            models.Index(
                fields=["tenant", "updated_at"],
                condition=models.Q(status="allocated"),
                name="subnet_allocated_only",
            ),
        ]

    class MPTTMeta:
        order_insertion_by = ["network"]

    def __str__(self):
        return f"{self.name}"

    def clean(self):
        """验证子网配置"""
        if not self.network:
            return

        try:
            network = ip_network(str(self.network))

            # 1. 验证网络重叠
            # self._validate_network_overlap()

            # 2. 验证公网/私网IP唯一性
            self._validate_network_uniqueness(network)

            # 3. 验证VLAN规则
            self._validate_vlan_rules()

            # 4. 验证父子网络关系
            self._validate_parent_child_relationship(network)

            # 5. 验证DNS服务器
            self.validate_dns_servers()

            # 6. 验证子网IP数量是否超出存储范围
            self._validate_network_ips_count(network)

            # 7. 验证子网分配情况，分配状态时必须填写租户信息
            self._validate_network_allocation()

        except ValueError as e:
            raise ValidationError(str(e))

    def _validate_network_allocation(self):
        pass

    def _validate_network_ips_count(self, network):
        # MAX_BIGINT = 9223372036854775807
        if network.num_addresses > 9223372036854775807:
            raise ValidationError(
                _("网络 %(network)s IP数量过大"), params={"network": network}
            )

    def _validate_network_overlap(self):
        """验证网络重叠"""
        # 构建查询条件
        query = Q(data_center_id=self.data_center_id)
        if self.tenant:
            query &= Q(tenant=self.tenant)

        # 排除自身
        if self.pk:
            query &= ~Q(pk=self.pk)

        # 检查重叠
        for existing in Subnet.objects.filter(query):
            existing_network = ip_network(str(existing.network))
            current_network = ip_network(str(self.network))
            if current_network.overlaps(existing_network):
                raise ValidationError(
                    _("网络 %(network)s 与现有网络 %(existing)s 重叠"),
                    params={"network": self.network, "existing": existing.network},
                )

    def _validate_network_uniqueness(self, network):
        """验证网络唯一性"""
        # 构建基本查询
        query = Q(data_center_id=self.data_center_id)
        if self.pk:
            query &= ~Q(pk=self.pk)

        if network.is_global:  # 公网IP
            # 公网IP在数据中心内唯一
            if Subnet.objects.filter(query, network=self.network).exists():
                raise ValidationError(_("此数据中心已存在相同的公网网段"))
        else:  # 私网IP
            if self.tenant:
                # 私网IP在租户内唯一
                query &= Q(tenant=self.tenant)
                if Subnet.objects.filter(query, network=self.network).exists():
                    raise ValidationError(_("此租户已存在相同的私网网段"))
            else:
                # 未分配租户的私网IP在数据中心内唯一
                query &= Q(tenant__isnull=True)
                if Subnet.objects.filter(query, network=self.network).exists():
                    raise ValidationError(_("此数据中心已存在相同的未分配私网网段"))

    def _validate_vlan_rules(self):
        """验证VLAN规则"""
        if self.vlan:
            # 验证VLAN是否属于同一数据中心
            if self.vlan.data_center_id != self.data_center_id:
                raise ValidationError(_("VLAN必须属于同一数据中心"))

            # 验证VLAN状态
            if not self.vlan.is_available:
                raise ValidationError(_("所选VLAN不可用"))

            # 验证租户权限
            if self.tenant and self.vlan.tenant and self.vlan.tenant != self.tenant:
                raise ValidationError(_("所选VLAN不属于此租户"))

            # 验证VLAN中的网段重叠
            for subnet in self.vlan.subnets.exclude(pk=self.pk):
                if ip_network(str(subnet.network)).overlaps(
                    ip_network(str(self.network))
                ):
                    raise ValidationError(
                        _("网络与VLAN %(vlan)s中的网络%(network)s重叠"),
                        params={"vlan": self.vlan, "network": subnet.network},
                    )

    def _validate_parent_child_relationship(self, network):
        """验证父子网络关系"""
        if self.parent:
            parent_network = ip_network(str(self.parent.network))

            # 验证网络类型匹配(IPv4/IPv6)
            if type(network) != type(parent_network):
                raise ValidationError(_("父子网络必须是相同的IP版本"))

            # 验证是否是父网络的子网
            if not network.subnet_of(parent_network):
                raise ValidationError(_("必须是父网络的子网"))

            # 验证数据中心一致性
            if self.parent.data_center_id != self.data_center_id:
                raise ValidationError(_("父子网络必须属于同一数据中心"))

            # 验证租户一致性
            if self.parent.tenant and self.parent.tenant != self.tenant:
                raise ValidationError(_("子网必须属于相同租户"))

    def save(self, *args, **kwargs):
        """保存前处理网络层级和掩码转换，并计算相关统计数据"""
        if self.network:
            # 转换网络地址为接口格式
            self.network = ip_interface(str(self.network))
            network = ip_network(str(self.network))

            # 计算总IP数
            self.total_ips = network.num_addresses

            # 设置起始和结束地址
            if isinstance(network, IPv4Network):
                self.start_address = ip_interface(
                    f"{network.network_address + 1}/{network.prefixlen}"
                )
                self.end_address = ip_interface(
                    f"{network.broadcast_address - 1}/{network.prefixlen}"
                )
                # IPv4需要减去网络地址和广播地址
                self.total_ips -= 2
            else:
                self.start_address = ip_interface(
                    f"{network.network_address + 1}/{network.prefixlen}"
                )
                self.end_address = ip_interface(
                    f"{network.network_address + network.num_addresses - 1}/{network.prefixlen}"
                )

            # 验证网关地址是否在子网范围内
            # if self.gateway:
            #     if not self.is_address_in_range(self.gateway):
            #         raise ValidationError(_("网关地址必须在子网范围内"))

            # 自动关联最佳父网络
            self.parent = self.find_parent_network()

        # is_new = self.pk is None  # 判断是否是新建子网
        super().save(*args, **kwargs)

        # 仅在新建子网时创建IP地址
        if not self.allocated_ips and self.tenant:
            self.create_available_ips()
            from dcrm.signals.counters import update_counts

            from .tenants import Tenant

            update_counts(Tenant, "ipaddr_count", "ip_addresses")

        # 更新父网络的子网统计
        if self.parent:
            self.parent.update_subnet_stats()

    def update_subnet_stats(self):
        """更新子网统计信息"""
        # 计算直接子网数量
        self.subnet_count = self.get_children().count()

        # 计算已分配的IP数量
        self.allocated_ips = self.ip_addresses.count()

        # 保存更新，但不触发递归
        super().save()

        # 递归更新父网络的统计信息
        if self.parent:
            self.parent.update_subnet_stats()

    def get_available_subnets(self, prefix_length):
        """获取指定前缀长度的可用子网

        Args:
            prefix_length: 子网前缀长度

        Returns:
            可用子网列表

        """
        network = ip_network(str(self.network))
        if prefix_length <= network.prefixlen:
            return []

        # 获取所有可能的子网
        potential_subnets = list(network.subnets(new_prefix=prefix_length))

        # 获取已使用的子网
        used_subnets = set()
        for child in self.get_children():
            child_network = ip_network(str(child.network))
            for subnet in potential_subnets:
                if subnet.overlaps(child_network):
                    used_subnets.add(subnet)

        # 返回未使用的子网
        return [subnet for subnet in potential_subnets if subnet not in used_subnets]

    def find_parent_network(self):
        """查找最佳的父网络

        实现逻辑：
        1. 获取当前网络的前缀长度
        2. 查找所有可能的父网络
        3. 选择前缀长度最大的包含当前网络的网络作为父网络

        Returns:
            Subnet: 最佳父网络对象，如果没有找到则返回None

        """
        if not self.network:
            return None

        current_network = ip_network(str(self.network))

        # 查找所有可能的父网络（排除自身）
        potential_parents = Subnet.objects.exclude(pk=self.pk).filter(
            data_center_id=self.data_center_id
        )

        best_parent = None
        smallest_prefix = -1

        # 遍历所有可能的父网络
        for potential_parent in potential_parents:
            try:
                parent_network = ip_network(str(potential_parent.network))
                if parent_network.version != current_network.version:
                    continue
                # 检查是否是有效的父网络：
                # 1. 当前网络必须是父网络的子网
                # 2. 父网络的前缀长度必须小于当前网络
                # 3. 父网络的前缀长度必须大于之前找到的最佳父网络
                if (
                    current_network.subnet_of(parent_network)
                    and parent_network.prefixlen < current_network.prefixlen
                    and parent_network.prefixlen > smallest_prefix
                ):

                    # 验证网络类型匹配(IPv4/IPv6)
                    if type(current_network) == type(parent_network):
                        best_parent = potential_parent
                        smallest_prefix = parent_network.prefixlen

            except ValueError:
                continue

        return best_parent

    @classmethod
    def auto_organize_networks(cls):
        """自动组织网络层级关系
        重新计算所有网络的父子关系
        """
        with transaction.atomic():
            # 临时解除所有父子关系
            cls.objects.all().update(parent=None)

            # 获取所有网络并转换为列表
            networks = list(cls.objects.all())

            # 按前缀长度排序（从小到大，即网络范围从大到小）
            networks.sort(key=lambda x: ip_network(str(x.network)).prefixlen)

            # 为每个网络寻找最佳父网络
            for network in networks:
                best_parent = network.find_parent_network()
                if best_parent:
                    network.parent = best_parent
                    network.save()

    def suggest_subnets(self, num_subnets):
        """建议子网划分方案

        Args:
            num_subnets: 需要的子网数量

        Returns:
            建议的子网列表

        """
        network = ip_network(str(self.network))

        # 计算需要的前缀长度
        current_prefix = network.prefixlen
        new_prefix = current_prefix

        while new_prefix <= (128 if network.version == 6 else 32):
            if 2 ** (new_prefix - current_prefix) >= num_subnets:
                break
            new_prefix += 1

        if new_prefix > (128 if network.version == 6 else 32):
            raise ValueError(_("无法划分出足够的子网"))

        return list(network.subnets(new_prefix=new_prefix))[:num_subnets]

    @property
    def network_info(self):
        """获取网络详细信息"""
        return get_network_info(str(self.network))

    @property
    def is_leaf_network(self):
        """判断是否是叶子网络"""
        return self.is_leaf_node()

    @property
    def used_ips(self):
        """获取已使用的IP数量

        计算规则：
        1. 直接关联到此子网的IP地址数量
        2. 包含所有子网的已分配IP总和
        3. IPv4网络需要排除网络地址和广播地址
        4. 考虑网关地址的使用

        Returns:
            int: 已使用的IP地址数量

        """
        # 基础使用量：当前子网直接分配的IP地址数
        base_usage = self.ip_addresses.count()

        # 子网使用量：所有子网的已分配IP总和
        subnet_usage = sum(child.used_ips for child in self.get_children())

        # 特殊地址使用量
        special_addresses = 0
        network = ip_network(str(self.network))

        # IPv4 网络需要考虑网络地址和广播地址
        if isinstance(network, IPv4Network):
            special_addresses += 2  # 网络地址和广播地址

        # 如果配置了网关地址，且网关不在已分配的IP中
        if self.gateway:
            gateway_ip = ip_interface(str(self.gateway))
            if not self.ip_addresses.filter(address=str(gateway_ip)).exists():
                special_addresses += 1

        return base_usage + subnet_usage + special_addresses

    @property
    def available_ips(self):
        """获取可用IP数量

        Returns:
            int: 可用的IP地址数量

        """
        return self.total_ips - self.used_ips

    @property
    def utilization_rate(self):
        """获取IP地址利用率

        Returns:
            float: IP地址利用率百分比

        """
        if self.total_ips == 0:
            return 0
        return round((self.used_ips / self.total_ips) * 100, 2)

    @property
    def subnet_utilization(self):
        """获取子网利用情况

        Returns:
            dict: 包含利用率详细信息的字典

        """
        used = self.used_ips
        return {
            "total": self.total_ips,
            "used": used,
            "available": self.total_ips - used,
            "utilization_rate": (
                round((used / self.total_ips * 100), 2) if self.total_ips else 0
            ),
            "subnet_count": self.subnet_count,
        }

    def get_all_child_subnets(self):
        """获取所有子网（包括递归子网）"""
        return self.get_descendants()

    def get_total_child_subnets(self):
        """获取所有子网数量（包括递归子网）"""
        return self.get_descendants().count()

    def get_direct_child_subnets(self):
        """获取直接子网"""
        return self.get_children()

    def get_subnet_tree(self):
        """获取子网树结构"""
        return {
            "id": self.pk,
            "name": self.name,
            "network": str(self.network),
            "total_ips": self.total_ips,
            "allocated_ips": self.allocated_ips,
            "subnet_count": self.subnet_count,
            "utilization_rate": self.utilization_rate,
            "children": [child.get_subnet_tree() for child in self.get_children()],
        }

    @classmethod
    def rebuild_subnet_stats(cls):
        """重建所有子网统计信息"""
        with transaction.atomic():
            # 从叶子节点开始更新
            leaf_nodes = cls.objects.filter(children__isnull=True)
            processed = set()

            for leaf in leaf_nodes:
                current = leaf
                while current and current.pk not in processed:
                    current.update_subnet_stats()
                    processed.add(current.pk)
                    current = current.parent

    def get_first_available_ip(self):
        """获取第一个可用的IP地址

        算法：
        1. 获取可用地址范围
        2. 获取已使用的IP列表
        3. 从起始地址开始遍历，找到第一个未使用的地址
        4. 考虑网关地址和特殊地址

        Returns:
            str|None: 第一个可用的IP地址，如果没有可用IP则返回None

        """
        if not self.network:
            return None

        try:
            network = ip_network(str(self.network))

            # 获取起始和结束地址
            if isinstance(network, IPv4Network):
                start_ip = network.network_address + 1  # 跳过网络地址
                end_ip = network.broadcast_address - 1  # 跳过广播地址
            else:
                start_ip = network.network_address + 1  # IPv6跳过网络地址
                end_ip = network.broadcast_address

            # 获取已使用的IP地址集合
            used_ips = set(
                ip_interface(str(ip.address)).ip for ip in self.ip_addresses.all()
            )

            # 添加网关地址到已使用集合
            if self.gateway:
                used_ips.add(ip_interface(str(self.gateway)).ip)

            # 获取所有子网的网络地址，避免分配到子网的网络地址
            child_networks = set()
            for child in self.get_descendants():
                child_net = ip_network(str(child.network))
                child_networks.add(child_net.network_address)
                if isinstance(child_net, IPv4Network):
                    child_networks.add(child_net.broadcast_address)

            # 遍历可用范围，找到第一个未使用的IP
            current_ip = start_ip
            while current_ip <= end_ip:
                if current_ip not in used_ips and current_ip not in child_networks:
                    # 检查此IP是否落在任何子网范围内
                    ip_in_child_subnet = False
                    for child in self.get_children():
                        child_net = ip_network(str(child.network))
                        if current_ip in child_net:
                            ip_in_child_subnet = True
                            break

                    if not ip_in_child_subnet:
                        # 找到可用IP，返回CIDR格式
                        return f"{current_ip}/{network.prefixlen}"

                current_ip += 1

            return None  # 没有可用IP

        except ValueError as e:
            logger.warn(f"网络{self.network}格式错误: {e}")
            return None

    @property
    def next_available_ip(self):
        """获取下一个可用IP地址的属性方法

        Returns:
            str|None: 下一个可用的IP地址

        """
        ip = self.get_first_available_ip()
        if ip:
            return ip_interface(ip)
        return None

    def get_available_ips(self, limit=None):
        """获取可用IP地址列表

        Args:
            limit: 限制返回的IP地址数量

        Returns:
            list: 可用IP地址列表

        """
        available_ips = []
        network = ip_network(str(self.network))

        # 获取已使用的IP集合
        used_ips = set(
            ip_interface(str(ip.address)).ip for ip in self.ip_addresses.all()
        )

        # 添加网关地址
        # if self.gateway:
        # used_ips.add(ip_interface(str(self.gateway)).ip)

        # 获取子网网络地址集合
        child_networks = set()
        for child in self.get_descendants():
            child_net = ip_network(str(child.network))
            child_networks.add(child_net.network_address)
            if isinstance(child_net, IPv4Network):
                child_networks.add(child_net.broadcast_address)

        # 设置起始和结束地址
        if isinstance(network, IPv4Network):
            start_ip = network.network_address + 1
            end_ip = network.broadcast_address - 1
        else:
            start_ip = network.network_address + 1
            end_ip = network.broadcast_address

        current_ip = start_ip
        while current_ip <= end_ip:
            if current_ip not in used_ips and current_ip not in child_networks:
                # 检查是否在子网范围内
                ip_in_child_subnet = False
                for child in self.get_children():
                    child_net = ip_network(str(child.network))
                    if current_ip in child_net:
                        ip_in_child_subnet = True
                        break

                if not ip_in_child_subnet:
                    available_ips.append(f"{current_ip}/{network.prefixlen}")
                    if limit and len(available_ips) >= limit:
                        break

            current_ip += 1

        return available_ips

    @property
    def address_range(self):
        """获取地址范围的字符串表示"""
        if self.start_address and self.end_address:
            return f"{self.start_address.ip} - {self.end_address.ip}"
        return ""

    @property
    def usable_addresses(self):
        """获取可用地址数量"""
        if not self.network:
            return 0

        network = ip_network(str(self.network))
        if isinstance(network, IPv4Network):
            # IPv4: 减去网络地址和广播地址
            return network.num_addresses - 2
        else:
            # IPv6: 所有地址都可用
            return network.num_addresses

    def get_available_ip_range(self):
        """获取可用IP地址范围"""
        if not self.network:
            return None, None

        network = ip_network(str(self.network))
        if isinstance(network, IPv4Network):
            first_usable = network.network_address + 1
            last_usable = network.broadcast_address - 1
        else:
            first_usable = network.network_address + 1
            last_usable = network.network_address + network.num_addresses - 1

        return (
            ip_interface(f"{first_usable}/{network.prefixlen}"),
            ip_interface(f"{last_usable}/{network.prefixlen}"),
        )

    def is_address_in_range(self, address):
        """检查IP地址是否在子网范围内

        Args:
            address: IP地址字符串或IP接口对象

        Returns:
            bool: 是否在范围内

        """
        if not self.start_address or not self.end_address:
            return False

        if isinstance(address, str):
            address = ip_interface(address)

        return (
            self.start_address.ip <= address.ip <= self.end_address.ip
            and address.network == self.network.network
        )

    def get_network_type(self):
        """获取网络类型

        Returns:
            str: 'IPv4' 或 'IPv6'

        """
        network = ip_network(str(self.network))
        return "IPv6" if isinstance(network, IPv6Network) else "IPv4"

    def get_ip_version(self):
        """获取IP版本号

        Returns:
            int: 4 或 6

        """
        return 6 if self.get_network_type() == "IPv6" else 4

    def get_vlan_subnets(self):
        """获取同一VLAN下的其他子网

        Returns:
            QuerySet: 子网查询集

        """
        if not self.vlan:
            return Subnet.objects.none()
        return self.vlan.subnets.exclude(pk=self.pk)

    def get_tenant_subnets(self):
        """获取同一租户的其他子网

        Returns:
            QuerySet: 子网查询集

        """
        if not self.tenant:
            return Subnet.objects.none()
        return self.tenant.subnets.exclude(pk=self.pk)

    @property
    def network_display(self):
        """获取网络显示格式

        Returns:
            str: 格式化的网络地址显示

        """
        if not self.network:
            return ""
        network = ip_network(str(self.network))
        return f"{network.network_address}/{network.prefixlen}"

    def validate_dns_servers(self):
        """验证DNS服务器配置"""
        if not self.dns_servers:
            return

        try:
            for server in self.dns_servers:
                ip_address(server)
        except ValueError:
            raise ValidationError({"dns_servers": _("DNS服务器地址格式无效")})

    def create_available_ips(self):
        """为子网创建可用IP地址

        功能:
        1. 自动创建子网范围内的所有可用IP地址
        2. 跳过网络地址和广播地址(IPv4)
        3. 跳过已分配的IP地址
        4. 支持批量创建以提高性能
        """
        # 获取可用IP地址列表
        available_ips = self.get_available_ips()

        # 批量创建IP地址对象
        ip_objects = []

        for ip_cidr in available_ips:
            is_gateway = ip_cidr == str(self.gateway)
            ip_objects.append(
                IPAddress(
                    data_center_id=self.data_center_id,
                    created_by_id=self.created_by_id,
                    subnet=self,
                    tenant=self.tenant,
                    address=ip_cidr,
                    is_gateway=is_gateway,
                    is_private=ip_interface(ip_cidr).ip.is_private,
                    status=IPAddressStatusChoices.ALLOCATED,
                    ip_type=(
                        IPAddressTypeChoices.IPv4
                        if isinstance(ip_interface(ip_cidr).ip, IPv4Address)
                        else IPAddressTypeChoices.IPv6
                    ),
                )
            )

        # 使用批量创建提高性能
        if ip_objects:
            IPAddress.objects.bulk_create(ip_objects, batch_size=254)

        # 更新子网统计信息
        self.update_subnet_stats()


class IPAddress(
    BaseModel,
    CustomFieldsMixin,
    NetworkValidationMixin,
    NetworkInheritanceMixin,
    TrackingModelMixin,
):
    """IP地址模型

    功能：
    1. 管理IP地址分配
    2. 支持IPv4和IPv6
    3. 关联子网和租户
    4. 记录IP使用状态
    """

    data_center = models.ForeignKey(
        to="dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("所属数据中心"),
    )
    subnet = models.ForeignKey(
        to="dcrm.Subnet",
        on_delete=models.CASCADE,
        related_name="ip_addresses",
        verbose_name=_("子网"),
        help_text=_("所属子网"),
    )
    tenant = models.ForeignKey(
        to="dcrm.Tenant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ip_addresses",
        verbose_name=_("租户"),
        help_text=_("分配租户"),
    )
    address = InterfaceIPAddressField(
        verbose_name=_("IP地址"),
        help_text=_("IP地址，格式：192.168.1.1/24 或 2001:db8::1/64"),
    )
    ip_type = models.CharField(
        max_length=50,
        choices=IPAddressTypeChoices.choices,
        default=IPAddressTypeChoices.IPv4,
        verbose_name=_("地址类型"),
        help_text=_("IP地址类型"),
    )
    description = models.TextField(blank=True, null=True, verbose_name=_("描述"))
    is_private = models.BooleanField(
        default=None,
        blank=True,
        null=True,
        editable=False,
        verbose_name=_("私网IP"),
        help_text=_("是否为私网IP地址"),
    )
    is_primary = models.BooleanField(
        default=False, blank=True, verbose_name=_("主IP"), help_text=_("是否为主IP地址")
    )
    is_management = models.BooleanField(
        default=False,
        blank=True,
        verbose_name=_("管理IP"),
        help_text=_("是否为管理IP地址"),
    )
    is_gateway = models.BooleanField(
        default=False,
        blank=True,
        verbose_name=_("网关IP"),
        help_text=_("是否为网关IP地址"),
    )
    mac_address = models.CharField(
        max_length=17,
        blank=True,
        null=True,
        verbose_name=_("MAC地址"),
        help_text=_("MAC地址"),
    )
    tracking = models.BooleanField(
        default=False,
        blank=True,
        verbose_name=_("跟踪IP"),
        help_text=_("是否跟踪该IP地址"),
    )
    status = models.CharField(
        max_length=20,
        choices=IPAddressStatusChoices.choices,
        default=IPAddressStatusChoices.EMPTY,
        verbose_name=_("状态"),
        help_text=_("状态"),
    )
    connected_to = models.ForeignKey(
        to=ContentType,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        limit_choices_to={
            "app_label": "dcrm",
            "model__in": ["onlinedevice", "deviceport", "devicehost"],
        },
        related_name="ipaddress",
        verbose_name=_("关联类型"),
        help_text=_("连接到指定的类型"),
    )
    connected_object_id = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name=_("连接对象ID"),
        help_text=_("连接到的对象ID"),
    )
    connected_object = GenericForeignKey(
        ct_field="connected_to", fk_field="connected_object_id"
    )
    connected_object.short_description = _("连接到")
    tags = models.ManyToManyField(
        to="dcrm.Tag",
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "ipaddress"),
        verbose_name=_("标签"),
        help_text=_("标签"),
    )

    _icon = "fa fa-map-marker"
    display_link_field = "address"
    search_fields = [
        "address",
    ]

    class Meta:
        verbose_name = _("IP地址")
        verbose_name_plural = _("IP地址")
        unique_together = ["data_center", "subnet", "address"]
        ordering = ["pk"]
        indexes = [
            # 原有索引
            models.Index(
                fields=["data_center", "subnet", "address"],
                name="idx_data_center_subnet_address",
            ),
            models.Index(
                fields=["data_center", "tenant", "address"],
                name="idx_data_center_tenant_address",
            ),
            models.Index(
                fields=["data_center", "address"], name="idx_data_center_address"
            ),
            models.Index(fields=["subnet", "address"], name="idx_subnet_address"),
            models.Index(fields=["tenant", "address"], name="idx_tenant_address"),
            # 新增优化索引
            models.Index(fields=["subnet", "status"]),
            models.Index(fields=["status", "address"]),
            models.Index(fields=["mac_address"]),
            models.Index(fields=["connected_to", "connected_object_id"]),
            # 特殊IP类型优化
            models.Index(fields=["is_gateway", "subnet"]),
            models.Index(fields=["is_primary", "connected_to", "connected_object_id"]),
            # IP类型和网络类型
            models.Index(fields=["ip_type", "status"]),
            models.Index(fields=["is_private", "status"]),
            # 部分索引 - 仅为已分配IP
            models.Index(
                fields=["address", "updated_at"],
                condition=models.Q(status="allocated"),
                name="ipaddress_allocated_only",
            ),
        ]

    def __str__(self):
        return f"{self.address}"

    def tree_path_display(self):
        """获取树路径显示"""
        return self.get_ancestors(include_self=True)

    @property
    def status_color(self):
        return IPAddressStatusChoices.get_color(self.status)

    @property
    def color_to_hex(self):
        return ColorChoices.to_hex_color(self.status_color)

    def clean(self):
        """数据验证
        1. 验证IP地址格式
        2. 验证IP地址是否在子网范围内
        3. 验证MAC地址格式
        4. 验证特殊IP标记的互斥关系
        """
        super().clean()
        self.validate_tenant_consistency()
        self.validate_datacenter_consistency()

        if self.address and self.subnet:
            # 验证IP是否在子网范围内
            if not self.subnet.is_address_in_range(self.address):
                raise ValidationError({"address": _("IP地址不在子网范围内")})

            # 验证IP版本是否匹配
            ip = ip_interface(str(self.address))
            subnet_network = ip_network(str(self.subnet.network))
            if type(ip.ip) != type(subnet_network.network_address):
                raise ValidationError({"address": _("IP地址版本与子网不匹配")})

            # 3. 验证租户权限
            if self.subnet.tenant and self.tenant != self.subnet.tenant:
                raise ValidationError(_("IP地址必须分配给子网所属的租户"))

            # 4. 验证特殊地址
            if isinstance(ip, IPv4Interface):
                if ip.ip == subnet_network.network_address:
                    raise ValidationError(_("不能用网络地址"))
                if ip.ip == subnet_network.broadcast_address:
                    raise ValidationError(_("不能使用广播地址"))

        # 验证MAC地址格式
        if self.mac_address:
            mac_pattern = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")
            if not mac_pattern.match(self.mac_address):
                raise ValidationError({"mac_address": _("MAC地址格式无效")})

        # 验证特殊IP标记的互斥关系
        special_flags = [self.is_primary, self.is_management, self.is_gateway]
        if sum(bool(flag) for flag in special_flags) > 1:
            raise ValidationError(_("IP地址不能同时是主IP、管理IP和网关IP"))

    def save(self, *args, **kwargs):
        """保存前的处理
        1. 自动设置是否为私网IP
        2. 自动继承子网的数据中心和租户信息
        3. 处理网关IP的特殊情况
        """
        self.inherit_network_attributes()
        if self.address:
            # 转换为IP接口对象
            ip = ip_interface(str(self.address))

            # 设置是否为私网IP
            if isinstance(ip.ip, (IPv4Address, IPv6Address)):
                self.is_private = ip.ip.is_private

            # 如果是网关IP，自动设置is_gateway
            if self.subnet and self.subnet.gateway:
                subnet_gateway = ip_interface(str(self.subnet.gateway))
                if ip.ip == subnet_gateway.ip:
                    self.is_gateway = True

            # 自动继承子网的数据中心
            if self.subnet and not self.data_center_id:
                self.data_center_id = self.subnet.data_center_id

            # 自动继承子网的租户
            if self.subnet and self.subnet.tenant and not self.tenant:
                self.tenant = self.subnet.tenant

        super().save(*args, **kwargs)
        # 重新计算子网统计信息
        self.subnet.update_subnet_stats()

    @classmethod
    def get_available_ips_for_tenant(cls, tenant):
        """获取租户可用的IP地址"""
        if not tenant:
            return cls.objects.none()

        return cls.objects.filter(models.Q(tenant=tenant))

    def validate_mac_address(self):
        """验证MAC地址格式"""
        if not self.mac_address:
            return

        mac_pattern = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")
        if not mac_pattern.match(self.mac_address):
            raise ValidationError({"mac_address": _("MAC地址格式无效")})

    def get_ip_type(self):
        """获取IP地址类型

        Returns:
            str: 'IPv4' 或 'IPv6'

        """
        ip = ip_interface(str(self.address))
        return "IPv6" if isinstance(ip.ip, IPv6Address) else "IPv4"

    @property
    def ip_type_display(self):
        """获取IP类型显示名称
        """
        if self.is_gateway:
            return _("网关IP")
        elif self.is_primary:
            return _("主IP")
        elif self.is_management:
            return _("管理IP")
        return _("普通IP")

    @property
    def network_type(self):
        """获取网络类型（IPv4/IPv6）
        """
        if not self.address:
            return None
        ip = ip_interface(str(self.address))
        return "IPv6" if isinstance(ip.ip, IPv6Address) else "IPv4"

    @property
    def address_with_mask(self):
        """获取带掩码的地址显示
        """
        if not self.address:
            return ""
        return str(self.address)

    @property
    def address_without_mask(self):
        """获取不带掩码的地址显示
        """
        if not self.address:
            return ""
        return str(ip_interface(str(self.address)).ip)

    @property
    def address_dot_number(self):
        if not self.address:
            return "."
        if self.ip_type == "ipv4":
            return f"{self.address_without_mask.split('.')[-1]}"
        else:
            return f"{self.address_without_mask.split(':')[-1]}"

    @property
    def address_display(self):
        """获取地址显示格式

        Returns:
            str: 格式化的IP地址显示

        """
        if not self.address:
            return ""
        ip = ip_interface(str(self.address))
        return f"{ip.ip}/{ip.network.prefixlen}"


class VLAN(BaseModel, CustomFieldsMixin, NetworkStatisticsMixin, TrackingModelMixin):
    """VLAN管理模型

    功能：
    1. VLAN资源管理
    2. 支持租户分配
    3. 关联子网管理
    """

    data_center = models.ForeignKey(
        to="dcrm.DataCenter",
        on_delete=models.PROTECT,
        related_name="vlans",
        verbose_name=_("数据中心"),
        help_text=_("所属数据中心"),
    )
    tenant = models.ForeignKey(
        to="dcrm.Tenant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="vlans",
        verbose_name=_("租户"),
        help_text=_("分配租户"),
    )
    name = models.CharField(
        max_length=100, verbose_name=_("VLAN名称"), help_text=_("VLAN名称")
    )
    vlan_id = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(4094)],
        verbose_name=_("VLAN ID"),
        help_text=_("VLAN标识"),
    )
    status = models.CharField(
        max_length=20,
        choices=SubnetStatusChoices.choices,
        default=SubnetStatusChoices.EMPTY,
        verbose_name=_("状态"),
        help_text=_("VLAN状态，如：空闲(Empty)、已分配(Allocated)、已回收(Recycled)等"),
    )
    description = models.TextField(blank=True, null=True, verbose_name=_("描述"))

    # 新增字段
    tags = models.ManyToManyField(
        to="dcrm.Tag",
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "vlan"),
        verbose_name=_("标签"),
        help_text=_("标签"),
    )

    _icon = "fa fa-ellipsis-h"
    display_link_field = "name"
    search_fields = [
        "name",
    ]

    class Meta:
        verbose_name = _("VLAN")
        verbose_name_plural = _("VLAN 管理")
        unique_together = ["data_center", "vlan_id"]
        ordering = ["-updated_at"]
        indexes = [
            # 原有索引
            models.Index(
                fields=["data_center", "vlan_id"], name="idx_data_center_vlan_id"
            ),
            models.Index(fields=["tenant", "name"], name="idx_tenant_name"),
            # 新增优化索引
            models.Index(fields=["data_center", "status"], name="idx_vlan_dc_status"),
            models.Index(fields=["tenant", "status"], name="idx_vlan_tenant_status"),
            models.Index(fields=["vlan_id", "status"], name="idx_vlan_id_status"),
            # 部分索引 - 仅为可用VLAN
            models.Index(
                fields=["vlan_id"],
                condition=models.Q(status="available"),
                name="idx_vlan_available_only",
            ),
        ]

    def __str__(self):
        return f"{self.name} (VLAN {self.vlan_id})"

    def clean(self):
        """验证VLAN配置"""
        # 验证VLAN ID的唯一性
        existing_vlans = VLAN.objects.filter(
            data_center_id=self.data_center_id, vlan_id=self.vlan_id
        ).exclude(pk=self.pk)

        if existing_vlans.exists():
            raise ValidationError({"vlan_id": _("此数据中心已存在相同的VLAN ID")})
        # 验证VLAN ID范围
        if self.vlan_id < 1 or self.vlan_id > 4094:
            raise ValidationError({"vlan_id": _("VLAN ID必须在1-4094范围内")})

    @property
    def is_available(self):
        """判断VLAN是否可用"""
        return self.status in [
            SubnetStatusChoices.ALLOCATED,
            SubnetStatusChoices.RESERVED,
        ]

    @transaction.atomic
    def allocate_to_tenant(self, tenant):
        """将VLAN分配给租户"""
        if not tenant:
            raise ValidationError(_("租户是必需的"))

        if not self.is_available:
            raise ValidationError(_("此VLAN不可用于分配"))

        self.tenant = tenant
        self.status = SubnetStatusChoices.ALLOCATED
        self.save()

        # 更新关联的子网
        Subnet.objects.filter(data_center_id=self.data_center_id, vlan=self).update(
            tenant=tenant
        )

    def release_from_tenant(self):
        """从租户释放VLAN"""
        if not self.tenant:
            return

        # 释放关联的子网
        Subnet.objects.filter(data_center_id=self.data_center_id, vlan=self).update(
            tenant=None
        )

        self.tenant = None
        self.status = SubnetStatusChoices.RECYCLED
        self.save()

    @classmethod
    def get_available_vlans(cls, data_center):
        """获取数据中心可用的VLAN"""
        return cls.objects.filter(
            data_center=data_center,
            status__in=[SubnetStatusChoices.EMPTY, SubnetStatusChoices.RECYCLED],
        )

    def get_associated_subnets(self):
        """获取关联的子网"""
        return Subnet.objects.filter(data_center_id=self.data_center_id, vlan=self)

    def get_subnet_count(self):
        """获取VLAN下的子网数量

        Returns:
            int: 子网数量

        """
        return self.subnets.count()

    def get_ip_count(self):
        """获取VLAN下的IP地址数量

        Returns:
            int: IP地址数量

        """
        return sum(subnet.used_ips for subnet in self.subnets.all())

    @property
    def utilization(self):
        """获取VLAN利用率信息

        Returns:
            dict: 包含利用率信息的字典

        """
        subnets = self.subnets.all()
        total_ips = sum(subnet.total_ips for subnet in subnets)
        used_ips = sum(subnet.used_ips for subnet in subnets)

        return {
            "subnet_count": len(subnets),
            "total_ips": total_ips,
            "used_ips": used_ips,
            "available_ips": total_ips - used_ips,
            "utilization_rate": (
                round((used_ips / total_ips * 100), 2) if total_ips else 0
            ),
        }

    @classmethod
    def get_available_vlans_for_tenant(cls, tenant, data_center):
        """获取租户可用的VLAN列表

        Args:
            tenant: 租户实例
            data_center: 数据中心实例

        Returns:
            QuerySet: VLAN查询集

        """
        return cls.objects.filter(
            data_center=data_center,
            status__in=[SubnetStatusChoices.ALLOCATED, SubnetStatusChoices.RESERVED],
        ).filter(Q(tenant__isnull=True) | Q(tenant=tenant))


class SNMP(BaseModel, CustomFieldsMixin):
    """SNMP配置模型

    用于存储和管理SNMP配置信息
    """

    data_center = models.ForeignKey(
        to="dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("所属数据中心"),
    )
    assigned_to = models.ForeignKey(
        to=ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="snmp",
        verbose_name=_("分配给"),
        help_text=_("分配给"),
    )
    assigned_to_object_id = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("分配给对象ID")
    )
    assigned_to_object = GenericForeignKey("assigned_to", "assigned_to_object_id")
    snmp_version = models.CharField(
        max_length=10,
        choices=SNMPVersionChoices.choices,
        default=SNMPVersionChoices.V2C,
        verbose_name=_("版本"),
        help_text=_("SNMP版本"),
    )
    name = models.CharField(
        max_length=100, verbose_name=_("名称"), help_text=_("SNMP配置名称")
    )
    community = models.CharField(
        max_length=100,
        verbose_name=_("社区"),
        help_text=_("SNMP配置的社区字符串"),
    )
    username = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("用户名"),
        help_text=_("SNMP配置的用户名"),
    )
    auth_key = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("密码"),
        help_text=_("SNMP 认证方式密码"),
    )
    auth_protocol = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        choices=SNMPAuthProtocolChoices.choices,
        default=None,
        verbose_name=_("认证协议"),
        help_text=_("设置 SNMP 认证算法：MD5、SHA 选项，默认为 MD5"),
    )
    enc_key = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("加密密钥"),
        help_text=_("SNMP 认证方式密码"),
    )
    enc_protocol = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        choices=SNMPPrivacyProtocolChoices.choices,
        default=None,
        verbose_name=_("加密协议"),
        help_text=_("设置 SNMP 加密算法：DES、AES-128 选项，默认为 DES"),
    )
    description = models.TextField(
        blank=True, null=True, verbose_name=_("描述"), help_text=_("SNMP配置说明")
    )
    is_active = models.BooleanField(
        default=True, verbose_name=_("启用"), help_text=_("是否启用此SNMP配置")
    )
    interval = models.PositiveIntegerField(
        default=60,
        verbose_name=_("检查间隔"),
        help_text=_("SNMP配置检查间隔(秒)"),
    )
    tags = models.ManyToManyField(
        "dcrm.Tag",
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "snmp"),
        verbose_name=_("标签"),
        help_text=_("标签"),
    )
    _icon = "fa fa-server"
    display_link_field = "name"
    search_fields = ["name"]

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("SNMP配置")
        verbose_name_plural = _("SNMP配置管理")


class Proxy(BaseModel, CustomFieldsMixin):
    """代理服务器模型

    用于存储和管理代理服务器信息，支持：
    1. HTTP/HTTPS/SOCKS4/SOCKS5代理
    2. 代理可用性检查
    3. 代理认证
    4. 自动检测响应时间
    """

    data_center = models.ForeignKey(
        to="dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("所属数据中心"),
    )
    name = models.CharField(
        max_length=100, verbose_name=_("代理名称"), help_text=_("代理服务器名称")
    )
    proxy_type = models.CharField(
        max_length=10,
        choices=ProxyTypeChoices.choices,
        default=ProxyTypeChoices.HTTP,
        verbose_name=_("代理类型"),
        help_text=_("代理服务器类型"),
    )
    host = models.CharField(
        max_length=255,
        verbose_name=_("主机地址"),
        help_text=_("代理服务器地址，如：proxy.example.com 或 192.168.1.1"),
    )
    port = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(65535)],
        verbose_name=_("端口"),
        help_text=_("代理服务器端口(1-65535)"),
    )
    username = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("用户名"),
        help_text=_("代理认证用户名(可选)"),
    )
    password = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("密码"),
        help_text=_("代理认证密码(可选)"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("启用"),
        help_text=_("是否启用此代理"),
    )
    last_check = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("最后检查"),
        help_text=_("最后一次检查时间"),
    )
    response_time = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("响应时间"),
        help_text=_("最后一次检查的响应时间(秒)"),
    )
    check_url = models.URLField(
        default="https://www.qq.com",
        verbose_name=_("检查URL"),
        help_text=_("用于检查代理可用性的URL"),
    )
    check_interval = models.PositiveIntegerField(
        default=300, verbose_name=_("检查间隔"), help_text=_("代理可用性检查间隔(秒)")
    )
    max_failed_checks = models.PositiveIntegerField(
        default=3,
        verbose_name=_("最大失败次数"),
        help_text=_("连续失败多少次后禁用代理"),
    )
    failed_checks = models.PositiveIntegerField(
        default=0, verbose_name=_("失败次数"), help_text=_("连续失败次数")
    )
    description = models.TextField(
        blank=True, null=True, verbose_name=_("描述"), help_text=_("代理服务器说明")
    )
    tags = models.ManyToManyField(
        "dcrm.Tag",
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "proxy"),
        verbose_name=_("标签"),
        help_text=_("标签"),
    )

    _icon = "fa fa-globe"
    display_link_field = "name"
    search_fields = ["name", "host"]

    class Meta:
        verbose_name = _("代理服务器")
        verbose_name_plural = _("代理服务器")
        ordering = ["-updated_at"]
        unique_together = ["data_center", "host", "port"]
        indexes = [
            models.Index(
                fields=["data_center", "host", "port"], name="idx_proxy_host_port"
            ),
            models.Index(fields=["is_active"], name="idx_proxy_active"),
        ]

    def __str__(self):
        return f"{self.name} ({self.host}:{self.port})"

    def clean(self):
        """验证代理配置"""
        super().clean()

        # 验证主机地址格式
        try:
            parsed = urlparse(f"//{self.host}")
            if not parsed.hostname:
                raise ValidationError({"host": _("无效的主机地址格式")})
        except Exception:
            raise ValidationError({"host": _("无效的主机地址格式")})

        # 验证认证信息完整性
        if bool(self.username) != bool(self.password):
            raise ValidationError(_("用户名和密码必须同时设置或同时为空"))

    def check_availability(self, timeout: int = 10) -> bool:
        """检查代理可用性

        Args:
            timeout: 超时时间(秒)

        Returns:
            bool: 代理是否可用

        """
        # 检查缓存
        cache_key = f"proxy_check_availability_{self.pk}"
        # cached_result = cache.get(cache_key)
        # if cached_result is not None:
        #     return cached_result

        try:
            start_time = time.time()

            # 配置会话
            session = requests.Session()

            # 根据代理类型选择不同的检查URL
            if self.proxy_type == "socks4":
                # SOCKS4 只用 HTTP 协议和 IP 地址
                check_url = "http://1.1.1.1"  # 使用Cloudflare的IP
            else:
                check_url = self.check_url

            # 配置代理
            proxy_url = self.get_proxy_url()
            proxies = {"http": proxy_url, "https": proxy_url}
            session.proxies = proxies

            # 发送请求
            response = session.get(
                check_url,
                timeout=timeout,
                verify=False if "https" in check_url else None,  # 只在HTTPS时禁用验证
            )

            # 计算响应时间
            self.response_time = time.time() - start_time

            # 检查响应
            is_available = response.status_code in [200, 301, 302]  # 接受重定向

            # 更新状态
            if is_available:
                self.failed_checks = 0
            else:
                self.failed_checks += 1

            if self.failed_checks >= self.max_failed_checks:
                self.is_active = False

            self.last_check = timezone.now()
            self.save()

            # 缓存结果
            cache.set(cache_key, is_available, self.check_interval)

            return is_available

        except Exception as e:
            logger.error(f"代理检查失败 {self.host}:{self.port}: {str(e)}")
            self.failed_checks += 1
            if self.failed_checks >= self.max_failed_checks:
                self.is_active = False
            self.last_check = timezone.now()
            self.save()

            # 缓存失败结果
            cache.set(cache_key, False, self.check_interval)

            return False

    def can_proxy_nmap(self) -> bool:
        """是否可以代理nmap
        socks4 代理nmap时，只能扫描基于tcp的协议，不支持域名，不支持icmp检测

        Returns:
            bool: 是否可以代理nmap

        """
        return self.proxy_type in ["http", "socks4"]

    def get_proxy_url(self) -> str:
        """获取代理URL"""
        auth = (
            f"{self.username}:{self.password}@"
            if self.username and self.password
            else ""
        )

        # SOCKS4 不支持认证，强制移除认证信息
        if self.proxy_type == "socks4":
            auth = ""

        return f"{self.proxy_type}://{auth}{self.host}:{self.port}"

    @property
    def is_available(self) -> bool:
        """检查代理是否可用"""
        if not self.is_active:
            return False
        return self.check_availability()
        # 如果从未检查过或者超过检查间隔，进行新的检查
        if not self.last_check or timezone.now() - self.last_check > timezone.timedelta(
            seconds=self.check_interval
        ):
            return self.check_availability()

        return self.failed_checks < self.max_failed_checks

    @classmethod
    def get_available_proxies(cls, data_center=None):
        """获取可用的代理列表"""
        queryset = cls.objects.filter(is_active=True)
        if data_center:
            queryset = queryset.filter(data_center=data_center)
        return queryset

    def get_proxy_config(self) -> dict:
        """获取代理配置

        Returns:
            Dict: 代理配置字典

        """
        return {
            "proxy_host": self.host,
            "proxy_port": self.port,
            "proxy_type": self.proxy_type,
            "proxy_username": self.username,
            "proxy_password": self.password,
        }

    @property
    def status_display(self) -> str:
        """获取状态显示"""
        if not self.is_active:
            return _("已禁用")
        if self.is_available:
            return _("可用")
        return _("不可用")

    @property
    def response_time_display(self) -> str:
        """获取响应时间显示"""
        if self.response_time is None:
            return _("未知")
        return f"{self.response_time:.2f}s"


"""
使用示例和说明文档
=================

1. 基本使用示例
--------------

# 创建根网络
root = Subnet.objects.create(
    name="总部网络",
    network="10.0.0.0/8",
    data_center=data_center_instance
)

# 创建子网
subnet1 = Subnet.objects.create(
    name="研发部网络",
    network="10.1.0.0/16",
    parent=root,
    data_center=data_center_instance
)

# 获取网络统计信息
stats = root.subnet_utilization
print(f"总IP数: {stats['total']}")
print(f"已分配: {stats['allocated']}")
print(f"可用: {stats['available']}")
print(f"利用率: {stats['utilization_rate']}%")
print(f"子网数: {stats['subnet_count']}")

# 获取子网树
tree = root.get_subnet_tree()
print("网络树结构:", tree)

# 重建统计信息
Subnet.rebuild_subnet_stats()

2. 主要改动和新增功能
------------------

2.1 Subnet模型字段
- start_address: 子网可用地址范围的起始地址
- end_address: 子网可用地址范围的结束地址
- subnet_count: 已划分的子网数量
- total_ips: 总IP地址数
- allocated_ips: 已分配的IP地址数

2.2 自动计算和更新
- 自动计算起始和结束地址
- 自动更新子网统计信息
- 递归更新父网络统计信息

2.3 网络验证功能
- 验证网络重叠
- 验证公网/私网IP唯一性
- 验证VLAN规则
- 验证父子网络关系

2.4 地址管理功能
- 地址范围计算
- 可用地址统计
- IP地址分配追踪

2.5 子网管理功能
- 子网树结构管理
- 子网统计信息
- 自动组织网络层级

3. 高级功能示例
-------------

# 获取可用子网
available_subnets = subnet1.get_available_subnets(prefix_length=24)
print(f"可用的/24子网: {available_subnets}")

# 自动组织网络
Subnet.auto_organize_networks()

# 建议子网划分
subnets = subnet1.suggest_subnets(num_subnets=4)
print(f"建议的子网划分: {subnets}")

# 检查IP地址是否在范围内
is_in_range = subnet1.is_address_in_range("10.1.1.1")
print(f"IP是否在范围内: {is_in_range}")

4. VLAN和IP地址管理示例
--------------------

# 创建VLAN
vlan = VLAN.objects.create(
    name="开发部VLAN",
    vlan_id=100,
    data_center=data_center_instance
)

# 分配VLAN给租户
vlan.allocate_to_tenant(tenant_instance)

# 创建IP地址
ip = IPAddress.objects.create(
    subnet=subnet1,
    address="10.1.1.1/16",
    ip_type=IPAddressTypeChoices.HOST,
    data_center=data_center_instance
)

# 获取租户可用的IP地址
available_ips = IPAddress.get_available_ips_for_tenant(tenant_instance)

5. 注意事项
---------

1. 网络地址验证
   - IPv4地址不能使用/32掩码
   - IPv6地址不能使用/128掩码
   - 子网必须属于父网络范围

2. VLAN管理
   - VLAN ID在数据中心内唯一
   - VLAN状态影响子网分配
   - 租户分配需要考虑权限

3. IP地址分配
   - 自动继承子网的数据中心和租户信息
   - 避免使用特殊地址(网络地址和广播地址)
   - 确保IP地址在子网范围内

4. 性能考虑
   - 使用事务保证数据一致性
   - 量更新时使用rebuild_subnet_stats
   - 合理使用缓存减少数据库查询


'tenant', 'vlan', 'name', 'network', 'start_address', 'end_address', 'description', 'parent', 'status', 'subnet_count', 'total_ips', 'allocated_ips', 'gateway', 'dns_servers',

"""
