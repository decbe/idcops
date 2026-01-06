import json
import logging
import re
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models, transaction
from django.db.models import Model, QuerySet
from django.forms import Field
from django.forms.widgets import DateInput, DateTimeInput
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from str2bool import str2bool

from .choices import CustomFieldTypeChoices, CustomFieldVisibilityChoices
from .mixins import BaseModel

logger = logging.getLogger(__name__)

__all__ = (
    "CustomFieldTypeChoices",
    "CustomField",
    "CustomFieldManager",
)


class CustomFieldManager(models.Manager):
    """自定义字段管理器
    """

    def get_for_model(
        self, model: type[Model], data_center: type[Model], hidden: bool = True
    ) -> QuerySet["CustomField"]:
        """返回分配给指定模型的所有CustomFields
        """
        if model is None:
            raise ValueError("model 参数不能为 None")
        if not hasattr(model, "_meta") or not hasattr(model._meta, "concrete_model"):
            raise ValueError("model 参数必须是有效的 Django 模型类")
        content_type = ContentType.objects.get_for_model(model._meta.concrete_model)
        queryset = (
            self.get_queryset()
            .filter(object_types=content_type, data_center=data_center, is_active=True)
            .order_by("order")
        )
        if hidden:
            return queryset.exclude(ui_visible=CustomFieldVisibilityChoices.HIDDEN)
        return queryset

    def get_for_models(
        self, models: Sequence[type[Model]], data_center: type[Model]
    ) -> QuerySet["CustomField"]:
        """返回分配给指定模型列表的所有CustomFields
        """
        content_types = [
            ContentType.objects.get_for_model(model._meta.concrete_model)
            for model in models
        ]
        return (
            self.get_queryset()
            .filter(object_types__in=content_types, data_center=data_center)
            .distinct()
        )

    def create_field(self, name: str, type: str, **kwargs: Any) -> "CustomField":
        """创建新的自定义字段
        """
        if not name.isidentifier():
            raise ValidationError(_("字段名称必须是有效的Python标识符"))

        if self.filter(name=name).exists():
            raise ValidationError(_("字段名称已存在"))

        if type not in dict(CustomFieldTypeChoices.choices):
            raise ValidationError(_("无效的字段类型"))

        field = self.model(name=name, type=type, **kwargs)

        field.full_clean()
        field.save()

        return field

    def copy_field(
        self, field: "CustomField", new_name: str | None = None
    ) -> "CustomField":
        """复制现有的自定义字段
        """
        if not isinstance(field, self.model):
            raise ValueError(_("必须提供CustomField实例"))

        field_copy = self.model.objects.get(pk=field.pk)
        field_copy.pk = None

        if new_name:
            field_copy.name = new_name
        else:
            base_name = field.name
            counter = 1
            while self.filter(name=f"{base_name}_{counter}").exists():
                counter += 1
            field_copy.name = f"{base_name}_{counter}"

        field_copy.save()
        field_copy.object_types.set(field.object_types.all())

        return field_copy

    def bulk_create_fields(
        self, field_definitions: list[dict[str, Any]]
    ) -> list["CustomField"]:
        """批量创建自定义字段
        """
        fields = []
        errors = []

        for index, definition in enumerate(field_definitions):
            try:
                field = self.create_field(**definition)
                fields.append(field)
            except (ValidationError, ValueError) as e:
                errors.append(
                    {"index": index, "definition": definition, "error": str(e)}
                )

        if errors:
            raise ValidationError({"errors": errors, "created_fields": fields})

        return fields

    def get_fields_for_content_type(self, content_type) -> QuerySet["CustomField"]:
        """获取指定ContentType的所有自定义字段
        """
        return self.get_queryset().filter(object_types=content_type)

    def get_required_fields(self, model=None) -> QuerySet["CustomField"]:
        """获取所有必填字段
        """
        qs = self.get_queryset().filter(required=True)
        if model:
            qs = qs.filter(object_types=ContentType.objects.get_for_model(model))
        return qs

    def get_unique_fields(self, model=None) -> QuerySet["CustomField"]:
        """获取所有唯一字段
        """
        qs = self.get_queryset().filter(unique=True)
        if model:
            qs = qs.filter(object_types=ContentType.objects.get_for_model(model))
        return qs

    def search_fields(self, search_term: str) -> QuerySet["CustomField"]:
        """搜索自定义字段
        """
        return self.get_queryset().filter(
            models.Q(name__icontains=search_term)
            | models.Q(label__icontains=search_term)
            | models.Q(description__icontains=search_term)
        )

    def get_by_natural_key(self, name: str) -> "CustomField":
        """通过自然键获取字段
        """
        return self.get(name=name)


