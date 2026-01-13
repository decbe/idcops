import random
from ipaddress import IPv4Address, IPv6Address, ip_address

from django.db.models import IntegerChoices, TextChoices
from django.utils.translation import gettext_lazy as _

__all__ = [
    "ColorChoices",
    "CustomFieldTypeChoices",
    "CustomFieldVisibilityChoices",
    "ActionColorChoices",
    "DurationChoices",
    "WebhookHttpMethodChoices",
    "ChangeActionChoices",
    "RackTypeChoices",
    "RackStatusChoices",
    "PDUSlotChoices",
    "DeviceMetaChoices",
    "DeviceStatusChoices",
    "DeviceTypeChoices",
    "DevicePortTypeChoices",
    "DevicePortStatusChoices",
    "SubnetStatusChoices",
    "VLANStatusChoices",
    "IPAddressTypeChoices",
    "NodePortTypeChoices",
    "PatchCordStatusChoices",
    "DeviceHostStatusChoices",
    "DeviceHostGroupChoices",
    "DeviceHostAuthTypeChoices",
    "PortTypeChoices",
    "NodeTypeChoices",
    "TenantTypeChoices",
    "SNMPVersionChoices",
    "SNMPAuthProtocolChoices",
    "SNMPPrivacyProtocolChoices",
    "ItemInstanceStatus",
    "ItemInstanceHistoryOperationType",
]


#
# 颜色映射
#
class ColorChoices(TextChoices):
    RED = "red", _("红色")
    ORANGE = "orange", _("橙色")
    YELLOW = "yellow", _("黄色")
    GREEN = "green", _("绿色")
    BLUE = "blue", _("蓝色")
    BLACK = "black", _("黑色")
    AQUA = "aqua", _("水蓝色")
    GRAY = "gray", _("灰色")
    GRAY_LIGHT = "gray-light", _("浅灰色")
    NAVY = "navy", _("海军蓝")
    TEAL = "teal", _("青色")
    OLIVE = "olive", _("橄榄色")
    LIME = "lime", _("青柠色")
    FUCHSIA = "fuchsia", _("紫红色")
    PURPLE = "purple", _("紫色")
    MAROON = "maroon", _("栗色")
    # WHITE = "white", _('白色')
    LIGHT_BLUE = "light-blue", _("浅蓝色")

    @staticmethod
    def get_default_color():
        value = random.sample([color[0] for color in ColorChoices.choices], k=1)[0]
        return ColorChoices(value)

    @classmethod
    def get_color(cls, value, tag="label"):
        """获取颜色样式
        :param value: 颜色值
        :param tag: 标签类型，可选值为 'label', 'text' 或 'bg'
        :return: 对应的 CSS 类名
        """
        match tag:
            case "label":
                return cls(value)
            case "text":
                return f"text-{cls(value).value}"
            case "bg":
                return f"bg-{cls(value).value}"
            case _:
                return cls(value).value

    @staticmethod
    def to_hex_color(value):
        color_maps = {
            "gray": "#d2d6de",
            "gray-light": "#f7f7f7",
            "black": "#111",
            "red": "#dd4b39",
            "yellow": "#f39c12",
            "aqua": "#00c0ef",
            "blue": "#0073b7",
            "light-blue": "#3c8dbc",
            "green": "#00a65a",
            "navy": "#001F3F",
            "teal": "#39CCCC",
            "olive": "#3D9970",
            "lime": "#01FF70",
            "orange": "#FF851B",
            "fuchsia": "#F012BE",
            "purple": "#605ca8",
            "maroon": "#D81B60",
        }
        return color_maps.get(value)


