import json
from typing import Any

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dcrm.utilities.serialization import serialize_object

# Local application
from .choices import ChangeActionChoices
from .fields import CounterCacheField
from .mixins import (
    AbsoluteUrlMixin,
    BaseModel,
    ColorMixin,
    ConfigurableMixin,
    CustomFieldsMixin,
    IconMixin,
    NestedGroupModel,
)
from .tracking import TrackingModelMixin
from .utils import tag_limit_filter

__all__ = [
    "DataCenter",
    "DataCenterGroup",
    "LogEntry",
    "Tag",
    "Manufacturer",
    "Contact",
    "ContactRole",
    "Comment",
]


class LogEntryManager(models.Manager):
    use_in_migrations = True

    def log_action(
        self,
        user,
        action,
        object_repr,
        message="",
        created_at=None,
        changed=False,
        **kwargs,
    ) -> Any:
        if isinstance(message, list):
            message = json.dumps(message)
        prechange_data = kwargs.get("prechange_data", {})
        if changed:
            postchange_data = kwargs.get("postchange_data") or serialize_object(
                object_repr
            )
        else:
            postchange_data = kwargs.get("postchange_data", {})
        extra_data = kwargs.get("extra_data", {})
        action_type = kwargs.get("action_type", action)
        log = self.model(
            created_by=user,
            data_center=user.data_center,
            object_repr=object_repr,
            action=action,
            action_type=action_type,
            message=message,
            timestamp=str(int(timezone.now().timestamp() * 1000)),
            prechange_data=prechange_data,
            postchange_data=postchange_data,
            extra_data=extra_data,
        )
        if created_at is not None:
            log.created_at = created_at
        return log.save()