class CustomField(BaseModel):
    """自定义字段模型
    """

    data_center = models.ForeignKey(
        to="dcrm.DataCenter",
        on_delete=models.PROTECT,
        verbose_name=_("数据中心"),
        help_text=_("数据中心"),
    )
    object_types = models.ManyToManyField(
        to=ContentType,
        related_name="custom_fields",
        limit_choices_to=models.Q(app_label="dcrm"),
        verbose_name=_("适用对象类型"),
        help_text=_("选择可以使用此字段的对象类型"),
    )

    type = models.CharField(
        max_length=50,
        choices=CustomFieldTypeChoices.choices,
        default=CustomFieldTypeChoices.TYPE_TEXT,
        verbose_name=_("字段类型"),
        help_text=_("此字段中的数据类型，对于对象/多对象字段，请选择相关对象类型。"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("是否启用"),
        help_text=_("是否启用此字段，启用后将在对应模型中生效"),
    )
    name = models.CharField(
        max_length=50,
        unique=True,
        validators=[
            RegexValidator(
                regex=r"^[a-z0-9_]+$", message=_("只允许使用小写字母、数字和下划线")
            ),
            RegexValidator(
                regex=r"__", message=_("不允许使用双下划线"), inverse_match=True
            ),
        ],
        verbose_name=_("字段名称"),
        help_text=_("唯一标识符, 只能使用小写字母、数字和下划线"),
    )

    label = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("显示名称"),
        help_text=_("在表单和列表中显示的名称，(不填写, 默认是字段名称)"),
    )

    ui_visible = models.SlugField(
        choices=CustomFieldVisibilityChoices.choices,
        default=CustomFieldVisibilityChoices.ONLY_DETAIL,
        blank=True,
        verbose_name=_("UI 可见性"),
        help_text=_("字段在 UI 中的可见性, 仅详情可见将不出现在列表中"),
    )

    description = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("描述"),
        help_text=_("这将显示为表单字段的帮助文本"),
    )

    required = models.BooleanField(
        default=False,
        verbose_name=_("是否必填"),
        help_text=_("创建新对象或编辑现有对象时，此字段是必填字段。"),
    )

    unique = models.BooleanField(
        default=False,
        verbose_name=_("是否唯一"),
        help_text=_("字段值在所属对象类型中必须唯一"),
    )

    default = models.JSONField(
        null=True, blank=True, verbose_name=_("默认值"), help_text=_("字段的默认值")
    )

    # 验证规则
    validation_minimum = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("最小值"),
        help_text=_("适用于数值类型字段"),
    )

    validation_maximum = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("最大值"),
        help_text=_("适用于数值类型字段"),
    )

    validation_regex = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_("正则验证"),
        help_text=_("适用于文本类型字段的正则表达式验证"),
    )

    # 选项设置
    choices = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_("选项"),
        help_text=_(
            "适用于选择类型字段，格式: 每行输入一个选项，可以在每个选项使用冒号来指定显示内容。例如：3a:AAA"
        ),
    )

    # 对象关联设置
    related_model = models.ForeignKey(
        ContentType,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        limit_choices_to=models.Q(app_label="dcrm"),
        related_name="custom_field_relations",
        verbose_name=_("关联模型"),
        help_text=_("选项数据来源的关联模型，适用于字段类型为对象或多对象"),
    )
    order = models.PositiveSmallIntegerField(
        default=100,
        verbose_name=_("排序"),
        help_text=_("字段的排序，数值越大排在越后面，默认值 100"),
    )

    filter_params = models.JSONField(
        null=True,
        blank=True,
        verbose_name=_("过滤参数"),
        help_text=_(
            '用于过滤关联对象的参数，格式: {"field": "value"}，适用于字段类型为对象或多对象'
        ),
    )

    objects = CustomFieldManager()

    _icon = "fa fa-cog"
    display_link_field = "name"
    search_fields = [
        "name",
    ]

    class Meta:
        verbose_name = _("自定义字段")
        verbose_name_plural = _("自定义字段")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["type", "name"], name="idx_customfield_type_name"),
            models.Index(fields=["ui_visible"], name="idx_customfield_ui_visible"),
        ]

    def __str__(self):
        return self.label or self.name

    def serialize(self, value):
        """Prepare a value for storage as JSON data.
        """
        if value is None:
            return value
        if self.type == CustomFieldTypeChoices.TYPE_DECIMAL and type(value) is Decimal:
            return float(value)
        if self.type == CustomFieldTypeChoices.TYPE_DATE and type(value) is date:
            return value.isoformat()
        if (
            self.type == CustomFieldTypeChoices.TYPE_DATETIME
            and type(value) is datetime
        ):
            return value.isoformat()
        if self.type == CustomFieldTypeChoices.TYPE_OBJECT and isinstance(
            value, models.Model
        ):
            return value.pk
        if self.type == CustomFieldTypeChoices.TYPE_MULTIOBJECT and isinstance(
            value, models.QuerySet
        ):
            return [obj.pk for obj in value] or None
        return value

    def deserialize(self, value):
        """Convert JSON data to a Python object suitable for the field type.
        """
        if value is None:
            return value
        if self.type == CustomFieldTypeChoices.TYPE_DECIMAL:
            return Decimal(value)
        if self.type == CustomFieldTypeChoices.TYPE_DATE:
            try:
                return date.fromisoformat(value)
            except ValueError:
                return value
        if self.type == CustomFieldTypeChoices.TYPE_DATETIME:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return value
        if self.type == CustomFieldTypeChoices.TYPE_OBJECT:
            model = self.related_model.model_class()
            return model.objects.filter(pk=value).first()
        if self.type == CustomFieldTypeChoices.TYPE_MULTIOBJECT:
            model = self.related_object_type.model_class()
            return model.objects.filter(pk__in=value)
        return value

    def clean(self):
        super().clean()

        # 验证默认值
        if self.default is not None:
            # 对于文本类型字段的特殊处理
            # if self.type != CustomFieldTypeChoices.TYPE_JSON:
            #     try:
            #         # 如果已经是JSON格式的字典，直接使用
            #         if isinstance(self.default, dict) and 'value' in self.default:
            #             pass
            #         # 如果是字符串，包装成JSON格式
            #         else:
            #             self.default = {'value': str(self.default)}
            #     except (TypeError, ValueError) as e:
            #         raise ValidationError({
            #             'default': _(
            #                 '文本类型字段的默认值无效: {}'
            #             ).format(str(e))
            #         })

            try:
                # 验证实际值
                logger.warning(f"{self.get_default_value()}")
                # self.validate(self.get_default_value())
            except ValidationError as err:
                raise ValidationError(
                    {
                        "default": _('默认值 "{value}" 无效: {error}').format(
                            value=self.default, error=err.message
                        )
                    }
                )

        # 验证数值范围
        if self.type not in (
            CustomFieldTypeChoices.TYPE_INTEGER,
            CustomFieldTypeChoices.TYPE_DECIMAL,
        ):
            if self.validation_minimum is not None:
                raise ValidationError(
                    {"validation_minimum": _("最小值只适用于数值类型字段")}
                )
            if self.validation_maximum is not None:
                raise ValidationError(
                    {"validation_maximum": _("最大值只适用于数值类型字段")}
                )

        # 验证正则表达式
        if self.validation_regex and self.type not in (
            CustomFieldTypeChoices.TYPE_TEXT,
            CustomFieldTypeChoices.TYPE_LONGTEXT,
            CustomFieldTypeChoices.TYPE_URL,
        ):
            raise ValidationError(
                {"validation_regex": _("正则验证只适用于文本类型字段")}
            )

        # 验证选项集
        if self.type in (
            CustomFieldTypeChoices.TYPE_SELECT,
            CustomFieldTypeChoices.TYPE_MULTISELECT,
        ):
            if not self.choices:
                raise ValidationError({"choices": _("选择类型字段必须定义选项")})
            try:
                choices = (
                    json.loads(self.choices)
                    if isinstance(self.choices, str)
                    else self.choices
                )
                if not isinstance(choices, list) or not all(
                    isinstance(c, list) and len(c) == 2 for c in choices
                ):
                    raise ValidationError
            except ValueError:
                raise ValidationError({"choices": _("选项格式无效")})

        # 验证关联对象
        if self.type in (
            CustomFieldTypeChoices.TYPE_OBJECT,
            CustomFieldTypeChoices.TYPE_MULTIOBJECT,
        ):
            if not self.related_model:
                raise ValidationError(
                    {"related_model": _("对象类型字段必须指定关联模型")}
                )
            if self.filter_params:
                try:
                    if not isinstance(json.loads(self.filter_params), dict):
                        raise ValidationError
                except ValueError:
                    raise ValidationError({"filter_params": _("过滤参数格式无效")})

        # 验证隐藏值，隐藏值不能必填，
        if self.ui_visible == CustomFieldVisibilityChoices.HIDDEN:
            if self.required:
                raise ValidationError({"required": _("隐藏字段不能是必填")})

        # 验证唯一性约束
        if self.unique and self.type in (
            CustomFieldTypeChoices.TYPE_BOOLEAN,
            CustomFieldTypeChoices.TYPE_MULTISELECT,
            CustomFieldTypeChoices.TYPE_MULTIOBJECT,
        ):
            raise ValidationError({"unique": _("多值字段不支持唯一性约束")})

    def validate(self, value: Any) -> None:
        """验证字段值"""
        if value not in [None, ""]:
            # 文本字段验证
            if self.type in (
                CustomFieldTypeChoices.TYPE_TEXT,
                CustomFieldTypeChoices.TYPE_LONGTEXT,
            ):
                if not isinstance(value, str):
                    raise ValidationError(_("值必须是字符串"))
                if self.validation_regex:
                    if not re.match(self.validation_regex, value):
                        raise ValidationError(_("值不匹配正则表达式规则"))

            # 整数验证
            elif self.type == CustomFieldTypeChoices.TYPE_INTEGER:
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    raise ValidationError(_("值必须是整数"))
                if (
                    self.validation_minimum is not None
                    and value < self.validation_minimum
                ):
                    raise ValidationError(
                        _("值不能小于 {min}").format(min=self.validation_minimum)
                    )
                if (
                    self.validation_maximum is not None
                    and value > self.validation_maximum
                ):
                    raise ValidationError(
                        _("值不能大于 {max}").format(max=self.validation_maximum)
                    )

            # 小数验证
            elif self.type == CustomFieldTypeChoices.TYPE_DECIMAL:
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    raise ValidationError(_("值必须是数字"))
                if (
                    self.validation_minimum is not None
                    and value < self.validation_minimum
                ):
                    raise ValidationError(
                        _("值不能小于 {min}").format(min=self.validation_minimum)
                    )
                if (
                    self.validation_maximum is not None
                    and value > self.validation_maximum
                ):
                    raise ValidationError(
                        _("值不能大于 {max}").format(max=self.validation_maximum)
                    )

            # 布尔值验证
            elif self.type == CustomFieldTypeChoices.TYPE_BOOLEAN:
                try:
                    value = str2bool(value, raise_exc=True)
                except ValueError as e:
                    if not isinstance(value, bool):
                        raise ValidationError(_("值必须是布尔类型: {e}").format(e=e))

            # 日期验证
            elif self.type == CustomFieldTypeChoices.TYPE_DATE:
                if not isinstance(value, date) and value.lower() != "now":
                    try:
                        date.fromisoformat(value)
                    except (TypeError, ValueError):
                        raise ValidationError(_("日期格式无效，应为 YYYY-MM-DD"))

            # 日期时间验证
            elif self.type == CustomFieldTypeChoices.TYPE_DATETIME:
                if not isinstance(value, datetime) and value.lower() != "now":
                    try:
                        datetime.fromisoformat(value)
                    except (TypeError, ValueError):
                        raise ValidationError(
                            _("日期时间格式无效，应为 YYYY-MM-DD HH:MM:SS")
                        )

            # URL验证
            elif self.type == CustomFieldTypeChoices.TYPE_URL:
                from django.core.validators import URLValidator

                try:
                    URLValidator()(value)
                except ValidationError:
                    raise ValidationError(_("URL格式无效"))

            # JSON验证
            elif self.type == CustomFieldTypeChoices.TYPE_JSON:
                try:
                    if isinstance(value, str):
                        json.loads(value)
                except json.JSONDecodeError:
                    raise ValidationError(_("JSON格式无效"))

            # 选择验证
            elif self.type == CustomFieldTypeChoices.TYPE_SELECT:
                choices = (
                    json.loads(self.choices)
                    if isinstance(self.choices, str)
                    else self.choices
                )
                if not choices:
                    choices = []
                if choices is None:
                    choices = []
                valid_values = [c[0] for c in choices]
                if value not in valid_values:
                    raise ValidationError(_("选项值无效"))

            # 多选验证
            elif self.type == CustomFieldTypeChoices.TYPE_MULTISELECT:
                if not isinstance(value, (list, tuple)):
                    raise ValidationError(_("值必须是列表类型"))
                choices = (
                    json.loads(self.choices)
                    if isinstance(self.choices, str)
                    else self.choices
                )
                valid_values = [c[0] for c in choices]
                invalid_values = [v for v in value if v not in valid_values]
                if invalid_values:
                    raise ValidationError(
                        _("选项值无效: {values}").format(
                            values=", ".join(map(str, invalid_values))
                        )
                    )

            # 对象验证
            elif self.type == CustomFieldTypeChoices.TYPE_OBJECT:
                try:
                    model = self.related_model.model_class()
                    if isinstance(value, model):
                        value = value.pk
                    if not model.objects.filter(pk=value).exists():
                        raise ValidationError(_("对象不存在"))
                except (AttributeError, ValueError):
                    raise ValidationError(_("对象值无效"))

            # 多对象验证
            elif self.type == CustomFieldTypeChoices.TYPE_MULTIOBJECT:
                if not isinstance(value, (list, tuple, models.QuerySet)):
                    raise ValidationError(_("值必须是列表类型"))
                try:
                    model = self.related_model.model_class()
                    if not all(
                        isinstance(v, (model, int, str))
                        and model.objects.filter(
                            pk=v.pk if isinstance(v, model) else v
                        ).exists()
                        for v in value
                    ):
                        raise ValidationError(_("一个或多个对象不存在"))
                except (AttributeError, ValueError):
                    raise ValidationError(_("对象值无效"))

        # TODO: 必填字段没有默认值时会抛出异常
        elif self.required and self.default:
            raise ValidationError(_("必填字段不能为空"))

        # 验证唯一性
        if self.unique and value is not None:
            for content_type in self.object_types.all():
                model = content_type.model_class()
                if model:
                    query = {f"custom_field_data__{self.name}": value}
                    if model.objects.filter(**query).count() > 1:
                        raise ValidationError(_("值必须唯一"))

    def to_form_field(
        self, set_initial: bool = True, enforce_required: bool = True
    ) -> Field:
        """返回用于在表单中渲染此自定义字段的表单字段
        """
        default = self.get_default_value()
        initial = default if set_initial else None
        required = self.required if enforce_required else False

        # 基础字段参数
        field_kwargs: dict[str, Any] = {
            "required": required,
            "initial": initial,
            "label": self.label or self.name,
            "help_text": self.description,
        }

        # 根据字段类型创建表单字段
        if self.type == CustomFieldTypeChoices.TYPE_INTEGER:
            field_kwargs.update(
                {
                    "min_value": self.validation_minimum,
                    "max_value": self.validation_maximum,
                }
            )
            field = forms.IntegerField(**field_kwargs)

        elif self.type == CustomFieldTypeChoices.TYPE_DECIMAL:
            field_kwargs.update(
                {
                    "min_value": self.validation_minimum,
                    "max_value": self.validation_maximum,
                    "max_digits": 15,
                    "decimal_places": 4,
                }
            )
            field = forms.DecimalField(**field_kwargs)

        elif self.type == CustomFieldTypeChoices.TYPE_BOOLEAN:
            # field_kwargs['choices'] = (
            #     (None, '---------'),
            #     (True, _('是')),
            #     (False, _('否')),
            # )
            field = forms.NullBooleanField(**field_kwargs)

        elif self.type == CustomFieldTypeChoices.TYPE_DATE:
            initial_value = field_kwargs["initial"]
            if initial_value and initial_value.lower() == "now":
                field_kwargs["initial"] = date.today()
            field_kwargs["widget"] = DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            )
            field = forms.DateField(**field_kwargs)

        elif self.type == CustomFieldTypeChoices.TYPE_DATETIME:
            initial_value = field_kwargs["initial"]
            if initial_value and initial_value.lower() == "now":
                field_kwargs["initial"] = datetime.now()
            field_kwargs["widget"] = DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            )
            field = forms.DateTimeField(**field_kwargs)

        elif self.type == CustomFieldTypeChoices.TYPE_URL:
            field = forms.URLField(**field_kwargs)

        elif self.type == CustomFieldTypeChoices.TYPE_JSON:
            field_kwargs["widget"] = forms.Textarea(attrs={"rows": 4})
            field = forms.JSONField(**field_kwargs)

        elif self.type == CustomFieldTypeChoices.TYPE_SELECT:
            choices = (
                json.loads(self.choices)
                if isinstance(self.choices, str)
                else self.choices
            )
            field_kwargs["choices"] = (
                [("", "---------")] + choices if not required else choices
            )
            field = forms.ChoiceField(**field_kwargs)

        elif self.type == CustomFieldTypeChoices.TYPE_MULTISELECT:
            choices = (
                json.loads(self.choices)
                if isinstance(self.choices, str)
                else self.choices
            )
            field_kwargs["choices"] = choices
            field = forms.MultipleChoiceField(**field_kwargs)

        elif self.type == CustomFieldTypeChoices.TYPE_OBJECT:
            model = self.related_model.model_class()
            field_kwargs["queryset"] = model.objects.all()
            if self.filter_params:
                filter_params = (
                    json.loads(self.filter_params)
                    if isinstance(self.filter_params, str)
                    else self.filter_params
                )
                field_kwargs["queryset"] = field_kwargs["queryset"].filter(
                    **filter_params
                )
            field = forms.ModelChoiceField(**field_kwargs)

        elif self.type == CustomFieldTypeChoices.TYPE_MULTIOBJECT:
            model = self.related_model.model_class()
            field_kwargs["queryset"] = model.objects.all()
            if self.filter_params:
                filter_params = (
                    json.loads(self.filter_params)
                    if isinstance(self.filter_params, str)
                    else self.filter_params
                )
                field_kwargs["queryset"] = field_kwargs["queryset"].filter(
                    **filter_params
                )
            field = forms.ModelMultipleChoiceField(**field_kwargs)

        elif self.type == CustomFieldTypeChoices.TYPE_LONGTEXT:
            field_kwargs["widget"] = forms.Textarea(attrs={"rows": 4})
            field = forms.CharField(**field_kwargs)

        else:  # TYPE_TEXT
            if self.validation_regex:
                field_kwargs["validators"] = [
                    RegexValidator(
                        regex=self.validation_regex,
                        message=_("值必须匹配正则表达式: {regex}").format(
                            regex=self.validation_regex
                        ),
                    )
                ]
            field = forms.CharField(**field_kwargs)
        field.widget.attrs["class"] = "form-control"
        if required:
            field.label = format_html(
                '{}<span class="text-red" style="margin-left: 5px;">*</span>',
                self.label or self.name,
            )
        field.custom = True
        return field

    def remove_stale_data(self, content_types=None):
        """删除不再相关的自定义字段数据
        """
        if content_types is None:
            content_types = self.object_types.all()

        for ct in content_types:
            if model := ct.model_class():
                instances = model.objects.filter(
                    custom_field_data__has_key=self.name
                ).iterator()

                batch = []
                batch_size = 100
                logger.info(f"Removing stale data for {self.name} in {model.__name__}")
                for instance in instances:
                    if self.name in instance.custom_field_data:
                        del instance.custom_field_data[self.name]
                        batch.append(instance)

                        if len(batch) >= batch_size:
                            model.objects.bulk_update(batch, ["custom_field_data"])
                            batch = []

                if batch:
                    model.objects.bulk_update(batch, ["custom_field_data"])

    def rename_field_data(self, old_name):
        """重命名字段时更新所有相关数据
        """
        if old_name == self.name:
            return

        for ct in self.object_types.all():
            if model := ct.model_class():
                instances = model.objects.filter(
                    custom_field_data__has_key=old_name
                ).iterator()

                batch = []
                batch_size = 100

                for instance in instances:
                    if old_name in instance.custom_field_data:
                        instance.custom_field_data[self.name] = (
                            instance.custom_field_data.pop(old_name)
                        )
                        batch.append(instance)

                        if len(batch) >= batch_size:
                            model.objects.bulk_update(batch, ["custom_field_data"])
                            batch = []

                if batch:
                    model.objects.bulk_update(batch, ["custom_field_data"])

    def save(self, *args, **kwargs):
        # 检查是否是新创建的字段或字段值已更改
        if self.pk:
            old_instance = CustomField.objects.get(pk=self.pk)
            # 检查所有可能影响关联对象的字段变化
            fields_changed = any(
                [
                    old_instance.default != self.default,
                    old_instance.type != self.type,
                    old_instance.required != self.required,
                    old_instance.validation_minimum != self.validation_minimum,
                    old_instance.validation_maximum != self.validation_maximum,
                    old_instance.validation_regex != self.validation_regex,
                    old_instance.choices != self.choices,
                    old_instance.related_model_id != self.related_model_id,
                    old_instance.filter_params != self.filter_params,
                ]
            )

            # 处理字段重命名
            if old_instance.name != self.name:
                # 遍历所有关联的内容类型
                for content_type in self.object_types.all():
                    model = content_type.model_class()
                    if not model:
                        continue

                    with transaction.atomic():
                        for obj in model.objects.all():
                            if not obj.custom_field_data and self.default is not None:
                                # 如果对象没有该字段值，则设置默认值
                                obj.custom_field_data = {
                                    self.name: self.get_default_value()
                                }
                                obj.save()
                            elif (
                                obj.custom_field_data
                                and old_instance.name in obj.custom_field_data
                            ):
                                obj.custom_field_data[self.name] = (
                                    obj.custom_field_data.pop(old_instance.name)
                                )
                                obj.save()
        else:
            fields_changed = self.default is not None
        if not self.label:
            self.label = self.name.replace("_", " ").title()
        if not self.is_active:
            # 不启用时，隐藏字段，不显示在列表中，不强制必填，不唯一
            self.ui_visible = CustomFieldVisibilityChoices.HIDDEN
            self.required = False
            self.unique = False
        # 保存字段
        super().save(*args, **kwargs)

        # 如果有字段变化，更新关联对象
        if fields_changed:
            logger.info(
                f"Updating related objects for {self.name} due to field changes"
            )
            transaction.on_commit(self.update_related_objects)

    def update_related_objects(self):
        """更新所有关联对象的自定义字段值"""
        try:
            # 获取所有关联的内容类型
            for content_type in self.object_types.all():
                model = content_type.model_class()
                if not model:
                    continue

                # 获取默认值
                default_value = self.get_default_value()
                if default_value is None:
                    continue

                # 批量更新逻辑
                with transaction.atomic():
                    # 获取所有没有该自定义字段值的对象
                    objects_to_update = []
                    for obj in model.objects.all():
                        custom_field_data = obj.custom_field_data or {}

                        # 只更新没有值或值为空的字段
                        if self.name not in custom_field_data or custom_field_data[
                            self.name
                        ] in [None, "", {}]:
                            custom_field_data[self.name] = default_value
                            obj.custom_field_data = custom_field_data
                            objects_to_update.append(obj)

                    # 批量更新
                    if objects_to_update:
                        model.objects.bulk_update(
                            objects_to_update, ["custom_field_data"], batch_size=100
                        )

                        logger.info(
                            f"Updated {len(objects_to_update)} objects with default value "
                            f"for custom field {self.name} in model {model.__name__}"
                        )

        except Exception as e:
            logger.error(
                f"Error updating objects with default value for custom field {self.name}: {str(e)}"
            )
            raise

    def get_default_value(self):
        """获取字段的实际默认值"""
        if self.default is None:
            return None
        # 对于文本类型字段，从JSON中提取字符串值
        # if self.type not in (CustomFieldTypeChoices.TYPE_JSON,):
        #     if isinstance(self.default, dict) and 'value' in self.default:
        #         return self.default['value']
        #     return None
        return self.default