#
# CustomFields 自定义字段类型
#
class CustomFieldTypeChoices(TextChoices):
    TYPE_TEXT = "text", _("文本")
    TYPE_LONGTEXT = "longtext", _("长文本")
    TYPE_INTEGER = "integer", _("整数")
    TYPE_DECIMAL = "decimal", _("小数")
    TYPE_BOOLEAN = "boolean", _("布尔值(true/false)")
    TYPE_DATE = "date", _("日期")
    TYPE_DATETIME = "datetime", _("日期时间")
    TYPE_URL = "url", _("URL")
    TYPE_JSON = "json", _("JSON")
    TYPE_SELECT = "select", _("单选框")
    TYPE_MULTISELECT = "multiselect", _("多选框")
    TYPE_OBJECT = "object", _("单对象")
    TYPE_MULTIOBJECT = "multiobject", _("多对象")


class CustomFieldVisibilityChoices(TextChoices):
    ONLY_DETAIL = "only_detail", _("仅详情可见")
    LIST_AND_DETAIL = "list_and_detail", _("列表和详情可见")
    HIDDEN = "hidden", _("隐藏")


#
# Action color choices
#
class ActionColorChoices(TextChoices):
    DEFAULT = "default", _("默认")
    PRIMARY = "primary", _("主要")
    SECONDARY = "secondary", _("次要")
    DANGER = "danger", _("危险")
    INFO = "info", _("信息")
    WARNING = "warning", _("警告")
    SUCCESS = "success", _("成功")


#
# Duration choices
#
class DurationChoices(IntegerChoices):
    HOURLY = 60, _("每小时")
    TWELVE_HOURS = 720, _("12小时")
    DAILY = 1440, _("每天")
    WEEKLY = 10080, _("每周")
    THIRTY_DAYS = 43200, _("30天")


#
# Webhooks
#
class WebhookHttpMethodChoices(TextChoices):
    METHOD_GET = "GET", _("GET")
    METHOD_POST = "POST", _("POST")
    METHOD_PUT = "PUT", _("PUT")
    METHOD_PATCH = "PATCH", _("PATCH")
    METHOD_DELETE = "DELETE", _("DELETE")


#
# Webhook Request Content Type
#
class WebhookRequestContentTypeChoices(TextChoices):
    JSON = "application/json", _("application/json")
    FORM_DATA = "application/x-www-form-urlencoded", _(
        "application/x-www-form-urlencoded"
    )


#
# Webhook Event Types
#
class WebhookEventTypes(TextChoices):
    EVENT_CREATED = "created", _("创建")
    EVENT_UPDATED = "updated", _("更新")
    EVENT_DELETED = "deleted", _("删除")


#
# Staging
#
class ChangeActionChoices(TextChoices):
    CREATE = "create", _("创建")
    UPDATE = "update", _("更新")
    DELETE = "delete", _("删除")
    BULK_CREATE = "bulk_create", _("批量创建")
    BULK_UPDATE = "bulk_update", _("批量更新")
    ACTION_LOGIN = "login", _("登录")
    ACTION_LOGOUT = "logout", _("退出登录")

    @classmethod
    def get_color(cls, value) -> str | None:
        """获取设备状态颜色
        :param value: 设备状态
        :return: 颜色值或设备状态
        """
        colors = {
            cls.CREATE: "olive",
            cls.UPDATE: "yellow",
            cls.DELETE: "red",
            cls.ACTION_LOGIN: "light-blue",
            cls.ACTION_LOGOUT: "gray",
        }
        return colors.get(value)