class LogEntry(AbsoluteUrlMixin, models.Model):
    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        models.PROTECT,
        verbose_name=_("数据中心"),
        related_name="%(app_label)s_%(class)s_data_center",
        help_text=_("该日志条目所属的数据中心"),
    )
    content_type = models.ForeignKey(
        ContentType,
        models.PROTECT,
        verbose_name=_("内容类型"),
        help_text=_("日志条目关联的对象类型（如设备、机柜等）"),
        related_name="%(app_label)s_%(class)s_content_type",
        limit_choices_to={"app_label": "dcrm"},
    )
    object_id = models.PositiveIntegerField(
        verbose_name=_("对象ID"),
        blank=True,
        null=True,
        help_text=_("日志条目关联对象的主键ID"),
    )
    object_repr = GenericForeignKey("content_type", "object_id")
    object_repr.short_description = _("对象")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_created",
        verbose_name=_("操作人"),
        help_text=_("该日志由谁记录"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("操作时间"),
        help_text=_("该日志的操作时间"),
    )
    timestamp = models.SlugField(
        editable=False,
        blank=True,
        null=True,
        verbose_name=_("时间戳"),
        help_text=_("时间戳代表对象在系统中的创建时间，区别于对象业务开始时间"),
    )
    action = models.CharField(
        max_length=64,
        choices=ChangeActionChoices.choices,
        default=ChangeActionChoices.CREATE,
        verbose_name=_("操作分类"),
        help_text=_("日志条目的操作分类, 例如: 创建、更新、删除等"),
    )
    action_type = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        verbose_name=_("操作类型"),
        help_text=_("日志条目的操作类型, 例如: 分配机柜，下架，迁移，等等"),
    )
    count = models.IntegerField(
        default=1,
        blank=True,
        null=True,
        editable=False,
        verbose_name=_("操作数量"),
        help_text=_("该日志的批量操作数量"),
    )
    message = models.TextField(
        blank=True, null=True, verbose_name=_("消息"), help_text=_("变更消息")
    )
    prechange_data = models.JSONField(
        blank=True,
        null=True,
        verbose_name=_("变更前数据"),
        help_text=_("对象变更前的数据"),
    )
    postchange_data = models.JSONField(
        blank=True,
        null=True,
        verbose_name=_("变更后数据"),
        help_text=_("对象变更后的数据"),
    )
    extra_data = models.JSONField(
        blank=True,
        null=True,
        verbose_name=_("附加数据"),
        help_text=_("额外信息，如IP地址、user-agent、关联对象、参与人员等"),
    )
    objects = LogEntryManager()
    _icon = "fa fa-history"
    display_link_field = "timestamp"

    def __str__(self) -> str:
        return f"{self.message} - {self.content_type}"

    class Meta:
        verbose_name = _("操作日志")
        verbose_name_plural = _("操作日志")
        ordering = ["-pk"]
        indexes = [
            # 核心查询索引
            models.Index(
                fields=["data_center", "content_type", "object_id"],
                name="idx_logentry_dc_ct_obj",
            ),
            models.Index(
                fields=["data_center", "created_at"], name="idx_logentry_dc_created"
            ),
            models.Index(
                fields=["content_type", "object_id", "created_at"],
                name="idx_logentry_obj_created",
            ),
            models.Index(
                fields=["created_by", "created_at"], name="idx_logentry_user_created"
            ),
            models.Index(
                fields=["action", "created_at"], name="idx_logentry_action_created"
            ),
            models.Index(
                fields=["data_center", "action", "created_at"],
                name="idx_logentry_dc_action_created",
            ),
            # 部分索引 - 仅为有效记录
            models.Index(
                fields=["timestamp"],
                condition=models.Q(timestamp__isnull=False),
                name="idx_logentry_timestamp_valid",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.timestamp:
            if self.created_at:
                self.timestamp = str(int(self.created_at.timestamp() * 1000))
            else:
                self.timestamp = str(int(timezone.now().timestamp() * 1000))
        super().save(*args, **kwargs)

    def get_object_logs(self) -> models.QuerySet["LogEntry"]:
        """获取对象的操作日志"""
        return LogEntry.objects.filter(
            content_type=self.content_type, object_id=self.object_id
        )


class Tag(ColorMixin, NestedGroupModel):
    """
    标签
    """

    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.CASCADE,
        verbose_name=_("数据中心"),
        help_text=_("标签所属的数据中心"),
    )
    object_types = models.ManyToManyField(
        ContentType,
        related_name="object_types",
        limit_choices_to={"app_label": "dcrm"},
        verbose_name=_("适用对象类型"),
        help_text=_("选择可以使用此标签的对象类型"),
    )
    shared = models.BooleanField(
        default=True,
        blank=True,
        verbose_name=_("是否共享"),
        help_text=_("是否共享给其他数据中心引用"),
    )

    _icon = "fa fa-tag"
    display_link_field = "name"
    search_fields = ["name"]

    def __str__(self) -> str:
        return self.name

    class Meta:
        verbose_name = _("标签")
        verbose_name_plural = _("标签")
        ordering = ["tree_id", "lft"]
        unique_together = ["data_center", "parent", "name"]

    @classmethod
    def get_tags_for_model(cls, model, data_center=None, include_shared=True):
        """
        获取适用于指定模型的标签

        Args:
            model: 模型类或模型实例
            data_center: 数据中心，如果为None则获取所有数据中心的标签
            include_shared: 是否包含共享标签

        Returns:
            QuerySet: 适用于指定模型的标签查询集
        """
        from django.contrib.contenttypes.models import ContentType

        # 获取模型的ContentType
        if hasattr(model, "_meta"):
            content_type = ContentType.objects.get_for_model(model)
        else:
            content_type = model

        # 构建查询条件
        query = models.Q(object_types=content_type)

        if data_center:
            query &= models.Q(data_center=data_center)

        if include_shared:
            query |= models.Q(shared=True)

        return cls.objects.filter(query).distinct()

    @classmethod
    def get_tags_for_content_type(
        cls, content_type, data_center=None, include_shared=True
    ):
        """
        获取适用于指定ContentType的标签

        Args:
            content_type: ContentType实例或ID
            data_center: 数据中心，如果为None则获取所有数据中心的标签
            include_shared: 是否包含共享标签

        Returns:
            QuerySet: 适用于指定ContentType的标签查询集
        """
        # 构建查询条件
        query = models.Q(object_types=content_type)

        if data_center:
            query &= models.Q(data_center=data_center)

        if include_shared:
            query |= models.Q(shared=True)

        return cls.objects.filter(query).distinct()

    @classmethod
    def get_tags_for_app_label(cls, app_label, data_center=None, include_shared=True):
        """
        获取适用于指定应用标签的标签

        Args:
            app_label: 应用标签名称
            data_center: 数据中心，如果为None则获取所有数据中心的标签
            include_shared: 是否包含共享标签

        Returns:
            QuerySet: 适用于指定应用标签的标签查询集
        """
        from django.contrib.contenttypes.models import ContentType

        # 获取指定应用的所有ContentType
        content_types = ContentType.objects.filter(app_label=app_label)

        # 构建查询条件
        query = models.Q(object_types__in=content_types)

        if data_center:
            query &= models.Q(data_center=data_center)

        if include_shared:
            query |= models.Q(shared=True)

        return cls.objects.filter(query).distinct()

    @classmethod
    def get_available_tags(cls, data_center, model=None, include_shared=True):
        """
        获取可用的标签（推荐使用此方法）

        Args:
            data_center: 数据中心
            model: 模型类或模型实例，如果为None则获取所有标签
            include_shared: 是否包含共享标签

        Returns:
            QuerySet: 可用的标签查询集
        """
        if model is None:
            # 获取所有标签
            query = models.Q(data_center=data_center)
            if include_shared:
                query |= models.Q(shared=True)
            return cls.objects.filter(query).distinct()
        else:
            # 获取适用于指定模型的标签
            return cls.get_tags_for_model(model, data_center, include_shared)


class Manufacturer(BaseModel, IconMixin, CustomFieldsMixin):
    """
    制造商
    """

    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.CASCADE,
        verbose_name=_("数据中心"),
        help_text=_("制造商所属的数据中心"),
    )
    name = models.CharField(
        max_length=128,
        verbose_name=_("名称"),
        help_text=_("制造商的名称, 例如: Dell、Huawei、ZTE、Cisco等"),
    )
    name_cn = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        verbose_name=_("中文名称"),
        help_text=_("制造商的中文名称, 例如: 戴尔、华为、中兴、思科等"),
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("描述"),
        help_text=_("制造商的描述, 例如: 华为是中国的制造商等"),
    )
    shared = models.BooleanField(
        default=True,
        blank=True,
        verbose_name=_("是否共享"),
        help_text=_("是否共享给其他数据中心引用"),
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "manufacturer"),
        verbose_name=_("标签"),
        help_text=_("制造商的标签"),
    )
    website = models.URLField(
        blank=True,
        null=True,
        verbose_name=_("网站"),
        help_text=_("制造商的网站，获取图标和方便用户访问"),
    )
    _icon = "fa fa-circle-o"
    display_link_field = "name"
    search_fields = ["name", "name_cn"]

    def __str__(self) -> str:
        if self.name_cn:
            return f"{self.name} ({self.name_cn})"
        return self.name

    class Meta:
        verbose_name = _("制造商")
        verbose_name_plural = _("制造商")

    @classmethod
    def get_manufacturers(cls, data_center_id: int = 0) -> models.QuerySet:
        query = models.Q()
        if data_center_id:
            query = models.Q(shared=True) | models.Q(data_center_id=data_center_id)
        queryset = cls.objects.filter(query).values(*["id", "name", "name_cn"])
        return queryset

    @classmethod
    def get_default_manufacturer(cls, data_center_id: int = 0):
        _defaults = {"name": "Other", "name_cn": "未知品牌"}
        defaults = getattr(settings, "MANUFACTURER_DEFAULT", _defaults)
        query = models.Q(**_defaults)
        if data_center_id:
            query &= models.Q(shared=True) | models.Q(data_center_id=data_center_id)
        instance, _ = cls.objects.filter(query).get_or_create(
            **defaults, defaults={"shared": False, "data_center_id": data_center_id}
        )
        data = {
            "id": instance.pk,
            "name": instance.name,
            "name_cn": instance.name_cn,
            "default": True,
        }
        return data


