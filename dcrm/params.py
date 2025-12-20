from typing import Any, Dict

from django import forms
from django.utils.translation import gettext_lazy as _


class ConfigParam:
    """配置参数类，用于定义配置项的元数据"""

    def __init__(
        self,
        name: str,
        label: str,
        default=None,
        description: str = "",
        field=None,
        field_kwargs=None,
        group: str = "system.general",
        order: int = 0,
        is_readonly: bool = False,
        choices=None,
    ) -> None:
        self.name = name
        self.label = label
        self.description = description
        self.field = field or forms.CharField
        self.field_kwargs = field_kwargs or {}
        self.group = group
        self.order = order
        self.is_readonly = is_readonly
        self.default = default
        self.choices = choices

    def to_dict(self) -> Dict[str, Any]:
        """将配置参数转换为字典"""
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "field": self.field,
            "field_kwargs": self.field_kwargs,
            "group": self.group,
            "order": self.order,
            "is_readonly": self.is_readonly,
            "default": self.default,
            "choices": self.choices,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConfigParam":
        """从字典创建配置参数对象"""
        return cls(
            name=data.get("name", ""),
            label=data.get("label", ""),
            description=data.get("description", ""),
            field=data.get("field", forms.CharField),
            field_kwargs=data.get("field_kwargs", {}),
            group=data.get("group", "system.general"),
            order=data.get("order", 0),
            is_readonly=data.get("is_readonly", False),
            default=data.get("default"),
            choices=data.get("choices"),
        )


# 允许动态配置的设置项
DYNAMIC_SETTINGS = (
    # 邮件配置
    ConfigParam(
        name="EMAIL_HOST",
        label=_("邮件服务器地址"),
        description=_("SMTP服务器地址"),
        field=forms.CharField,
        group="system",
        order=10,
    ),
    ConfigParam(
        name="EMAIL_PORT",
        label=_("邮件服务器端口"),
        description=_("SMTP服务器端口"),
        field=forms.ChoiceField,
        group="system",
        order=20,
        default=25,
        field_kwargs={
            "choices": [(25, "25"), (465, "465"), (587, "587"), (2525, "2525")],
        },
    ),
    ConfigParam(
        name="EMAIL_USE_TLS",
        label=_("使用TLS加密"),
        description=_("是否使用TLS加密连接"),
        field=forms.BooleanField,
        group="system",
        order=30,
        field_kwargs={
            "widget": forms.CheckboxInput(),
        },
        default=False,
    ),
    ConfigParam(
        name="EMAIL_HOST_USER",
        label=_("邮箱账号"),
        description=_("SMTP服务器用户名"),
        field=forms.EmailField,
        group="system",
        order=40,
    ),
    ConfigParam(
        name="EMAIL_HOST_PASSWORD",
        label=_("邮箱密码"),
        description=_("SMTP服务器密码"),
        field=forms.CharField,
        group="system",
        order=50,
        field_kwargs={
            "widget": forms.PasswordInput(render_value=True, attrs={"type": "text"}),
        },
    ),
    ConfigParam(
        name="DEFAULT_FROM_EMAIL",
        label=_("默认发件人"),
        description=_("系统发送邮件时使用的默认发件人地址"),
        field=forms.EmailField,
        group="system",
        order=60,
    ),
    # 用户配置
    ConfigParam(
        name="PAGINATION_PER_PAGE",
        label=_("每页显示记录数"),
        description=_("列表页面每页默认显示的记录数量"),
        field=forms.ChoiceField,
        group="user",
        order=10,
        default=20,
        field_kwargs={
            "choices": [(20, "20"), (25, "25"), (50, "50"), (100, "100")],
        },
    ),
    ConfigParam(
        name="SIDEBAR_COLLAPSE",
        label=_("收起侧边菜单栏"),
        description=_("默认是否收起侧边栏菜单"),
        field=forms.BooleanField,
        group="user",
        order=20,
        default=False,
    ),
    ConfigParam(
        name="PREDICT_DEV_MODEL_COUNT",
        label=_("SN预测设备型号数量"),
        description=_("根据SN预测设备型号时返回的最大数量"),
        field=forms.ChoiceField,
        group="user",
        order=40,
        default=5,
        field_kwargs={
            "choices": [
                (0, "不进行预测"),
                (5, "预测5条结果"),
                (10, "预测10条结果"),
                (100, "不限制"),
            ],
        },
    ),
    ConfigParam(
        name="SHOW_ICON_FOR_INSTANCE",
        label=_("显示图标"),
        description=_("显示制造商/租户图标"),
        field=forms.BooleanField,
        group="user",
        order=50,
        default=True,
        is_readonly=True,
    ),
    ConfigParam(
        name="SIMPLE_FORM_MODE",
        label=_("表单简洁模式"),
        description=_("是否使用简洁的表单显示模式"),
        field=forms.BooleanField,
        group="user",
        order=30,
        default=False,
    ),
    # 数据中心设置
    ConfigParam(
        name="RACK_DEFAULT_HEIGHT",
        label=_("机柜默认高度"),
        description=_("新建机柜的默认高度(U)"),
        field=forms.IntegerField,
        group="datacenter",
        order=10,
        default=45,
        field_kwargs={"max_value": 60, "min_value": 1},
    ),
    ConfigParam(
        name="WARN_RACK_SPACE_USED",
        label=_("机柜空间使用率超过多少显示告警颜色"),
        description=_("机柜空间使用率超过多少显示告警颜色"),
        field=forms.IntegerField,
        group="datacenter",
        order=20,
        default=50,
        field_kwargs={"max_value": 60, "min_value": 40},
    ),
    # 飞书 webhook 设置
    ConfigParam(
        name="FEISHU_WEBHOOK_URL",
        label=_("飞书机器人 URL"),
        description=_("飞书机器人 Webhook URL"),
        field=forms.URLField,
        group="notifications.feishu",
        order=50,
        default="",
    ),
    ConfigParam(
        name="FEISHU_WEBHOOK_SECRET",
        label=_("飞书机器人密钥"),
        description=_("启用签名校验时需填写"),
        field=forms.CharField,
        default="",
        group="notifications.feishu",
        order=60,
    ),
    # 钉钉 webhook 设置
    ConfigParam(
        name="DINGTALK_WEBHOOK_URL",
        label=_("钉钉机器人 URL"),
        description=_("钉钉机器人 Webhook URL"),
        field=forms.URLField,
        group="notifications.dingtalk",
        order=60,
        default="",
    ),
    ConfigParam(
        name="DINGTALK_WEBHOOK_SECRET",
        label=_("钉钉机器人密钥"),
        description=_("启用签名校验时需填写"),
        field=forms.CharField,
        group="notifications.dingtalk",
        order=70,
        default="",
    ),
    # 企业微信 webhook 设置
    ConfigParam(
        name="WECOM_WEBHOOK_URL",
        label=_("企业微信机器人 URL"),
        description=_("企业微信机器人 Webhook URL"),
        field=forms.URLField,
        group="notifications.wecom",
        order=70,
        default="",
    ),
    ConfigParam(
        name="WECOM_MESSAGE_TYPE",
        label=_("企业微信消息类型"),
        description=_("企业微信消息类型"),
        field=forms.ChoiceField,
        group="notifications.wecom",
        order=80,
        default="text",
        field_kwargs={
            "choices": [
                ("text", _("文本")),
                ("markdown", _("Markdown")),
            ],
        },
    ),
    # 百度 OCR 设置
    ConfigParam(
        name="BDOCR_APPID",
        label=_("百度OCR APPID"),
        description=_("百度OCR APPID"),
        field=forms.CharField,
        group="datacenter",
        order=30,
    ),
    ConfigParam(
        name="BDOCR_API_KEY",
        label=_("百度OCR API KEY"),
        description=_("百度OCR API KEY"),
        field=forms.CharField,
        group="datacenter",
        order=40,
        field_kwargs={
            "widget": forms.PasswordInput(render_value=True, attrs={"type": "text"}),
        },
    ),
    ConfigParam(
        name="BDOCR_SECERT_KEY",
        label=_("百度OCR SECERT KEY"),
        description=_("百度OCR SECERT KEY"),
        field=forms.CharField,
        group="datacenter",
        order=50,
        field_kwargs={
            "widget": forms.PasswordInput(render_value=True, attrs={"type": "text"}),
        },
    ),
)

