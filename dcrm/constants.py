from datetime import datetime

from django.utils.translation import gettext_lazy as _

# 分页相关
PAGINATE_BY_PARAM = "pre_page"
DEFAULT_PER_PAGE = 20
MAX_PAGE_SIZE = 1000

# 排序相关
ORDERING_PARAM = "ordering"
# 多字段排序分割符
ORDERING_SEP = ","

# 下载相关，下载条目数超过多少将启用流式下载
DOWNLOAD_ENABLED_STREAMING = 500

SELECT2_TRANSLATIONS = {
    x.lower(): x
    for x in [
        "ar",
        "az",
        "bg",
        "ca",
        "cs",
        "da",
        "de",
        "el",
        "en",
        "es",
        "et",
        "eu",
        "fa",
        "fi",
        "fr",
        "gl",
        "he",
        "hi",
        "hr",
        "hu",
        "id",
        "is",
        "it",
        "ja",
        "km",
        "ko",
        "lt",
        "lv",
        "mk",
        "ms",
        "nb",
        "nl",
        "pl",
        "pt-BR",
        "pt",
        "ro",
        "ru",
        "sk",
        "sr-Cyrl",
        "sr",
        "sv",
        "th",
        "tr",
        "uk",
        "vi",
    ]
}
SELECT2_TRANSLATIONS.update({"zh-hans": "zh-CN", "zh-hant": "zh-TW"})


FIELD_TYPE_MAP = {
    # 字符串类型
    "CharField": _("字符串"),
    "TextField": _("文本"),
    "EmailField": _("邮箱"),
    "URLField": _("URL"),
    "UUIDField": _("UUID"),
    "SlugField": _("Slug"),
    "IPAddressField": _("IP地址"),
    "GenericIPAddressField": _("IP地址(cidr格式)"),
    # 数字类型
    "IntegerField": _("整数"),
    "SmallIntegerField": _("小整数"),
    "BigIntegerField": _("大整数"),
    "PositiveIntegerField": _("正整数"),
    "PositiveSmallIntegerField": _("正小整数"),
    "FloatField": _("浮点数"),
    "DecimalField": _("小数"),
    # 日期时间类型
    "DateField": _("日期"),
    "TimeField": _("时间"),
    "DateTimeField": _("日期时间"),
    "DurationField": _("时间间隔"),
    # 布尔类型
    "BooleanField": _("布尔值"),
    "NullBooleanField": _("三态布尔值"),
    # 二进制类型
    "BinaryField": _("二进制"),
    # JSON类型
    "JSONField": _("JSON"),
    # 关系类型
    "ForeignKey": _("外键"),
    "OneToOneField": _("一对一"),
    "ManyToManyField": _("多对多"),
    # 其他类型
    "AutoField": _("自增ID"),
    "BigAutoField": _("大自增ID"),
}


PARSE_DATETIME_FORMATS = [
    "%Y-%m-%d %H:%M",  # 2024-12-21 23:55
    "%Y-%m-%d %H:%M:%S",  # 2024-12-21 23:55:00
    "%Y/%m/%d %H:%M",  # 2024/12/21 23:55
    "%Y/%m/%d %H:%M:%S",  # 2024/12/21 23:55:00
    "%Y年%m月%d日 %H:%M",  # 2024年12月21日 23:55
    "%Y年%m月%d日 %H时%M分",  # 2024年12月21日 23时55分
    "%Y年%m月%d号 %H:%M",  # 2024年12月21号 23:55
    "%Y年%m月%d号 %H时%M分",  # 2024年12月21号 23时55分
    "%Y-%m-%d",  # 2024-12-21
    "%Y/%m/%d",  # 2024/12/21
    "%Y年%m月%d日",  # 2024年12月21日
    "%Y年%m月%d号",  # 2024年12月21号
]

DATE_FORMATS = [
    "%Y-%m-%d",  # 2024-12-21
    "%Y/%m/%d",  # 2024/12/21
    "%Y年%m月%d日",  # 2024年12月21日
]

DATETIME_FORMATS = [
    "%Y-%m-%d %H:%M",  # 2024-12-21 23:55
    "%Y-%m-%d %H:%M:%S",  # 2024-12-21 23:55:00
    "%Y年%m月%d日 %H:%M",  # 2024年12月21日 23:55
    "%Y年%m月%d日 %H时%M分",  # 2024年12月21日 23时55分
]

TIME_FORMATS = [
    "%H:%M",  # 2024-12-21 23:55
    "%H:%M:%S",  # 2024-12-21 23:55:00
    "%H时%M分",  # 2024年12月21日 23时55分
    "%H时%M分%S秒",  # 2024年12月21号 23时55分
]


def datetime_choices(formats=DATE_FORMATS):
    choices = []
    for format in formats:
        choices.append((format, datetime.now().strftime(format)))
    return choices


WEBHOOK_EVENT_TYPES = {}
