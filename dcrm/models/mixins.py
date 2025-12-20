import json
from datetime import date, datetime
from typing import Any, List, Literal, Optional, Type

from mptt.managers import TreeManager
from mptt.models import MPTTModel, TreeForeignKey
from str2bool import str2bool

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from dcrm.middleware import get_current_user
from dcrm.utilities.base import camel_to_snake

from .choices import ColorChoices
from .utils import upload_to

__all__ = [
    "AbsoluteUrlMixin",
    "BaseModel",
    "ContentMixin",
    "CreatedAtMixin",
    "CreatedByMixin",
    "CreatedUpdatedMixin",
    "CustomFieldsMixin",
    "NestedGroupModel",
    "UpdatedAtMixin",
    "UpdatedByMixin",
    "ConfigurableMixin",
    "ColorMixin",
]


class AbsoluteUrlMixin:
    """Absolute URL Mixin"""

    def get_absolute_url(self) -> Any | Literal["#"]:
        opts = self._meta
        model_name = camel_to_snake(opts.object_name)
        try:
            url = reverse(f"{model_name}_detail", args=[self.pk])
        except NoReverseMatch:
            url = "#"
        return url

    def get_absolute_url_with_concrete(self) -> Any | Literal["#"]:
        opts = self._meta
        if opts.proxy:
            opts = opts.concrete_model._meta
        model_name = camel_to_snake(opts.object_name)
        try:
            url = reverse(f"{model_name}_detail", args=[self.pk])
        except NoReverseMatch:
            url = "#"
        return url

    def get_update_url(self) -> Any | Literal["#"]:
        opts = self._meta
        model_name = camel_to_snake(opts.object_name)
        try:
            url = reverse(f"{model_name}_update", args=[self.pk])
        except NoReverseMatch:
            url = "#"
        return url

    def get_delete_url(self) -> Any | Literal["#"]:
        opts = self._meta
        model_name = camel_to_snake(opts.object_name)
        try:
            url = reverse(f"{model_name}_delete", args=[self.pk])
        except NoReverseMatch:
            url = "#"
        return url

    def get_create_url(self) -> Any | None:
        opts = self._meta
        model_name = camel_to_snake(opts.object_name)
        try:
            url = reverse(f"{model_name}_create")
        except NoReverseMatch:
            url = None
        return url

    def get_list_url(self) -> Any | Literal["#"]:
        opts = self._meta
        model_name = camel_to_snake(opts.object_name)
        try:
            url = reverse(f"{model_name}_list")
        except NoReverseMatch:
            url = "#"
        return url


class CreatedByMixin(models.Model):
    """
    创建人Mixin
    user model: settings.AUTH_USER_MODEL
    related_name: %(app_label)s_%(class)s_created
    related_name Usage:
    user.dcrm_device_created.all()
    user.dcrm_device_created.set([device1, device2])
    """

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_created",
        verbose_name=_("创建人"),
        help_text=_("此对象的创建者"),
    )

    class Meta:
        abstract = True


class UpdatedByMixin(models.Model):
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_updated",
        blank=True,
        null=True,
        verbose_name=_("更新人"),
        help_text=_("此对象的最后修改者"),
    )

    class Meta:
        abstract = True


class CreatedAtMixin(models.Model):
    created_at = models.DateTimeField(
        default=timezone.datetime.now,
        editable=True,
        verbose_name=_("创建时间"),
        help_text=_("此对象的创建时间"),
    )

    class Meta:
        abstract = True


class UpdatedAtMixin(models.Model):
    updated_at = models.DateTimeField(
        auto_now=True,
        null=True,
        blank=True,
        editable=True,
        verbose_name=_("更新时间"),
        help_text=_("此对象的最后修改时间"),
    )

    class Meta:
        abstract = True
        ordering = ["-updated_at"]


class CreatedUpdatedMixin(
    CreatedByMixin,
    UpdatedByMixin,
    CreatedAtMixin,
    UpdatedAtMixin,
):
    class Meta:
        abstract = True


class ContentMixin(CreatedUpdatedMixin):
    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        models.PROTECT,
        verbose_name=_("数据中心"),
        related_name="%(app_label)s_%(class)s_data_center",
    )
    content_type = models.ForeignKey(
        ContentType,
        models.PROTECT,
        verbose_name=_("内容类型"),
        help_text=_("涉及的模块类型"),
        related_name="%(app_label)s_%(class)s_content_type",
        limit_choices_to={"app_label": "dcrm"},
    )
    object_id = models.PositiveIntegerField(
        verbose_name=_("对象ID"),
        blank=True,
        null=True,
    )
    object_repr = GenericForeignKey("content_type", "object_id")
    object_repr.short_description = _("对象")
    content = models.JSONField(
        verbose_name=_("内容"),
        blank=True,
        null=True,
    )

    def __str__(self):
        if self.object_id:
            return str(self.object_repr)
        else:
            return str(self.content_type)

    class Meta:
        abstract = True


