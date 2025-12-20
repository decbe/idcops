import logging

from mptt.managers import TreeManager
from mptt.models import MPTTModel, TreeForeignKey

from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models.signals import post_save, pre_delete
from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _

from .mixins import BaseModel, CustomFieldsMixin

logger = logging.getLogger(__name__)


AUTO_FILL_MODELS = getattr(
    settings,
    "AUTO_FILL_MODELS",
    [
        "dcrm.device",
        "dcrm.devicehost",
        "dcrm.patchcord",
        "dcrm.Warehouse",
        "dcrm.InventoryItem",
        "dcrm.ItemInstance",
    ],
)

__all__ = [
    "CodingRule",
    "CodingRuleManager",
]


def auto_fill_models_filter() -> models.Q:
    """
    获取标签选择器选项
    """
    if not AUTO_FILL_MODELS:
        return models.Q(app_label="dcrm")
    fill_models = []
    for model in AUTO_FILL_MODELS:
        model_name = model.split(".")[-1].lower()
        try:
            fill_models.append(apps.get_model("dcrm", model_name)._meta.model_name)
        except LookupError as e:
            logger.error(f"LookupError: {e}")
            continue
    q = models.Q(app_label="dcrm", model__in=fill_models)
    return q


class CodingRuleManager(TreeManager):
    """编码规则管理器"""

    def get_for_model(self, model, data_center):
        """获取指定模型的编码规则"""
        model = ContentType.objects.get_for_model(model)
        return self.get_queryset().filter(content_type=model, data_center=data_center)