"""

.bg-red,.bg-yellow,.bg-aqua,.bg-blue,.bg-light-blue,.bg-green,.bg-navy,.bg-teal,.bg-olive,.bg-lime,.bg-orange,.bg-fuchsia,.bg-purple,.bg-maroon,.bg-black,

.bg-red-active,.bg-yellow-active,.bg-aqua-active,.bg-blue-active,.bg-light-blue-active,.bg-green-active,.bg-navy-active,.bg-teal-active,.bg-olive-active,.bg-lime-active,.bg-orange-active,.bg-fuchsia-active,.bg-purple-active,.bg-maroon-active,.bg-black-active,.callout.callout-danger,.callout.callout-warning,.callout.callout-info,.callout.callout-success,.alert-success,.alert-danger,.alert-error,.alert-warning,.alert-info,

.label-danger,.label-info,.label-warning,.label-primary,.label-success,

.modal-primary 

.modal-body,.modal-primary .modal-header,.modal-primary .modal-footer,.modal-warning .modal-body,.modal-warning .modal-header,.modal-warning .modal-footer,.modal-info .modal-body,.modal-info .modal-header,.modal-info .modal-footer,.modal-success .modal-body,.modal-success .modal-header,.modal-success .modal-footer,.modal-danger .modal-body,.modal-danger .modal-header,.modal-danger .modal-footer {
    color: #fff !important
}

.bg-gray {
    color: #000;
    background-color: #d2d6de !important
}

.bg-gray-light {
    background-color: #f7f7f7
}

.bg-black {
    background-color: #111 !important
}

.bg-red,.callout.callout-danger,.alert-danger,.alert-error,.label-danger,.modal-danger .modal-body {
    background-color: #dd4b39 !important
}

.bg-yellow,.callout.callout-warning,.alert-warning,.label-warning,.modal-warning .modal-body {
    background-color: #f39c12 !important
}

.bg-aqua,.callout.callout-info,.alert-info,.label-info,.modal-info .modal-body {
    background-color: #00c0ef !important
}

.bg-blue {
    background-color: #0073b7 !important
}

.bg-light-blue,.label-primary,.modal-primary .modal-body {
    background-color: #3c8dbc !important
}

.bg-green,.callout.callout-success,.alert-success,.label-success,.modal-success .modal-body {
    background-color: #00a65a !important
}

.bg-navy {
    background-color: #001F3F !important
}

.bg-teal {
    background-color: #39CCCC !important
}

.bg-olive {
    background-color: #3D9970 !important
}

.bg-lime {
    background-color: #01FF70 !important
}

.bg-orange {
    background-color: #FF851B !important
}

.bg-fuchsia {
    background-color: #F012BE !important
}

.bg-purple {
    background-color: #605ca8 !important
}

.bg-maroon {
    background-color: #D81B60 !important
}

.bg-gray-active {
    color: #000;
    background-color: #b5bbc8 !important
}

.bg-black-active {
    background-color: #000 !important
}

.bg-red-active,.modal-danger .modal-header,.modal-danger .modal-footer {
    background-color: #d33724 !important
}

.bg-yellow-active,.modal-warning .modal-header,.modal-warning .modal-footer {
    background-color: #db8b0b !important
}

.bg-aqua-active,.modal-info .modal-header,.modal-info .modal-footer {
    background-color: #00a7d0 !important
}

.bg-blue-active {
    background-color: #005384 !important
}

.bg-light-blue-active,.modal-primary .modal-header,.modal-primary .modal-footer {
    background-color: #357ca5 !important
}

.bg-green-active,.modal-success .modal-header,.modal-success .modal-footer {
    background-color: #008d4c !important
}

.bg-navy-active {
    background-color: #001a35 !important
}

.bg-teal-active {
    background-color: #30bbbb !important
}

.bg-olive-active {
    background-color: #368763 !important
}

.bg-lime-active {
    background-color: #00e765 !important
}

.bg-orange-active {
    background-color: #ff7701 !important
}

.bg-fuchsia-active {
    background-color: #db0ead !important
}

.bg-purple-active {
    background-color: #555299 !important
}

.bg-maroon-active {
    background-color: #ca195a !important
}

[class^="bg-"].disabled {
    opacity: .65;
    filter: alpha(opacity=65)
}

.text-red {
    color: #dd4b39 !important
}

.text-yellow {
    color: #f39c12 !important
}

.text-aqua {
    color: #00c0ef !important
}

.text-blue {
    color: #0073b7 !important
}

.text-black {
    color: #111 !important
}

.text-light-blue {
    color: #3c8dbc !important
}

.text-green {
    color: #00a65a !important
}

.text-gray {
    color: #d2d6de !important
}

.text-navy {
    color: #001F3F !important
}

.text-teal {
    color: #39CCCC !important
}

.text-olive {
    color: #3D9970 !important
}

.text-lime {
    color: #01FF70 !important
}

.text-orange {
    color: #FF851B !important
}

.text-fuchsia {
    color: #F012BE !important
}

.text-purple {
    color: #605ca8 !important
}

.text-maroon {
    color: #D81B60 !important
}

.link-muted {
    color: #7a869d
}

.link-muted:hover,.link-muted:focus {
    color: #606c84
}

.link-black {
    color: #666
}

.link-black:hover,.link-black:focus {
    color: #999
}

"""