class BaseModel(AbsoluteUrlMixin, CreatedUpdatedMixin):
    """
    基础模型，包含数据中心管理器
    fields include:
        - created_by
        - updated_by
        - created_at
        - updated_at
    """

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """
        保存时设置创建者和更新者
        """
        is_new = self.pk is None
        if is_new:
            if hasattr(self, "created_by") and self.created_by is None:
                if user := get_current_user():
                    self.created_by = user
        else:
            if hasattr(self, "updated_by") and self.updated_by is None:
                if user := get_current_user():
                    self.updated_by = user
        super().save(*args, **kwargs)


class NestedGroupModel(BaseModel, MPTTModel):
    """
    用于形成层次结构的对象的基模型（区域、位置等）。这些模型递归使用MPTT。
    在每个父级中，每个子实例必须有一个唯一的名称。
    """

    parent = TreeForeignKey(
        to="self",
        on_delete=models.CASCADE,
        related_name="children",
        blank=True,
        null=True,
        db_index=True,
        verbose_name=_("上一级"),
        help_text=_("此对象的上一级对象"),
    )
    name = models.CharField(verbose_name=_("名称"), max_length=100)
    description = models.TextField(verbose_name=_("描述"), blank=True)

    objects = TreeManager()

    class Meta:
        abstract = True

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


class ColorMixin(models.Model):
    color = models.SlugField(
        choices=ColorChoices.choices,
        default=ColorChoices.get_default_color,
        null=True,
        blank=True,
        verbose_name=_("颜色"),
    )

    class Meta:
        abstract = True

    def color_with_html(self) -> str:
        color = self.get_color_display()
        if self.color:
            return mark_safe(
                f'<span class="label bg-{self.color}" style="display: inline-block; width: 7rem;">{color}</span>'
            )
        return color

    color_with_html.short_description = _("直观颜色")


class IconMixin(models.Model):
    icon = models.ImageField(
        upload_to=upload_to,
        blank=True,
        null=True,
        verbose_name=_("图标"),
        help_text=_("对象图标"),
    )

    class Meta:
        abstract = True

    def icon_exists(self):
        """
        验证图标文件是否存在
        根据Django官方文档的最佳实践进行文件存在性检查
        """
        # 首先检查字段是否有值（Django推荐方式）
        if not self.icon:
            return False

        # 检查文件名是否有效
        if not self.icon.name:
            return False

        # 检查存储后端是否可用
        if not hasattr(self.icon, "storage") or not hasattr(
            self.icon.storage, "exists"
        ):
            return False

        # 最后检查文件是否真实存在
        try:
            return self.icon.storage.exists(self.icon.name)
        except (ValueError, OSError):
            # 处理可能的文件系统错误
            return False

    def icon_with_html(self) -> str:
        if self.icon:
            return mark_safe(
                f'<img src="{self.icon.url}" alt="{self.name}" style="width: auto; height: 18px;">'
            )
        return ""

    icon_with_html.short_description = _("图标")