class CodingRule(BaseModel, MPTTModel, CustomFieldsMixin):
    """
    应用于设备，机柜，跳线，库存等
    """

    parent = TreeForeignKey(
        to="self",
        on_delete=models.CASCADE,
        related_name="children",
        blank=True,
        null=True,
        db_index=True,
        verbose_name=_("父级"),
        help_text=_("此对象的父级对象"),
    )
    data_center = models.ForeignKey(
        to="dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("房间所属的数据中心"),
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        limit_choices_to=auto_fill_models_filter,
        verbose_name=_("应用于"),
        help_text=_("规则将自动应用到目标字段上进行自动填充"),
    )
    to_field = models.SlugField(
        verbose_name=_("目标字段"),
        help_text=_("规则将自动应用到目标字段上进行自动填充"),
    )
    name = models.CharField(max_length=64, verbose_name=_("名称"))
    prefix = models.CharField(
        max_length=30, verbose_name=_("前缀"), help_text=_("规则前缀，例如：ISDX020-")
    )
    start_at = models.SlugField(
        verbose_name=_("起始序号"), help_text=_("通常是数字序列，例如：00000")
    )
    suffix = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        verbose_name=_("后缀"),
        help_text=_("规则后缀，例如：-XYZ"),
    )
    is_enum = models.BooleanField(
        default=False,
        editable=False,
        blank=True,
        null=True,
        verbose_name=_("是否枚举"),
        help_text=_("是否枚举，枚举时，容量为1，并且不显示容量"),
    )
    capacity = models.IntegerField(
        blank=True, null=True, verbose_name="容量", help_text=_("该编码规则总容量")
    )
    width = models.DecimalField(
        blank=True,
        null=True,
        max_digits=5,
        decimal_places=2,
        verbose_name=_("标签宽度"),
        help_text=_("该规则打印标签的时候的宽度，单位：mm(毫米)"),
    )
    used_amount = models.IntegerField(
        blank=True,
        null=True,
        verbose_name=_("已使用"),
        help_text=_("该编码规则已使用的数量"),
    )
    height = models.DecimalField(
        blank=True,
        null=True,
        max_digits=5,
        decimal_places=2,
        verbose_name=_("标签高度"),
        help_text=_("该规则打印标签的时候的高度，单位：mm(毫米)"),
    )
    description = models.TextField(
        blank=True, null=True, verbose_name=_("描述"), help_text=_("定义该规则的描述")
    )

    objects = CodingRuleManager()

    _icon = "fa fa-barcode"
    display_link_field = "name"
    search_fields = [
        "name",
    ]
    supports_import = True

    def __str__(self) -> str:
        return self.name

    class Meta:
        verbose_name = _("编号规则")
        verbose_name_plural = _("编号规则")
        unique_together = [
            ("data_center", "name"),
            ("data_center", "content_type", "to_field"),
        ]
        indexes = [
            models.Index(fields=["content_type", "to_field"]),
            models.Index(fields=["data_center", "content_type", "to_field"]),
        ]

    class MPTTMeta:
        order_insertion_by = ("name",)

    def clean(self):
        super().clean()
        # 不能是自己的子节点
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
        # 验证目标字段是否存在
        model = self.content_type.model_class()
        if model is None:
            raise ValidationError(
                {"content_type": _("无法获取目标模型类，请检查 content_type 设置")}
            )
        try:
            target_field = model._meta.get_field(self.to_field)
        except FieldDoesNotExist:
            model_name = model._meta.model_name
            raise ValidationError(
                {
                    "to_field": _("目标模型 [%(model)s] 中没有 [%(field)s] 这个字段")
                    % {"model": model_name, "field": self.to_field}
                }
            )
        # 验证目标字段是否为字符串类型
        if not isinstance(
            target_field, (models.CharField, models.SlugField, models.TextField)
        ):
            model_class = self.content_type.model_class()
            model_name = model_class._meta.model_name if model_class else "UnknownModel"
            raise ValidationError(
                {
                    "to_field": _("目标模型字段 [%(model)s.%(field)s] 必须是字符串类型")
                    % {"model": model_name, "field": self.to_field}
                }
            )

    def save(self, *args, **kwargs):
        # 保存时，自动更新编码规则的容量
        self.capacity = self.get_max_number()
        self.used_amount = self.get_used_amount()
        return super().save(*args, **kwargs)

    def get_max_number(self):
        """
        计算编码规则的容量
        如果 start_at 不为空，则计算容量
        """
        if not self.start_at:
            return 0
        length = len(self.start_at)
        return int("9" * length)

    def get_available_codes(self, limit=1):
        """
        获取可用靠前的编码，返回列表
        正常情况下列表长度应该为 1
        遇到预留，或其他情况不是序列时，返回多个最靠前的编码

        Returns:
            list: 可用的编码列表
        """
        if self.suffix and self.suffix.strip():
            regex_pattern = f"{self.prefix}([0-9]+){self.suffix}$".strip()
        else:
            regex_pattern = f"{self.prefix}([0-9]+)$".strip()
        model_class = self.content_type.model_class()
        if model_class is None:
            return []
        used_codes = (
            model_class.objects.filter(**{f"{self.to_field}__regex": regex_pattern})
            .only(self.to_field)
            .values_list(self.to_field, flat=True)
            .order_by(self.to_field)
        )

        _last_used_number = used_codes.last()
        if _last_used_number:
            last_used_number = _last_used_number.split(self.prefix)[1]
        else:
            last_used_number = self.start_at
        result = []
        for i in range(1, limit + 1):
            next_number = f"%0{len(last_used_number)}d" % (int(last_used_number) + i)
            result.append(self.get_next_code(next_number))
        return result

    def get_next_code(self, last_used_number: str) -> str:
        """
        获取下一个编码
        """
        next_number = f"%0{len(last_used_number)}d" % (int(last_used_number))
        if self.suffix and self.suffix.strip():
            return f"{self.prefix}{next_number}{self.suffix}".strip()
        else:
            return f"{self.prefix}{next_number}".strip()

    def get_used_amount(self):
        """
        获取已使用数量
        """
        model_class = self.content_type.model_class()
        if model_class is None:
            return 0
        return model_class.objects.filter(
            **{f"{self.to_field}__regex": self.get_regex_pattern()}
        ).count()

    def get_regex_pattern(self):
        """
        获取正则表达式模式
        """
        if self.suffix and self.suffix.strip():
            return f"{self.prefix}([0-9]+){self.suffix}$".strip()
        else:
            return f"{self.prefix}([0-9]+)$".strip()

    def get_available_amount(self):
        """
        获取可用数量
        """
        capacity = self.capacity if self.capacity is not None else 0
        return capacity - self.get_used_amount()

    def available_next_number(self):
        """
        获取下一个可用编码
        """
        return self.get_available_codes(limit=1)[0]

    available_next_number.short_description = _("下一个可用")


def update_coding_rule_used_amount_for_related_models(**kwargs):
    instance = kwargs.get("instance")
    if not instance or not hasattr(instance, "data_center"):
        return
    supported_models = ContentType.objects.filter(
        auto_fill_models_filter()
    ).values_list("model", flat=True)
    ct = ContentType.objects.get_for_model(instance)
    if ct.model not in supported_models:
        return
    # 更新相关模型的编码规则用量
    model_coding_rules = CodingRule.objects.filter(
        content_type=ct, data_center=instance.data_center
    )
    for coding_rule in model_coding_rules:
        coding_rule.used_amount = coding_rule.get_used_amount()
        coding_rule.save(update_fields=["used_amount"])


post_save.connect(
    receiver=update_coding_rule_used_amount_for_related_models,
    dispatch_uid="post_save_update_coding_rule_used_amount_for_related_models",
)
pre_delete.connect(
    receiver=update_coding_rule_used_amount_for_related_models,
    dispatch_uid="pre_delete_update_coding_rule_used_amount_for_related_models",
)