class ContactRole(BaseModel, CustomFieldsMixin):
    """联系人角色"""

    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.CASCADE,
        verbose_name=_("数据中心"),
        help_text=_("联系人角色所属的数据中心"),
    )
    name = models.CharField(
        max_length=128, verbose_name=_("名称"), help_text=_("联系人角色的名称")
    )
    description = models.TextField(
        blank=True, null=True, verbose_name=_("描述"), help_text=_("联系人角色的描述")
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "contactrole"),
        verbose_name=_("标签"),
        help_text=_("联系人角色的标签"),
    )
    contact_count = CounterCacheField(
        to_model="dcrm.Contact",
        to_field="role",
        verbose_name=_("联系人(个)"),
    )
    _icon = "fa fa-user-circle"
    display_link_field = "name"
    search_fields = [
        "name",
    ]

    def __str__(self) -> str:
        return self.name

    class Meta:
        verbose_name = _("联系人角色")
        verbose_name_plural = _("联系人角色")


class Contact(BaseModel, CustomFieldsMixin, TrackingModelMixin):
    """联系人"""

    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.CASCADE,
        verbose_name=_("数据中心"),
        help_text=_("联系人所属的数据中心"),
    )
    name = models.CharField(
        max_length=128,
        verbose_name=_("名称"),
        help_text=_("联系人的名称, 例如: 张三、李四、王五等"),
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name=_("电话"),
        help_text=_("联系人的电话"),
    )
    email = models.EmailField(
        blank=True, null=True, verbose_name=_("邮箱"), help_text=_("联系人的邮箱")
    )
    address = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=_("地址"),
        help_text=_("联系人的地址, 例如: 广州市天河区、上海市浦东新区、北京市海淀区等"),
    )
    role = models.ForeignKey(
        ContactRole,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        verbose_name=_("角色"),
        help_text=_("联系人的角色, 例如: 管理员、运维、技术支持等"),
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "contact"),
        verbose_name=_("标签"),
        help_text=_("联系人的标签, 例如: 管理员、运维、技术支持等"),
    )
    _icon = "fa fa-phone-square"
    display_link_field = "name"
    search_fields = [
        "name",
    ]

    def __str__(self) -> str:
        return f"{self.name} ({self.role})"

    class Meta:
        verbose_name = _("联系人")
        verbose_name_plural = _("联系人")