#
# Rack type choices
#
class RackTypeChoices(TextChoices):
    """机柜类型"""

    SHARED = "shared", _("散U")  # 共享机柜，共享机柜可以共享给多个用户使用
    EXCLUSIVE = "exclusive", _(
        "整柜"
    )  # 独享机柜, 独享机柜只能分配给一个用户使用, 默认值
    PATCH_PANEL = "patch_panel", _(
        "配线柜"
    )  # 跳线面板机柜，跳线面板机柜可以连接跳线，ODF,EDF等
    # INTERNAL = "internal", _("内部机柜")  # 内部机柜，内部机柜只能内部使用
    UNSPECIFIED = "unspecified", _("未指定")  # 未指定

    @classmethod
    def get_color(cls, value):
        """.bg-red,.bg-yellow,.bg-aqua,.bg-blue,.bg-light-blue,
        .bg-green,.bg-navy,.bg-teal,.bg-olive,.bg-lime,
        .bg-orange,.bg-fuchsia,.bg-purple,.bg-maroon,.bg-black,
        """
        """获取颜色"""
        colors = {
            cls.SHARED: "fuchsia",
            cls.EXCLUSIVE: "light-blue",
            cls.PATCH_PANEL: "yellow",
            # cls.INTERNAL: "navy",
            cls.UNSPECIFIED: "gray",
        }
        return colors.get(value)


#
# Rack Status
#
class RackStatusChoices(TextChoices):
    """机柜状态
    已预留：预留给可能进行机柜扩容的某一个客户（机柜实质是空闲状态，并且未被占用）
    已采购：已经向数据中心运营商采购的机柜（针对第三方IDC公司）
    预分配：某一客户已经确认了扩容，预分配给该客户（与客户有实质性业务来往时发生的状态）
    使用中：某一客户正在使用中的机柜
    已释放：某一客户已经退租，并且已清空设备的机柜状态
    被占用：这个机柜被其他IDC公司或运营商占用（属于不能采购到的一种）
    空闲：可以采购，预留，分配给客户的机柜状态
    mark：
        按客户类型分:
            1. 第三方配线柜，可以上架第三方配线设备，并且变更不参与业务报表的统计
            2. 客户类型如果是内部客户，
        1. 预留和预分配是差不多的，但是预留是指预留给可能进行机柜扩容的某一个客户，预分配是指某一客户已经确认了扩容
        2. [已采购，预分配，使用中] 这三种状态是允许直接上架设备的（运营商配线柜除外）|,
        3. 即：机柜类型式配线柜，那么可以直接添加设备，并且，客户类型为第三方的时候，配线柜的变更不参与业务报表的统计
        4. 指定为 散U 类型的机柜可以直接上架，并参与业务报表的统计
    """

    PURCHASED = "purchased", _("已采购")  # 已采购
    RESERVED = "reserved", _("已预留")  # 已预留
    PRE_ALLOCATION = "pre_allocation", _("预分配")  # 预分配
    USED = "used", _("使用中")  # 使用中
    RELEASED = "released", _("已释放")  # 已释放
    OCCUPIED = "occupied", _("被占用")  # 被占用
    EMPTY = "empty", _("空闲")  # 空闲 default value

    @classmethod
    def get_color(cls, value):
        """.bg-red,.bg-yellow,.bg-aqua,.bg-blue,.bg-light-blue,
        .bg-green,.bg-navy,.bg-teal,.bg-olive,.bg-lime,
        .bg-orange,.bg-fuchsia,.bg-purple,.bg-maroon,.bg-black,
        """
        """获取颜色"""
        colors = {
            cls.PURCHASED: "aqua",
            cls.RESERVED: "yellow",
            cls.USED: "red",
            cls.PRE_ALLOCATION: "lime",
            cls.RELEASED: "olive",
            cls.OCCUPIED: "purple",
            cls.EMPTY: "gray",
        }
        return colors.get(value)


