from django.apps import apps
from django.conf import settings
from django.contrib import admin
from django.db import models
from django.utils.translation import gettext_lazy as _

# Register your models here.

label, model = settings.AUTH_USER_MODEL.split(".")
User = apps.get_model(label, model, require_ready=False)

dcrm_models = apps.get_app_config("dcrm").get_models()


def check_initialization():
    """
    检查初始化
    """
    from dcrm.models import DataCenter
    from dcrm.register import registry

    if not User.objects.filter(is_superuser=True).exists():
        registry["has_superuser"] = False
    if not DataCenter.objects.filter().exists():
        registry["has_datacenter"] = False


PER_PAGE = 50

LIST_FIELD_TYPES = (
    models.CharField,
    models.SlugField,
    models.BooleanField,
    models.DecimalField,
    models.EmailField,
    models.FloatField,
    models.IntegerField,
    models.PositiveIntegerField,
    models.URLField,
    models.UUIDField,
    models.DateTimeField,
    models.DateField,
)

FILTER_FIELD_TYPES = (
    models.BooleanField,
    models.DateField,
    models.DateTimeField,
)

SEARCH_FIELD_TYPES = (
    models.CharField,
    models.SlugField,
    models.EmailField,
    models.URLField,
    models.TextField,
    models.GenericIPAddressField,
)

# 定义最适合作为链接的字段名称（按优先级排序）
LINK_PRIORITY_FIELDS = (
    "name",  # 名称
    "title",  # 标题
    "slug",  # 别名
    "code",  # 编码
    "number",  # 编号
    "sn",  # 序列号
    "hostname",  # 主机名
    "username",  # 用户名
    "email",  # 邮箱
)

# 定义最常用于列表显示的字段名称
COMMON_LIST_FIELDS = (
    "username",
    "name",
    "title",
    "slug",
    "code",
    "number",
    "sn",
    "status",
    "type",
    "category",
    "is_active",
    "is_enabled",
    "is_default",
    "created_at",
    "updated_at",
)

# 定义需要排除在列表显示的字段
EXCLUDE_LIST_FIELDS = (
    "password",
    "_password",
)


def get_smart_fieldsets(model, fields):
    """
    智能分析模型字段，生成合理的 fieldsets 分组

    分组规则：
    1. 必填信息（按字符串、外键、多对多排序）
    2. 选填信息（按字符串、外键、多对多排序）
    3. 系统信息（用户、时间、状态字段）
    4. 多对多关系
    """
    required_char_fields = []  # 必填字符串字段
    required_fk_fields = []  # 必填外键字段
    required_m2m_fields = []  # 必填多对多字段

    optional_char_fields = []  # 选填字符串字段
    optional_fk_fields = []  # 选填外键字段
    optional_m2m_fields = []  # 选填多对多字段

    system_fields = []  # 系统信息字段
    m2m_fields = []  # 其他多对多字段

    # 系统相关字段名称
    system_field_names = {
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    }

    for field in fields:
        if not field.editable or field.name == "id":
            continue

        # 系统字段单独处理
        if field.name in system_field_names:
            system_fields.append(field.name)
            continue

        # 处理多对多字段
        if isinstance(field, models.ManyToManyField):
            if field.blank:
                optional_m2m_fields.append(field.name)
            else:
                required_m2m_fields.append(field.name)
            continue

        # 处理外键字段
        if isinstance(field, models.ForeignKey):
            if field.blank:
                optional_fk_fields.append(field.name)
            else:
                required_fk_fields.append(field.name)
            continue

        # 处理字符串和其他字段
        if field.blank:
            optional_char_fields.append(field.name)
        else:
            required_char_fields.append(field.name)

    # 构建 fieldsets
    fieldsets = []

    # 必填信息
    required_fields = required_char_fields + required_fk_fields + required_m2m_fields
    if required_fields:
        fieldsets.append((_("必填信息"), {"fields": required_fields}))

    # 选填信息
    optional_fields = optional_char_fields + optional_fk_fields + optional_m2m_fields
    if optional_fields:
        fieldsets.append((_("选填信息"), {"fields": optional_fields}))

    # 系统信息
    if system_fields:
        fieldsets.append(
            (_("系统信息"), {"fields": system_fields, "classes": ("collapse",)})
        )

    # 多对多关系
    m2m_fields = [
        f.name
        for f in fields
        if isinstance(f, models.ManyToManyField)
        and f.name not in required_m2m_fields
        and f.name not in optional_m2m_fields
    ]
    if m2m_fields:
        fieldsets.append(
            (_("关联信息"), {"fields": m2m_fields, "classes": ("collapse",)})
        )

    return tuple(fieldsets)


if dcrm_models:
    for model in dcrm_models:
        if not admin.site.is_registered(model):
            opts = model._meta
            _fields = [f for f in opts.get_fields() if f.editable == True]

            # 生成列表显示字段 - 优化显示顺序
            list_display = []

            # 1. 首先添加常用标识字段
            for field_name in COMMON_LIST_FIELDS:
                if field_name in [f.name for f in _fields]:
                    list_display.append(field_name)

            # 2. 添加其他合适的字段
            for field in _fields:
                if (
                    isinstance(field, LIST_FIELD_TYPES)
                    and field.name not in list_display
                    and not field.name.startswith("_")
                    and field.name not in EXCLUDE_LIST_FIELDS
                ):  # 排除私有字段
                    list_display.append(field.name)

            # 3. 确保列表不会太长，最多显示 8 个字段
            list_display = list_display[:8]

            # 如果没有找到合适的显示字段，则使用 id
            if not list_display:
                list_display = ["id"]

            # 其他配置保持不变
            list_filter = [
                field.name for field in _fields if isinstance(field, FILTER_FIELD_TYPES)
            ]

            search_fields = [
                field.name for field in _fields if isinstance(field, SEARCH_FIELD_TYPES)
            ]

            filter_horizontal = [
                field.name
                for field in _fields
                if isinstance(field, models.ManyToManyField)
            ]

            fieldsets = get_smart_fieldsets(model, _fields)

            options = {
                "list_display": list_display,
                "list_filter": list_filter if list_filter else [],
                "search_fields": search_fields if search_fields else [],
                "filter_horizontal": filter_horizontal if filter_horizontal else [],
                "per_page": PER_PAGE,
                "fieldsets": fieldsets,
            }

            admin.site.register(model, **options)