class Comment(BaseModel, CustomFieldsMixin):
    """评论"""

    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.CASCADE,
        verbose_name=_("数据中心"),
        help_text=_("评论所属的数据中心"),
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name=_("内容类型"),
        help_text=_("评论的内容类型"),
    )
    object_id = models.PositiveIntegerField(
        verbose_name=_("对象ID"), help_text=_("评论的对象ID")
    )
    object_repr = GenericForeignKey("content_type", "object_id")
    object_repr.short_description = _("评论对象")
    content = models.TextField(verbose_name=_("内容"), help_text=_("评论的内容"))
    extra_data = models.JSONField(
        blank=True,
        null=True,
        verbose_name=_("附加数据"),
        help_text=_("用于存储与评论相关的额外信息，如附件、元数据等"),
    )
    _icon = "fa fa-commenting"

    def __str__(self) -> str:
        return self.content

    class Meta:
        verbose_name = _("评论")
        verbose_name_plural = _("评论")


class DataCenterGroup(NestedGroupModel, CustomFieldsMixin, TrackingModelMixin):
    """数据中心分组"""

    name = models.CharField(
        verbose_name=_("名称"),
        max_length=100,
        unique=True,
    )
    datacenter_count = CounterCacheField(
        to_model="dcrm.datacenter",
        to_field="group",
        verbose_name=_("数据中心(个)"),
    )

    _icon = "fa fa-building"
    display_link_field = "name"
    search_fields = [
        "name",
    ]

    def __str__(self) -> str:
        return self.name

    def get_data_center_count(self) -> int:
        return DataCenter.objects.filter(group=self).count()

    class Meta:
        verbose_name = _("数据中心分组")
        verbose_name_plural = _("数据中心分组")
        ordering = ["-updated_at"]