ALLOWED_MOUNT_STATUS = [
    RackStatusChoices.PRE_ALLOCATION,  # 预分配
    RackStatusChoices.USED,  # 使用中
    RackStatusChoices.RESERVED,  # 已预留
    RackStatusChoices.PURCHASED,  # 已采购
]


class PDUSlotChoices(TextChoices):
    """PDU槽位电流"""

    A10 = "10A", _("10A")
    A16 = "16A", _("16A")


class RackPDUStatusChoices(TextChoices):
    USED = "used", _("使用中")
    EMPTY = "empty", _("空闲")  # 空闲
    FAULT = "fault", _("故障")  # 标记PDU不可用，

    @classmethod
    def get_color(cls, value):
        """.bg-red,.bg-yellow,.bg-aqua,.bg-blue,.bg-light-blue,
        .bg-green,.bg-navy,.bg-teal,.bg-olive,.bg-lime,
        .bg-orange,.bg-fuchsia,.bg-purple,.bg-maroon,.bg-black,
        """
        """获取颜色"""
        colors = {
            cls.USED: "olive",
            cls.FAULT: "red",
            cls.EMPTY: "gray",
        }
        return colors.get(value)


#
# DeviceMeta 设备元数据字段选项
#
class DeviceMetaChoices(TextChoices):
    """设备元数据字段选项"""

    # 状态
    STATUS = "status", _("状态")  # 已上架、已下架、已迁移
    # 角色
    ROLE = "role", _("角色")  # 服务器、存储、网络设备等
    # 环境（主要兼容小型自有机房）
    ENVIRONMENT = "environment", _("环境")  # 生产、测试、开发等
    # 生命周期（主要兼容小型自有机房）
    LIFECYCLE = "lifecycle", _("生命周期")  # 新建、运行中、待报废等


#
# DeviceStatus 设备状态选项
#
class DeviceStatusChoices(TextChoices):
    """设备状态"""

    MOUNTED = "mounted", _("已上架")
    MIGRATED = "migrated", _("已迁移")
    UNMOUNTED = "unmounted", _("已下架")
    DRAFT = "draft", _("草稿")  # 草稿，扫SN条码，批量上下架时使用

    @classmethod
    def get_color(cls, value):
        """获取设备状态颜色
        :param value: 设备状态
        :return: 颜色值或设备状态
        """
        colors = {
            cls.MOUNTED: "olive",
            cls.UNMOUNTED: "red",
            cls.MIGRATED: "yellow",
            cls.DRAFT: "blue",
        }
        return colors.get(value)


#
# DeviceTypeChoices 设备型号端口类型选项
#
class DeviceTypeChoices(TextChoices):
    """设备型号类型"""

    SERVER = "server", _("服务器")
    SWITCH = "switch", _("交换机")
    ROUTER = "router", _("路由器")
    STORAGE = "storage", _("存储")
    FIREWALL = "firewall", _("防火墙")
    NETWORK = "network", _("网络设备")
    PATCH_PANEL = "patch_panel", _("配线架")
    CABLE_MANAGER = "cable_manager", _("理线架")
    UPS = "ups", _("UPS")
    PDU = "pdu", _("PDU")
    OTHER = "other", _("其他")

    @classmethod
    def get_icon(cls, value):
        icons = {
            "cable_manager": "fa fa-cable",
            "ups": "fa fa-battery-full",
            "pdu": "fa fa-plug",
            "other": "fa fa-question",
        }
        return icons.get(value, "fa fa-question")

    @classmethod
    def get_symbol(cls, value):
        """获取设备类型对应的图标"""
        from django.templatetags.static import static

        symbols = {
            cls.SERVER: static("icons/server.svg"),
            cls.SWITCH: static("icons/switch.svg"),
            cls.ROUTER: static("icons/router.svg"),
            cls.STORAGE: static("icons/nas.svg"),
            cls.FIREWALL: static("icons/firewall.svg"),
            cls.NETWORK: static("icons/server-network.svg"),
            cls.PATCH_PANEL: static("icons/solar-panel-large.svg"),
            cls.CABLE_MANAGER: static("icons/artboard.svg"),
            cls.UPS: static("icons/ups.svg"),
            cls.PDU: static("icons/pdu.svg"),
            cls.OTHER: static("icons/other.svg"),
            "rack": static("icons/rack.svg"),
        }
        return symbols.get(value, static("icons/other.svg"))  # 默认返回 other.svg


