from ast import Tuple
from typing import Any

from django.apps import apps
from django.contrib.admin.utils import (
    display_for_field,
    display_for_value,
    get_fields_from_path,
)
from django.contrib.contenttypes.fields import GenericForeignKey
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import ManyToOneRel
from django.db.models.constants import LOOKUP_SEP
from django.db.models.functions import (
    TruncDay,
    TruncMonth,
    TruncQuarter,
    TruncWeek,
    TruncYear,
)
from django.db.models.functions.datetime import (
    TruncDay,
    TruncMonth,
    TruncQuarter,
    TruncWeek,
    TruncYear,
)
from django.urls import resolve, reverse
from django.urls.exceptions import Resolver404
from django.utils.html import format_html, strip_tags
from django.utils.safestring import mark_safe
from django.utils.translation import get_language

from dcrm.constants import SELECT2_TRANSLATIONS
from dcrm.models import CustomField, User
from dcrm.models.fields import DeviceHeightField, RackPositionField

from .base import camel_to_snake, lookup_field_verbose
from .display import get_object_display

__all__ = [
    "EMPTY_VALUE_DISPLAY",
    "LookupFields",
    "is_model_field",
    "get_view_info_by_url_name",
    "get_model_view_url_name",
    "create_trunc_function",
]


EMPTY_VALUE_DISPLAY = "-"