class DataCenter(BaseModel, CustomFieldsMixin, ConfigurableMixin, TrackingModelMixin):
    name = models.CharField(
        max_length=128,
        unique=True,
        verbose_name=_("名称"),
        help_text=_("数据中心的名称, 例如: 广州数据中心、上海数据中心、北京数据中心等"),
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("描述"),
        help_text=_("数据中心的描述, 例如: 广州数据中心、上海数据中心、北京数据中心等"),
    )
    duty_type = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        verbose_name=_("值班类型"),
        help_text=_("数据中心的值班类型, 例如: 7*24、7*8等"),
    )
    group = models.ForeignKey(
        DataCenterGroup,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        verbose_name=_("分组"),
        help_text=_("数据中心所属的分组, 例如: 华南区、华北区、华东区等"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("是否启用"),
        help_text=_("是否启用该数据中心"),
    )
    physical_address = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=_("物理地址"),
        help_text=_("建筑物的物理位置, 例如: 上海市浦东新区、北京市海淀区等"),
    )
    shipping_address = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=_("收货地址"),
        help_text=_("如果与物理地址不同, 则填写收货地址"),
    )
    latitude = models.DecimalField(
        max_digits=8,
        decimal_places=6,
        editable=False,
        blank=True,
        null=True,
        verbose_name=_("纬度"),
        help_text=_("GPS坐标,十进制格式(xx.yyyyyy)"),
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        editable=False,
        blank=True,
        null=True,
        verbose_name=_("经度"),
        help_text=_("GPS坐标,十进制格式(xx.yyyyyy)"),
    )
    contact_name = models.CharField(
        verbose_name=_("联系人姓名"), max_length=100, blank=True, null=True
    )
    contact_phone = models.CharField(
        verbose_name=_("联系人电话"), max_length=20, blank=True, null=True
    )
    contact_email = models.EmailField(
        verbose_name=_("联系人邮箱"), blank=True, null=True
    )
    security_level = models.CharField(
        max_length=50,
        choices=[
            ("tier1", "Tier I"),
            ("tier2", "Tier II"),
            ("tier3", "Tier III"),
            ("tier4", "Tier IV"),
        ],
        blank=True,
        null=True,
        verbose_name=_("安全等级"),
        help_text=_("数据中心的安全等级, 例如: Tier I、Tier II、Tier III、Tier IV"),
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "datacenter"),
        verbose_name=_("标签"),
        help_text=_("数据中心的标签, 例如: 核心机房、边缘机房、灾备机房等"),
    )
    configure = models.JSONField(
        blank=True,
        null=True,
        default=dict,
        verbose_name=_("配置信息"),
    )
    room_count = CounterCacheField(
        to_model="dcrm.Room",
        to_field="data_center",
        verbose_name=_("房间(个)"),
    )
    rack_count = CounterCacheField(
        to_model="dcrm.Rack",
        to_field="data_center",
        verbose_name=_("机柜(个)"),
    )
    tenant_count = CounterCacheField(
        to_model="dcrm.Tenant",
        to_field="data_center",
        verbose_name=_("租户(个)"),
    )
    device_count = CounterCacheField(
        to_model="dcrm.Device",
        to_field="data_center",
        verbose_name=_("设备(台)"),
        help_text=_("含历史在线的设备总数"),
    )
    subnet_count = CounterCacheField(
        to_model="dcrm.Subnet",
        to_field="data_center",
        verbose_name=_("子网(个)"),
    )
    user_count = CounterCacheField(
        to_model="dcrm.User",
        to_field="data_center",
        verbose_name=_("用户数(个)"),
    )
    warehouse_count = CounterCacheField(
        to_model="dcrm.Warehouse",
        to_field="data_center",
        verbose_name=_("仓库(个)"),
    )

    _icon = "fa fa-building"
    display_link_field = "name"
    search_fields = [
        "name",
    ]

    def __str__(self) -> str:
        return self.name

    class Meta:
        verbose_name = _("数据中心")
        verbose_name_plural = _("数据中心")
        ordering = ["name"]
        indexes = [
            # 基本索引
            models.Index(fields=["name"]),
            models.Index(fields=["group", "name"]),
            models.Index(fields=["is_active"]),
            # 地理位置索引
            models.Index(fields=["latitude", "longitude"]),
            # 部分索引 - 仅为活跃数据中心
            models.Index(
                fields=["name"],
                condition=models.Q(is_active=True),
                name="datacenter_active_only",
            ),
        ]


# 信号接收器 - 在创建数据中心后初始化默认配置
@receiver(post_save, sender=DataCenter)
def initialize_datacenter_configs(sender, instance, created, **kwargs):
    """
    当创建新的数据中心时，自动初始化默认配置
    """
    if created:
        instance.initialize_default_configs()