#
# DevicePortTypeChoices 设备端口类型选项
#
class DevicePortTypeChoices(TextChoices):
    """设备端口类型选项"""

    ETHERNET = "ethernet", _("以太网")
    FIBER = "fiber", _("光纤")
    CONSOLE = "console", _("Console")
    USB = "usb", _("USB口")
    MGMT = "mgmt", _("管理口")
    POWER = "power", _("电源口")
    OTHER = "other", _("其他端口")


NETWORK_PORT_TYPES = [
    DevicePortTypeChoices.ETHERNET,
    DevicePortTypeChoices.FIBER,
    DevicePortTypeChoices.CONSOLE,
    DevicePortTypeChoices.USB,
    DevicePortTypeChoices.MGMT,
]


#
# DevicePortStatusChoices 设备端口状态选项
#
class DevicePortStatusChoices(TextChoices):
    """设备端口状态选项"""

    CONNECTED = "connected", _("已连接")
    DISCONNECTED = "disconnected", _("未连接")

    @classmethod
    def get_color(cls, value):
        """获取设备端口状态颜色"""
        colors = {
            "connected": "olive",
            "disconnected": "red",
        }
        return colors.get(value)


#
# SubnetStatusChoices 子网状态选项
#
class SubnetStatusChoices(TextChoices):
    """子网状态选项"""

    RESERVED = "reserved", _("已预留")  # 已预留，可以预留分配给某个租户
    ALLOCATED = "allocated", _("已分配")  # 已分配给某个租户
    RECYCLED = "recycled", _("已回收")  # 已回收
    EMPTY = "empty", _("空闲")  # 空闲

    @classmethod
    def get_color(cls, value):
        """获取子网状态颜色"""
        colors = {
            cls.RESERVED: "yellow",
            cls.ALLOCATED: "green",
            cls.RECYCLED: "red",
            cls.EMPTY: "gray",
        }
        return colors.get(value)


#
# VLAN状态选项
#
class VLANStatusChoices(TextChoices):
    """VLAN状态选项"""

    AVAILABLE = "available", _("可用")
    RESERVED = "reserved", _("已预留")
    ALLOCATED = "allocated", _("已分配")
    DEPRECATED = "deprecated", _("已弃用")


#
# IP 地址类型
#
class IPAddressTypeChoices(TextChoices):
    """IP地址类型选项"""

    IPv4 = "ipv4", _("IPv4")
    IPv6 = "ipv6", _("IPv6")

    @classmethod
    def detect_ip_type(cls, address):
        """自动检测IP地址类型"""
        try:
            ip = ip_address(address)
            if isinstance(ip, IPv4Address):
                return cls.IPv4
            elif isinstance(ip, IPv6Address):
                return cls.IPv6
        except ValueError:
            return None
        return None