class LookupFields:
    """用于查找模型字段的类
    """

    def __init__(
        self,
        model: type[models.Model] | models.Model,
        fields: list[str],
        custom_fields: models.QuerySet | None = None,
        empty_value_display: str = EMPTY_VALUE_DISPLAY,
        primary_link: bool = False,
        user: User | None = None,
    ):
        """初始化 LookupFields

        Args:
            model: Django 模型类或模型实例
            fields: 字段名称列表，支持外键路径 (如 ['id', 'name', 'model__name'])
            empty_value_display: 空值显示的字符串

        """
        # 如果传入的是模型实例，获取其类
        exclude_fields = ["_password", "password"]
        self.model = model if isinstance(model, type) else model.__class__
        self.fields = [field for field in fields if field not in exclude_fields]
        self.opts = self.model._meta
        self.empty_value_display = empty_value_display
        self.primary_link = primary_link
        self.custom_fields = custom_fields
        if custom_fields is not None:
            self.custom_fields_maps = {
                field.name: field for field in self.custom_fields
            }
        else:
            self.custom_fields_maps = {}
        # 预处理字段信息
        self._field_info = {}
        for field_name in fields:
            if LOOKUP_SEP in field_name:
                continue  # 跳过外键路径，它们需要动态处理
            try:
                field = self.opts.get_field(field_name)
                self._field_info[field_name] = {
                    "field": field,
                    "is_bool": isinstance(field, models.BooleanField),
                    "is_foreign": isinstance(
                        field, (models.ForeignKey, GenericForeignKey)
                    ),
                    "is_many": isinstance(field, models.ManyToManyField),
                    "is_many_to_one": isinstance(field, models.ManyToOneRel),
                    "has_choices": hasattr(field, "choices") and field.choices,
                    "is_display": hasattr(self.model, "display_link_field"),
                    "is_position": isinstance(
                        field, (RackPositionField, DeviceHeightField)
                    ),
                    "is_datetime": isinstance(
                        field, (models.DateField, models.DateTimeField)
                    ),
                }
            except FieldDoesNotExist:
                custom_field = self.custom_fields_maps.get(field_name, None)
                if custom_field:
                    self._field_info[field_name] = {
                        "field": custom_field,
                        "is_custom": True,
                    }
                else:
                    self._field_info[field_name] = None

    def get_field_labels(self) -> dict[str, str]:
        """批量获取所有字段的标签

        Returns:
            Dict[str, str]: 字段名到标签的映射，如 {'name': '名称', 'status': '状态'}

        """
        return {field: self.get_field_label(field) for field in self.fields}

    def get_field_values(
        self,
        obj: models.Model | type,
        html: bool = True,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """批量获取所有字段的值

        Args:
            obj: 模型实例或模型类
            html: 是否返回HTML格式的值，为False时返回纯文本
            fields: 指定要获取的字段，为None时获取所有字段

        Returns:
            Dict[str, Any]: 字段名到值的映射，如 {'name': '设备1', 'status': '<span class="badge bg-green">正常</span>'}

        Raises:
            TypeError: 如果传入的 obj 既不是模型实例也不是模型类

        """
        # 如果是模型实例，正常处理
        fields = fields or self.fields

        # 如果传入的是模型类，返回字段默认值
        if isinstance(obj, type):
            result = {}
            for field_name in fields:
                try:
                    field = self.opts.get_field(field_name)
                    result[field_name] = (
                        field.get_default()
                        if field.has_default()
                        else self.empty_value_display
                    )
                except FieldDoesNotExist:
                    result[field_name] = self.empty_value_display
            return result

        if html:
            return {field: self.get_field_value(obj, field) for field in fields}
        return {field: self.get_field_value_as_str(obj, field) for field in fields}

    def get_field_label(self, field_name: str) -> str:
        """获取字段的标签名称"""
        return lookup_field_verbose(
            self.model, self.custom_fields, field_name, self.custom_fields_maps
        )

    def handle_position_value(self, obj, field_name: str) -> str:
        """处理 RackPositionField 和 DeviceHeightField 的值"""
        field = self.opts.get_field(field_name)
        value = field.value_to_string(obj)
        return value if value else self.empty_value_display

    def handle_display_link_value(self, obj) -> str:
        """处理主键字段的值"""
        display_field, display_value, display_url = get_object_display(obj)
        if hasattr(obj, "lft") and obj.lft > 1 and hasattr(obj, "level"):
            display_value = mark_safe(
                f"""{'<span class="text-muted">•</span>' * obj.level} {display_value}"""
            )
        if display_url:
            return format_html('<a href="{}">{}</a>', display_url, display_value)
        return display_value

    def handle_choices_value(
        self, obj, field_name: str, field, html: bool = True
    ) -> str:
        """处理选择字段的值"""
        value = getattr(obj, field_name)
        if value is None:
            return self.empty_value_display

        # 获取显示值
        display_value = getattr(obj, f"get_{field_name}_display")()
        if not html:
            return display_value
        # 检查是否有颜色处理方法
        choices_class = (
            getattr(field.default, "__class__", None) if field.default else None
        )
        if choices_class and hasattr(choices_class, "get_color"):
            color = choices_class.get_color(value)
            if color:
                return format_html(
                    '<span class="label bg-{}">{}</span>', color, display_value
                )
        return display_value

    def handle_foreign_value(self, value: models.Model) -> str:
        """处理外键字段的值"""
        if hasattr(value, "get_absolute_url"):
            href = value.get_absolute_url()
            icon = getattr(value, "icon", None)
            color = getattr(value, "color", None)
            if icon:
                template = '<img src="{}" alt="{}" style="width: auto; height: 18px;">'
                icon = format_html(template, str(icon.url), str(value))
            if color and not icon:
                template = '<a href="{}"><span class="label bg-{}">{}</span></a>'
                return format_html(template, href, color, str(value))
            return format_html(
                '<a class="text-info" href="{}">{} {}</a>',
                href,
                icon if icon else "",
                str(value),
            )
        return str(value)

    def handle_one_to_many_value(self, value: models.Manager) -> str:
        """处理一对多字段的值"""
        # TODO: 处理成列表，不允许在list中展示
        if value is None:
            return self.empty_value_display
        return ", ".join(map(str, value.all()))

    def handle_many_to_many_value(self, value: models.Manager) -> str:
        """处理多对多字段的值
        支持以下格式：
        1. QuerySet 对象
        2. 空格分隔的标签字符串
        3. 逗号分隔的标签字符串
        """
        # 处理字符串类型的值（标签字符串）
        if isinstance(value, str):
            # 优先使用逗号分割，如果没有逗号就用空格分割
            tags = value.split(",") if "," in value else value.split()
            # 清理空白字符
            tags = [tag.strip() for tag in tags if tag.strip()]
            if not tags:
                return self.empty_value_display
            # 将标签转换为带样式的 span 标签
            spans = []
            for tag in tags:
                spans.append(
                    format_html(
                        '<a href="{}"><span class="badge bg-info margin-r-5">{}</span></a>',
                        tag.get_absolute_url(),
                        tag,
                    )
                )
            return format_html("".join(["{}" for _ in spans]), *spans)

        values = value.all()

        if not values.exists():
            return self.empty_value_display

        # 检查是否支持颜色
        if hasattr(value.model, "color"):
            # 预先构建模板字符串，避免重复拼接
            template = '<a href="{}"><span class="label bg-{} margin-r-5">{}</span></a>'
            spans = []
            for v in values:
                spans.append(
                    format_html(template, v.get_absolute_url(), v.color, str(v))
                )
            return format_html("".join(["{}" for _ in spans]), *spans)

        return ", ".join(map(str, values))

    def handle_custom_field_value(self, obj: models.Model, field_name: str) -> Any:
        """处理自定义字段的值"""
        field = self.custom_fields_maps.get(field_name)
        value = obj.get_custom_field_display(field_name, field)
        return display_for_value(value, self.empty_value_display)

    def handle_property_value(self, obj: models.Model, field_name: str) -> str:
        """处理属性或方法的值"""
        value = getattr(obj, field_name)
        if callable(value):
            value = value()
        return str(value) if value is not None else self.empty_value_display

    def handle_lookup_path_value(self, obj: models.Model, field_name: str) -> str:
        """处理外键路径的值"""
        value = obj
        fk, remote_field = get_fields_from_path(self.model, field_name)
        remote_value = getattr(value, fk.name, None)
        if remote_value is None:
            return self.empty_value_display
        lookup = LookupFields(
            model=fk.related_model,
            fields=[
                remote_field.name,
            ],
            custom_fields=CustomField.objects.none(),
            empty_value_display=self.empty_value_display,
        )
        return lookup.get_field_value(remote_value, remote_field.name)

    def handle_bool_value(
        self, obj: models.Model, field: models.Field, value: bool
    ) -> str:
        """处理布尔字段的值，返回带颜色的标签

        Args:
            obj: 模型实例
            field: 字段对象
            value: 布尔值

        Returns:
            str: 格式化后的 HTML 标签，例如：
                True -> '<span class="label bg-green">是</span>'
                False -> '<span class="label bg-red">否</span>'

        """
        # 获取显示文本
        text = getattr(
            obj, f"get_{field.name}_display", lambda: "是" if value else "否"
        )()
        icon = "check" if value else "times"

        # 设置标签颜色
        color = "green" if value else "red"

        return format_html(
            '<i class="fa fa-{} text-{}"></i><span class="hidden">{}</span>',
            icon,
            color,
            text,
        )

    def handle_datetime_value(self, value) -> str:
        """处理日期时间字段的值"""
        return display_for_value(value, self.empty_value_display)

    def get_field_value(self, obj: models.Model, field_name: str) -> Any:
        """获取字段值，支持外键路径、自定义字段、多对多字段等
        返回的值可能包含 HTML 标签
        """
        # 使用缓存的自定义字段名称集合进行检查
        if field_name in self.custom_fields_maps.keys():
            return self.handle_custom_field_value(obj, field_name)

        # 优先处理外键路径
        if LOOKUP_SEP in field_name:
            return self.handle_lookup_path_value(obj, field_name)

        # 处理显示链接字段
        if (
            field_name == getattr(self.model, "display_link_field", None)
            and self.primary_link
        ):
            return self.handle_display_link_value(obj)

        # 获取字段值
        value = getattr(obj, field_name, None)
        if value is None:
            return self.empty_value_display

        # 使用预处理的字段信息
        field_info = self._field_info.get(field_name)
        if field_info is None:
            # 字段不存在，尝试处理属性或方法
            return (
                self.handle_property_value(obj, field_name)
                if hasattr(obj, field_name)
                else self.empty_value_display
            )

        field = field_info["field"]

        # 按字段类型处理值
        if field_info["is_bool"]:
            return self.handle_bool_value(obj, field, value)

        if field_info["has_choices"] and hasattr(obj, f"get_{field_name}_display"):
            return self.handle_choices_value(obj, field_name, field)

        if field_info["is_foreign"]:
            return self.handle_foreign_value(value)

        if field_info["is_many"]:
            return self.handle_many_to_many_value(value)

        if field_info["is_position"]:
            return self.handle_position_value(obj, field_name)

        if field_info["is_datetime"]:
            return self.handle_datetime_value(value)

        # 处理其他类型字段
        return display_for_field(
            value, field, empty_value_display=self.empty_value_display
        )

    def get_field_value_as_str(self, obj: models.Model, field_name: str) -> str:
        """获取字段值的纯文本形式，移除所有 HTML 标签
        """
        value = self.get_field_value(obj, field_name)
        return strip_tags(str(value)) if value is not None else self.empty_value_display

    def __str__(self) -> str:
        return f"{self.model.__name__}.{','.join(self.fields)}"


def is_model_field(model, field_name):
    """判断一个字符串是否为模型中的字段
    """
    try:
        model._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False


def get_view_info_by_url_name(url_name):
    """通过URL name获取视图相关信息

    Args:
        url_name: URL的名称

    Returns:
        dict: 包含视图信息的字典

    """
    try:
        url = reverse(url_name)
        return resolve(url)
    except Resolver404:
        return None


def get_model_view_url_name(model, view_type="list") -> str:
    model_name = camel_to_snake(model._meta.object_name)
    return f"{model_name}_{view_type}"


def get_related_models(model):
    """Return a list of all models which have a ForeignKey to the given model and the name of the field. For example,
    `get_related_models(Tenant)` will return all models which have a ForeignKey relationship to Tenant.
    """
    related_models = [
        (field.related_model, field.remote_field)
        for field in model._meta.related_objects
        if type(field) is ManyToOneRel
    ]

    return related_models


def get_custom_field_models(
    exclude_models: list[str] | None = None,
) -> list[type[models.Model]]:
    """获取所有包含自定义字段的模型
    """
    dcrm_models = apps.get_app_config("dcrm").get_models()
    from dcrm.models.mixins import CustomFieldsMixin

    default_exclude_models = [
        "datacenter",
        "datacentergroup",
    ]
    if exclude_models is None:
        exclude_models = default_exclude_models
    else:
        exclude_models = list(set(exclude_models).union(default_exclude_models))
    cf_models = [
        model
        for model in dcrm_models
        if issubclass(model, CustomFieldsMixin)
        and not model._meta.proxy
        and model._meta.model_name not in exclude_models
    ]
    return cf_models


def get_cf_models_query():
    """获取所有包含自定义字段的模型 Q 查询
    """
    query = models.Q()
    cf_models = [m._meta.model_name for m in get_custom_field_models()]
    query |= models.Q(model__in=cf_models)
    return query


def get_cf_models_queryset():
    """获取所有包含自定义字段的模型 queryset
    """
    from django.contrib.contenttypes.models import ContentType

    return ContentType.objects.filter(get_cf_models_query())


def get_select2_language():
    lang_code = get_language()
    supported_code = SELECT2_TRANSLATIONS.get(lang_code)
    if supported_code is None and lang_code is not None:
        # If 'zh-hant-tw' is not supported, try subsequent language codes i.e.
        # 'zh-hant' and 'zh'.
        i = None
        while (i := lang_code.rfind("-", 0, i)) > -1:
            if supported_code := SELECT2_TRANSLATIONS.get(lang_code[:i]):
                return supported_code
    return supported_code


def generate_cable_label_by_nodes(src, apoint, zpoint) -> dict[int, str]:
    """根据数据源和节点始终，生成相对应的跳线标签

    src: 数据源，apoint：起始节点，zpoint，终止节点
    """
    assert src in ["device", "port"]
    flag_map = {"100": "CRo", "010": "CRa", "001": "LRa", "000": "CRoD"}
    if src == "port":
        adevice = apoint.device
        zdevice = zpoint.device
        aport = apoint.name
        zport = zpoint.name
    else:
        adevice = apoint
        zdevice = zpoint
        aport = ""
        zport = ""
    aroom = adevice.rack.room
    arack = adevice.rack
    aposition = adevice.position
    zroom = zdevice.rack.room
    zrack = zdevice.rack
    zposition = zdevice.position
    cross_room = int(aroom != zroom)
    cross_rack = int(not cross_room and arack != zrack)
    local_rack = int(arack == zrack)
    mask = f"{cross_room}{cross_rack}{local_rack}"
    flag = flag_map.get(mask)
    data = {
        1: f"{arack}#U{aposition}<={flag}=>{zrack}#U{zposition}",
        2: f"{arack}#U{aposition}#{adevice}<={flag}=>{zrack}#U{zposition}#{zdevice}",
        3: f"{arack}#U{aposition}#{adevice}#{aport}<={flag}=>{zrack}#U{zposition}#{zdevice}#{zport}",
    }
    return data


def create_trunc_function(
    aggregation, field
) -> TruncDay | TruncWeek | TruncMonth | TruncQuarter | TruncYear | None:
    """创建时间截断函数用于数据库查询的日期聚合

    根据指定的聚合类型和字段名，创建相应的Django ORM时间截断函数，
    用于在数据库层面按指定时间单位对日期字段进行分组聚合。

    Args:
        aggregation (str): 聚合类型，支持 'day', 'week', 'month', 'quarter', 'year'
        field (str): 需要进行时间截断的字段名

    Returns:
        TruncDay | TruncWeek | TruncMonth | TruncQuarter | TruncYear | None:
        对应的Django时间截断函数实例，如果聚合类型不支持则返回None

    Examples:
        >>> create_trunc_function('day', 'created_at')
        TruncDay('created_at')

        >>> create_trunc_function('month', 'created_at')
        TruncMonth('created_at')

        >>> create_trunc_function('invalid', 'created_at')
        None

    """
    aggregation = aggregation.lower()
    if aggregation == "day":
        return TruncDay(field)
    elif aggregation == "week":
        return TruncWeek(field)
    elif aggregation == "month":
        return TruncMonth(field)
    elif aggregation == "quarter":
        return TruncQuarter(field)
    elif aggregation == "year":
        return TruncYear(field)
    else:
        raise ValueError("Invalid aggregation")


def format_date_display(trend_stats: list | Tuple | None, aggregation: str) -> dict:
    """格式化趋势统计中的日期显示

    根据不同的聚合方式格式化日期显示格式，将统计结果中的日期转换为适合图表显示的字符串格式

    Args:
        trend_stats: 趋势统计数据列表，每个元素包含'period'键表示时间周期
        aggregation: 聚合方式，支持'day', 'week', 'month', 'quarter', 'year'等

    Returns:
        dict: 包含格式化后日期列表的字典，格式为 {"dates": [格式化后的日期字符串列表]}

    Examples:
        >>> trend_stats = [{'period': datetime(2023, 1, 1)}, {'period': datetime(2023, 1, 2)}]
        >>> format_date_display(trend_stats, 'day')
        {'dates': ['2023-01-01', '2023-01-02']}

        >>> format_date_display(trend_stats, 'week')
        {'dates': ['2023-W00', '2023-W00']}

    """
    trend_data = {"dates": []}
    raw_periods = [normalize_to_date(item["period"]) for item in trend_stats]
    periods = sorted(set(raw_periods))
    if periods:
        # 格式化日期显示
        if aggregation == "day":
            trend_data["dates"] = [period.strftime("%Y-%m-%d") for period in periods]
        elif aggregation == "week":
            trend_data["dates"] = [period.strftime("%Y-W%U") for period in periods]
        elif aggregation == "month":
            trend_data["dates"] = [period.strftime("%Y-%m") for period in periods]
        elif aggregation == "quarter":
            trend_data["dates"] = [
                f"{period.year}-Q{(period.month-1)//3+1}" for period in periods
            ]
        elif aggregation == "year":
            trend_data["dates"] = [period.strftime("%Y") for period in periods]
        else:
            trend_data["dates"] = [period.strftime("%Y-%m-%d") for period in periods]
    return trend_data


def normalize_to_date(value) -> Any:
    """获取所有时间段（兼容 date 与 datetime）
    """
    from datetime import datetime as dt

    if isinstance(value, dt):
        return value.date()
    return value