class CustomFieldsMixin(models.Model):
    """
    为模型添加自定义字段支持的Mixin
    """

    custom_field_data = models.JSONField(
        verbose_name=_("自定义字段数据"),
        default=dict,
        blank=True,
        help_text=_("存储自定义字段的值"),
    )

    class Meta:
        abstract = True

    @cached_property
    def custom_fields(self):
        if not hasattr(self, "custom_field_data"):
            self.custom_field_data = {}
        if not hasattr(self, "data_center") or not getattr(self, "data_center"):
            return
        if hasattr(self, "data_center") and not self.data_center:
            user = get_current_user()
            if not user.data_center:
                raise ValidationError(_("用户没有设置默认的数据中心"))
            self.data_center = user.data_center
        from .customfields import CustomField

        if not hasattr(self, "_custom_fields"):
            self._custom_fields = CustomField.objects.get_for_model(
                self.__class__, self.data_center
            )
        return self._custom_fields

    def clean_custom_fields(self):
        """
        验证所有自定义字段的值
        """
        # if not hasattr(self, "custom_field_data"):
        #     self.custom_field_data = {}
        # if not hasattr(self, "data_center"):
        #     return
        # if hasattr(self, "data_center") and not self.data_center:
        #     user = get_current_user()
        #     if not user.data_center:
        #         raise ValidationError(_("用户没有设置默认的数据中心"))
        #     self.data_center = user.data_center

        # from .customfields import CustomField
        custom_fields = self.custom_fields
        if not custom_fields:
            return
        # custom_fields = CustomField.objects.get_for_model(
        #     self.__class__, self.data_center
        # )
        errors = {}

        # 验证所有字段
        for cf in custom_fields:
            value = self.custom_field_data.get(cf.name)
            try:
                cf.validate(value)
            except ValidationError as e:
                errors[f"cf_{cf.name}"] = e.messages

        # 验证唯一性约束
        for cf in custom_fields.filter(unique=True):
            value = self.custom_field_data.get(cf.name)
            if value is not None:
                query = {f"custom_field_data__{cf.name}": value}
                qs = self.__class__.objects.filter(**query)
                if self.pk:
                    qs = qs.exclude(pk=self.pk)
                if qs.exists():
                    errors[f"cf_{cf.name}"] = [_("此值已被使用，必须唯一")]

        if errors:
            raise ValidationError(errors)

    def clean(self):
        """
        在保存前验证自定义字段
        """
        super().clean()
        self.clean_custom_fields()

    def get_custom_field_value(
        self, field_name: str, field: Type["models.Model"], default: Any = None
    ) -> Any:
        """
        获取自定义字段的值

        :param field_name: 字段名称
        :param default: 默认值
        :return: 字段值
        """
        # from .customfields import CustomField

        # if (
        #     # cf := CustomField.objects.get_for_model(self.__class__, self.data_center)
        #     cf := self.custom_fields.filter(name=field_name).first()
        # ):
        value = self.custom_field_data.get(field_name, default)
        if value is not None and isinstance(value, (int, list, tuple)):
            if field.type == "object" and not isinstance(value, models.Model):
                return field.related_model.model_class().objects.get(pk=value)
            elif field.type == "multiobject" and isinstance(value, (list, tuple)):
                return field.related_model.model_class().objects.filter(pk__in=value)

        return value

    def set_custom_field_value(
        self, field_name: str, value: Any, data_center: Type[models.Model]
    ) -> None:
        """
        设置自定义字段的值

        :param field_name: 字段名称
        :param value: 字段值
        :raises: ValidationError 如果值无效
        :raises: ValueError 如果字段不存在
        """
        from .customfields import CustomField

        try:
            cf = self.custom_fields.get(name=field_name)
            # cf = CustomField.objects.get_for_model(
            #     self.__class__, data_center=data_center
            # ).get(name=field_name)
        except CustomField.DoesNotExist:
            raise ValueError(
                f"Custom field '{field_name}' does not exist for {self.__class__.__name__}"
            )

        # 处理对象类型的值
        if value is not None:
            if cf.type == "object" and isinstance(value, models.Model):
                value = value.pk
            elif cf.type == "multiobject" and isinstance(value, (list, tuple)):
                value = [v.pk if isinstance(v, models.Model) else v for v in value]

        # 验证值
        cf.validate(value)

        # 设置值
        if not hasattr(self, "custom_field_data"):
            self.custom_field_data = {}

        if value is None and field_name in self.custom_field_data:
            del self.custom_field_data[field_name]
        else:
            self.custom_field_data[field_name] = value

    def get_custom_fields(self):
        """
        获取所有自定义字段及其值

        :return: 包含字段信息和值的字典列表
        """

        if not hasattr(self, "data_center"):
            user = get_current_user()
            self.data_center = user.data_center
        # custom_fields = CustomField.objects.get_for_model(
        #     self.__class__, self.data_center
        # )
        custom_fields = self.custom_fields
        result = []

        for cf in custom_fields:
            result.append(
                {
                    "field": cf,
                    "value": self.get_custom_field_value(cf.name, cf),
                    "display": self.get_custom_field_display(cf.name, cf),
                }
            )

        return result

    def get_custom_field_display(
        self, field_name: str, field: Type["models.Model"]
    ) -> Optional[str]:
        """
        获取自定义字段的显示值

        :param field_name: 字段名称
        :return: 格式化后的显示值
        """
        from .customfields import CustomField

        try:
            # cf = CustomField.objects.get_for_model(
            #     self.__class__, self.data_center
            # ).get(name=field_name)
            # cf = self.custom_fields.get(name=field_name)
            value = self.get_custom_field_value(field_name, field)

            if value is None:
                return ""

            # 处理选择类型
            if field.type in ("select", "multiselect"):
                choices = dict(
                    json.loads(field.choices)
                    if isinstance(field.choices, str)
                    else field.choices
                )
                if field.type == "select":
                    return choices.get(str(value), value)
                else:
                    return ", ".join(choices.get(str(v), str(v)) for v in value)

            # 处理对象类型
            elif field.type == "object":
                return str(value) if value else ""
            elif field.type == "multiobject":
                return ", ".join(map(str, value)) if value else ""

            # 处理布尔类型
            elif field.type == "boolean":
                if not isinstance(value, bool):
                    return str2bool(value)
                return value

            # 处理日期类型
            elif field.type == "date" and isinstance(value, (date, str)):
                try:
                    if isinstance(value, str):
                        value = date.fromisoformat(value)
                    return value.strftime("%Y-%m-%d")
                except ValueError:
                    return value

            # 处理日期时间类型
            elif field.type == "datetime" and isinstance(value, (datetime, str)):
                try:
                    if isinstance(value, str):
                        value = datetime.fromisoformat(value)
                    return value.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    return value

            return str(value)

        except CustomField.DoesNotExist:
            return None

    def validate_custom_fields(self) -> None:
        """
        验证所有自定义字段值

        :raises: ValidationError 如果任何字段值无效
        """
        self.clean_custom_fields()

    def save(self, *args, **kwargs):
        """
        重写save方法以确保在保存前验证自定义字段
        """
        if not hasattr(self, "data_center"):
            return super().save(*args, **kwargs)
        self.validate_custom_fields()
        # 如果是新对象且没有自定义字段数据，则设置默认值
        if not self.pk and not self.custom_field_data:
            if hasattr(self, "data_center") and not self.data_center:
                user = get_current_user()
                if not user.data_center:
                    raise ValidationError(_("用户没有设置默认的数据中心"))
                self.data_center = user.data_center

            # custom_fields = CustomField.objects.get_for_model(
            #     self.__class__, self.data_center
            # )
            custom_fields = self.custom_fields
            if custom_fields:
                for field in custom_fields.filter(default__isnull=False):
                    transaction.on_commit(field.update_related_objects)
        super().save(*args, **kwargs)

    @classmethod
    def get_custom_field_names(cls, data_center) -> List[str]:
        """
        获取此模型的所有自定义字段名称

        :return: 字段名称列表
        """
        from .customfields import CustomField

        return list(
            CustomField.objects.get_for_model(cls, data_center).values_list(
                "name", flat=True
            )
        )

    @classmethod
    def get_custom_field_choices(
        cls, data_center, field_name: str
    ) -> Optional[List[tuple]]:
        """
        获取选择类型字段的选项

        :param field_name: 字段名称
        :return: 选项列表或None
        """
        from .customfields import CustomField

        if (
            cf := CustomField.objects.get_for_model(cls, data_center)
            .filter(name=field_name)
            .first()
        ):
            if cf.type in ("select", "multiselect"):
                return (
                    json.loads(cf.choices)
                    if isinstance(cf.choices, str)
                    else cf.choices
                )
        return None