#
# IP 地址状态
#
class IPAddressStatusChoices(TextChoices):
    """IP地址状态"""

    RESERVED = "reserved", _("已保留")  # 可以预留分配给某个租户
    ALLOCATED = "allocated", _("已分配")  # 已分配给某个租户
    USED = "used", _("使用中")  # 已分配给某个租户，并且已使用
    DEPRECATED = "deprecated", _("已弃用")
    EMPTY = "empty", _("空闲")

    @classmethod
    def get_color(cls, value):
        """获取IP地址状态颜色"""
        colors = {
            cls.RESERVED: "yellow",
            cls.ALLOCATED: "blue",
            cls.USED: "green",
            cls.DEPRECATED: "red",
            cls.EMPTY: "gray",
        }
        return colors.get(value)


#
# SNMPVersionChoices SNMP版本
#
class SNMPVersionChoices(TextChoices):
    """SNMP版本"""

    V1 = "v1", _("V1")
    V2C = "v2c", _("V2C")
    V3 = "v3", _("V3")


#
# SNMPAuthProtocolChoices SNMP认证协议
#
class SNMPAuthProtocolChoices(TextChoices):
    """SNMP认证协议"""

    MD5 = "md5", _("MD5")
    SHA = "sha", _("SHA")
    SHA224 = "sha224", _("SHA224")
    SHA256 = "sha256", _("SHA256")
    SHA384 = "sha384", _("SHA384")
    SHA512 = "sha512", _("SHA512")


#
# SNMPPrivacyProtocolChoices SNMP加密协议
#
class SNMPPrivacyProtocolChoices(TextChoices):
    """SNMP加密协议"""

    DES = "des", _("DES")
    AES = "aes", _("AES")
    AES192 = "aes192", _("AES192")
    AES256 = "aes256", _("AES256")
    AES192C = "aes192c", _("AES192C")
    AES256C = "aes256c", _("AES256C")
    # NO_AUTH = "no_auth", _("无认证")


#
# ItemInstanceStatus 库存物品状态
#
class ItemInstanceStatus(TextChoices):
    IN_STOCK = "in_stock", _("在库")
    USED = "used", _("已使用")
    BORROWING = "borrowing", _("借用中")
    SCRAPPED = "scrapped", _("已报废")
    LOST = "lost", _("丢失")

    @classmethod
    def get_color(cls, value):
        """获取状态的颜色"""
        color_map = {
            cls.IN_STOCK: "green",
            cls.USED: "red",
            cls.BORROWING: "yellow",
            cls.SCRAPPED: "gray",
            cls.LOST: "gray-light",
        }
        return color_map.get(value)


class ItemInstanceHistoryOperationType(TextChoices):
    """库存历史操作类型"""

    CHECK_IN = "check_in", _("入库")
    CHECK_OUT = "check_out", _("出库")
    BORROW = "borrow", _("借用")
    RETURN = "return", _("归还")
    TRANSFER = "transfer", _("转移")
    SCRAP = "scrap", _("报废")
    STATUS_CHANGE = "status_change", _("状态变更")

    @classmethod
    def get_color(cls, value):
        """获取操作类型的颜色"""
        color_map = {
            cls.CHECK_IN: "green",
            cls.CHECK_OUT: "yellow",
            cls.BORROW: "yellow",
            cls.RETURN: "green",
            cls.TRANSFER: "yellow",
            cls.SCRAP: "red",
            cls.STATUS_CHANGE: "gray",
        }
        return color_map.get(value)


#
# ProxyTypeChoices 代理类型
#
class ProxyTypeChoices(TextChoices):
    """代理类型"""

    HTTP = "http", _("HTTP")
    HTTPS = "https", _("HTTPS")
    SOCKS4 = "socks4", _("SOCKS4")
    SOCKS5 = "socks5", _("SOCKS5")


#
# Node Port Type 节点端口类型
#
class NodePortTypeChoices(TextChoices):
    """节点端口类型"""

    RJ45 = "rj45", _("RJ45")  # 双绞线，默认值
    SFP = "sfp", _("SFP")  # 小型可插拔(GBIC)
    SFP_PLUS = "sfp_plus", _("SFP+")  # 增强型小型可插拔(SFP+)
    QSFP = "qsfp", _("QSFP")  # 四倍小型可插拔(QSFP)
    QSFP_PLUS = "qsfp_plus", _("QSFP+")  # 增强型四倍小型可插拔(QSFP+)
    USB = "usb", _("USB")
    OTHER = "other", _("其他")


