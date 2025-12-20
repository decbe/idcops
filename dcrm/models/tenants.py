from django.db import models
from django.utils.translation import gettext_lazy as _

from .base import BaseModel, CustomFieldsMixin
from .choices import TenantTypeChoices
from .fields import CounterCacheField
from .mixins import IconMixin
from .tracking import TrackingModelMixin
from .utils import tag_limit_filter

__all__ = ("Tenant",)


class Tenant(BaseModel, IconMixin, CustomFieldsMixin, TrackingModelMixin):
    """
    租户代表由 idcops 所有者服务的数据中心。通常是客户或内部部门。
    """

    data_center = models.ForeignKey(
        to="dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("租户所属的数据中心"),
    )
    type = models.CharField(
        max_length=100,
        choices=TenantTypeChoices.choices,
        default=TenantTypeChoices.EXTERNAL,
        verbose_name=_("类型"),
        help_text=_("例如：网络部、机房部门属于内部，运营商属于第三方"),
    )
    name = models.CharField(
        max_length=100,
        verbose_name=_("名称"),
        help_text=_("租户公司名称，如：阿里巴巴、腾讯、百度等"),
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("描述"),
        help_text=_("对租户公司的详细描述"),
    )
    contacts = models.ManyToManyField(
        to="dcrm.Contact",
        blank=True,
        verbose_name=_("联系人"),
        help_text=_("租户公司的联系人"),
    )
    address = models.CharField(
        verbose_name=_("地址"), max_length=200, blank=True, null=True
    )
    website = models.URLField(
        blank=True,
        null=True,
        verbose_name=_("网站"),
        help_text=_("租户公司的网站，获取图标和方便用户访问"),
    )
    # shared = models.BooleanField(
    #     default=False,
    #     blank=True,
    #     editable=False,
    #     verbose_name=_("共享"),
    #     help_text=_("共享这个租户给其他数据中心引用，方便统计和分析")
    # )
    is_active = models.BooleanField(
        _("是否激活"),
        default=True,
        blank=True,
        help_text=_("指定此租户是否应被视为活跃状态。"),
    )
    latitude = models.DecimalField(
        verbose_name=_("纬度"),
        max_digits=8,
        decimal_places=6,
        editable=False,
        blank=True,
        null=True,
        help_text=_("GPS坐标，十进制格式(xx.yyyyyy)"),
    )
    longitude = models.DecimalField(
        verbose_name=_("经度"),
        max_digits=9,
        decimal_places=6,
        editable=False,
        blank=True,
        null=True,
        help_text=_("GPS坐标，十进制格式(xx.yyyyyy)"),
    )
    tags = models.ManyToManyField(
        to="dcrm.Tag",
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "tenant"),
        verbose_name=_("标签"),
        help_text=_("租户的标签"),
    )
    rack_count = CounterCacheField(
        to_model="dcrm.Rack",
        to_field="tenant",
        verbose_name=_("机柜(个)"),
    )
    device_count = CounterCacheField(
        to_model="dcrm.Device",
        to_field="tenant",
        verbose_name=_("设备(台)"),
        help_text=_("含历史已下架设备"),
    )
    node_patch_count = CounterCacheField(
        to_model="dcrm.PatchCordNode",
        to_field="tenant",
        verbose_name=_("跳线节点(个)"),
    )
    subnet_count = CounterCacheField(
        to_model="dcrm.Subnet",
        to_field="tenant",
        verbose_name=_("子网(个)"),
    )
    ipaddr_count = CounterCacheField(
        to_model="dcrm.IPAddress",
        to_field="tenant",
        verbose_name=_("IP总数"),
    )
    vlan_count = CounterCacheField(
        to_model="dcrm.VLAN",
        to_field="tenant",
        verbose_name=_("VLAN总数"),
    )
    item_instance_count = CounterCacheField(
        to_model="dcrm.ItemInstance",
        to_field="tenant",
        verbose_name=_("库存(条)"),
        help_text=_("含历史库存的物品总数"),
    )

    _icon = "fa fa-users"
    display_link_field = "name"

    def __str__(self) -> str:
        return self.name

    class Meta:
        verbose_name = _("租户")
        verbose_name_plural = _("租户管理")
        unique_together = ("data_center", "name")
        ordering = ["-updated_at"]