# 配置组定义
CONFIG_GROUPS = {
    "user": {
        "name": _("用户设置"),
        "description": _("用户界面和偏好设置"),
        "order": 10,
    },
    "datacenter": {
        "name": _("数据中心"),
        "description": _("数据中心相关设置"),
        "order": 20,
    },
    "system": {
        "name": _("邮箱设置"),
        "description": _("系统邮箱相关配置"),
        "order": 40,
    },
    # "notifications": {
    #     "name": _("通知设置"),
    #     "description": _("通知相关设置"),
    #     "order": 50,
    #     "children": {
    #         "feishu": {
    #             "name": _("飞书机器人"),
    #             "description": _("飞书机器人相关设置"),
    #             "order": 10,
    #         },
    #         "dingtalk": {
    #             "name": _("钉钉机器人"),
    #             "description": _("钉钉机器人相关设置"),
    #             "order": 20,
    #         },
    #         "wecom": {
    #             "name": _("企业微信机器人"),
    #             "description": _("企业微信机器人相关设置"),
    #             "order": 30,
    #         },
    #     },
    # },
}

# 将元组转换为字典，方便通过配置名称查找
DYNAMIC_SETTINGS_DICT = {param.name: param for param in DYNAMIC_SETTINGS}


def is_dynamic_setting(key: str) -> bool:
    """检查是否为允许动态配置的设置项"""
    return key in DYNAMIC_SETTINGS_DICT


def get_setting_meta(key: str) -> Dict[str, Any]:
    """获取设置项的元数据"""
    if key in DYNAMIC_SETTINGS_DICT:
        return DYNAMIC_SETTINGS_DICT[key].to_dict()
    return {}