#
# PatchCordStatusChoices 跳线状态
#
class PatchCordStatusChoices(TextChoices):
    """跳线状态"""

    PLANNED = "planned", _("计划中")  # 新增跳线，但是未实际使用，可能节点不完整
    ACTIVE = "active", _("使用中")  # 新增跳线正在使用中
    PRE_RECYCLE = "pre_recycle", _("待回收")  # 连接的设备已迁移或下架
    RECYCLED = "recycled", _("已回收")  # 线缆已完全回收并清理

    @classmethod
    def get_color(cls, value):
        """.bg-red,.bg-yellow,.bg-aqua,.bg-blue,.bg-light-blue,
        .bg-green,.bg-navy,.bg-teal,.bg-olive,.bg-lime,
        .bg-orange,.bg-fuchsia,.bg-purple,.bg-maroon,.bg-black,
        """
        """获取颜色"""
        colors = {
            cls.ACTIVE: "green",
            cls.PRE_RECYCLE: "red",
            cls.PLANNED: "yellow",
            cls.RECYCLED: "gray",
        }
        return colors.get(value)


class PatchCordCableTypeChoices(TextChoices):
    RJ45 = "rj45", _("网线")
    FIBER = "fiber", _("光纤")
    RFMIXIN = "rfmixin", _("混合")
    USB = "usb", _("USB")
    OTHER = "other", _("其他")


#
# DeviceHostStatusChoices 主机状态
#
class DeviceHostStatusChoices(TextChoices):
    """主机状态"""

    ONLINE = "online", _("在线")
    OFFLINE = "offline", _("离线")
    FAULT = "fault", _("故障")
    MAINTENANCE = "maintenance", _("维护中")
    UNKNOWN = "unknown", _("未知")

    @classmethod
    def get_color(cls, value):
        """获取主机状态颜色"""
        colors = {
            "online": "success",
            "offline": "danger",
            "unknown": "warning",
            "maintenance": "info",
        }
        return colors.get(value, "default")


#
# DeviceHostGroupChoices 主机分组
#
class DeviceHostGroupChoices(TextChoices):
    """主机分组"""

    TEST = "test", _("测试")
    PRODUCTION = "production", _("生产")
    DEVELOPMENT = "development", _("开发")
    INTERNAL = "internal", _("内部")
    OTHER = "other", _("其他")


#
# DeviceHostAuthTypeChoices 主机认证方式
#
class DeviceHostAuthTypeChoices(TextChoices):
    """主机认证方式"""

    PASSWORD = "password", _("密码认证")
    SSH_KEY = "ssh_key", _("SSH密钥")


#
# PortTypeChoices 跳线端口类型
#
class PortTypeChoices(TextChoices):
    """跳线端口类型"""

    RJ45 = "rj45", _("RJ45")
    SFP = "sfp", _("SFP")
    SFP_PLUS = "sfp_plus", _("SFP+")
    QSFP = "qsfp", _("QSFP")
    QSFP_PLUS = "qsfp_plus", _("QSFP+")
    USB = "usb", _("USB")
    OTHER = "other", _("其他")


#
# NodeTypeChoices 跳线节点类型
#
class NodeTypeChoices(TextChoices):
    """跳线节点类型"""

    DEVICE = "device", _("设备")
    PATCH_PANEL = "patch_panel", _("配线架")


#
# TenantTypeChoices 租户类型
#
class TenantTypeChoices(TextChoices):
    """租户类型"""

    EXTERNAL = "external", _("外部整租")
    EXTERNAL_SHARED = "external_shared", _("外部散租")
    INTERNAL = "internal", _("内部租户")
    PROVIDER = "provider", _("运营商")
    THIRD_PARTY = "third_party", _("第三方")