class ConfigurableMixin(models.Model):
    """
    提供配置管理功能的混入类，用于统一管理各种模型的配置信息。

    要求使用此Mixin的模型必须具有configure JSONField字段：
    configure = models.JSONField(
        blank=True,
        null=True,
        default=dict,
        verbose_name=_("配置信息"),
    )

    数据结构简化为：
    configure = {
        "configs": {
            "KEY1": value1,
            "KEY2": value2
        }
    }

    元数据信息在渲染时从params.py中获取。
    """

    class Meta:
        abstract = True

    def _system_config_instance_by_proxy(self):
        """
        使用其中一个DataCenter实例来代理持久化系统配置
        """
        from .base import DataCenter

        return DataCenter.objects.filter().order_by("pk").first()

    def _get_system_config(self, key, default=None) -> Any:
        """
        使用代理持久化数据中心实例来获取系统配置
        """
        datacenter = self._system_config_instance_by_proxy()
        if not datacenter:
            return
        configs = datacenter.configure.get("system_configs", {})
        return configs.get(key, default)

    def _set_system_config(self, key, value):
        """
        使用代理持久化数据中心实例来存储系统配置
        """
        datacenter = self._system_config_instance_by_proxy()
        if not datacenter:
            return
        # 确保configure字段已初始化
        if not hasattr(datacenter, "configure") or datacenter.configure is None:
            datacenter.configure = {}

        # 确保configs子字段存在
        if "system_configs" not in datacenter.configure:
            datacenter.configure["system_configs"] = {}

        # 直接设置值
        datacenter.configure["system_configs"][key] = value

        # 保存更改
        datacenter.save(update_fields=["configure"])

    def _delete_system_config(self, key):
        """
        删除系统配置项
        """
        datacenter = self._system_config_instance_by_proxy()
        if not datacenter:
            return
        # 确保configure字段已初始化
        if not hasattr(datacenter, "configure") or not datacenter.configure:
            return False

        # 确保configs子字段存在
        if "system_configs" not in datacenter.configure:
            return False

        # 如果键存在则删除
        if key in datacenter.configure["system_configs"]:
            del datacenter.configure["system_configs"][key]
            # 保存更改
            datacenter.save(update_fields=["configure"])
            return True

        return False

    def get_config(self, key, default=None, is_system=False):
        """
        获取配置值

        :param key: 配置键名
        :param default: 默认值，如果配置不存在则返回此值
        :param is_system: 是否为系统配置
        :return: 配置值

        使用示例：
        value = instance.get_config('CONFIG_KEY', 'default_value')
        """
        # 如果是系统配置，则使用系统配置 key
        if is_system:
            return self._get_system_config(key, default)

        # 确保configure字段已初始化
        if not hasattr(self, "configure") or not self.configure:
            return default

        # 确保configs子字段存在
        configs = self.configure.get("configs", {})

        # 直接获取值
        return configs.get(key, default)

    def set_config(self, key, value, is_system=False):
        """
        设置单个配置

        :param key: 配置键名
        :param value: 配置值
        :param is_system: 是否为系统配置

        使用示例：
        instance.set_config('CONFIG_KEY', 'value')
        """
        # 如果是系统配置，则使用系统配置key system_configs
        if is_system:
            self._set_system_config(key, value)
            return

        # 确保configure字段已初始化
        if not hasattr(self, "configure") or self.configure is None:
            self.configure = {}

        # 确保configs子字段存在
        if "configs" not in self.configure:
            self.configure["configs"] = {}

        # 直接设置值
        self.configure["configs"][key] = value

        # 保存更改
        self.save(update_fields=["configure"])

    def delete_config(self, key, is_system=False):
        """
        删除配置项

        :param key: 配置键名
        :param is_system: 是否为系统配置
        :return: 布尔值，表示是否成功删除（True-删除成功，False-配置不存在）

        使用示例：
        success = instance.delete_config('CONFIG_KEY')
        """
        # 删除系统配置项
        if is_system:
            self._delete_system_config(key)
            return

        # 确保configure字段已初始化
        if not hasattr(self, "configure") or not self.configure:
            return False

        # 确保configs子字段存在
        if "configs" not in self.configure:
            return False

        # 如果键存在则删除
        if key in self.configure["configs"]:
            del self.configure["configs"][key]
            # 保存更改
            self.save(update_fields=["configure"])
            return True

        return False

    def get_all_configs(self):
        """
        获取所有配置

        :return: 所有配置的字典，格式：{'key1': value1, 'key2': value2, ...}

        使用示例：
        all_configs = instance.get_all_configs()
        """
        # 确保configure字段已初始化
        if not hasattr(self, "configure") or not self.configure:
            return {}

        # 返回configs子字段
        return self.configure.get("configs", {}).copy()

    def update_configs(self, configs_dict):
        """
        批量更新配置

        :param configs_dict: 配置字典，格式：{'key1': value1, 'key2': value2, ...}

        使用示例：
        instance.update_configs({
            'KEY1': 'value1',
            'KEY2': 'value2'
        })
        """
        # 确保configure字段已初始化
        if not hasattr(self, "configure") or self.configure is None:
            self.configure = {}

        # 确保configs子字段存在
        if "configs" not in self.configure:
            self.configure["configs"] = {}

        # 更新configs子字段
        self.configure["configs"].update(configs_dict)

        # 保存更改
        self.save(update_fields=["configure"])

    def initialize_default_configs(self, default_configs=None):
        """
        初始化默认配置

        :param default_configs: 默认配置字典，如果为None则使用子类定义的DEFAULT_CONFIGS

        使用示例：
        # 使用子类定义的DEFAULT_CONFIGS
        instance.initialize_default_configs()

        # 或者提供自定义的默认配置
        instance.initialize_default_configs({
            'KEY1': 'value1',
            'KEY2': 'value2'
        })
        """
        if default_configs is None:
            # 尝试使用子类定义的DEFAULT_CONFIGS
            default_configs = getattr(self.__class__, "DEFAULT_CONFIGS", {})

        # 批量设置默认配置
        self.update_configs(default_configs)
