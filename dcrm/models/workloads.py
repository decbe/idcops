from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _

from .base import NestedGroupModel
from .mixins import BaseModel, CustomFieldsMixin

__all__ = ["WorkloadType", "Workload"]


class WorkloadType(NestedGroupModel, CustomFieldsMixin):
    """工作量类型
    """

    data_center = models.ForeignKey(
        "DataCenter",
        on_delete=models.CASCADE,
        verbose_name=_("数据中心"),
    )
    shared = models.BooleanField(
        default=True,
        blank=True,
        verbose_name=_("是否共享"),
        help_text=_("是否共享给其他数据中心引用"),
    )

    _icon = "fa fa-tasks"
    display_link_field = "name"
    search_fields = ["name"]

    def __str__(self) -> str:
        return self.name

    class Meta:
        verbose_name = _("工作量类型")
        verbose_name_plural = _("工作量类型")


class Workload(BaseModel, CustomFieldsMixin):
    """工作量
    """

    data_center = models.ForeignKey(
        "DataCenter",
        on_delete=models.CASCADE,
        verbose_name=_("数据中心"),
    )
    assign_to = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name=_("分配给"),
        help_text=_("分配给哪个模型"),
    )
    name = models.CharField(verbose_name=_("名称"), max_length=100)
    workload_type = models.ForeignKey(
        WorkloadType,
        on_delete=models.CASCADE,
        verbose_name=_("工作量类型"),
    )
    description = models.CharField(verbose_name=_("描述"), max_length=200, blank=True)
    duration = models.IntegerField(verbose_name=_("工时"), help_text=_("工时"))

    _icon = "fa fa-tasks"
    display_link_field = "name"
    search_fields = ["name"]

    def __str__(self) -> str:
        return self.name

    class Meta:
        verbose_name = _("工作量")
        verbose_name_plural = _("工作量")
        ordering = ["workload_type", "name"]
