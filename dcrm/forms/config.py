from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from dcrm.params import ConfigParam


class ConfigParamForm(forms.Form):
    """
    批量配置表单，用于一次性编辑多个配置项。

    此表单动态生成多个字段，每个字段对应一个配置项，并提供批量验证和保存功能。
    """

    def __init__(self, params=None, user=None, *args, **kwargs):
        """
        初始化批量配置表单

        Args:
            params: 配置参数列表，每个元素是一个ConfigParam对象
            *args: 传递给表单的额外参数
            **kwargs: 传递给表单的额外关键字参数
        """
        super().__init__(*args, **kwargs)
        self.config_params = params or []
        self.user = user
        # 为每个配置参数创建字段
        for param in self.config_params:
            field_class = param.field
            field_kwargs = param.field_kwargs.copy()

            # 设置通用字段属性
            field_kwargs.update(
                {
                    "label": param.label,
                    "help_text": param.description,
                    "required": False,
                    "disabled": param.is_readonly,
                }
            )

            # 添加字段到表单，使用参数名作为字段名
            self.fields[param.name] = field_class(**field_kwargs)

    def get_fields_by_group(self):
        """
        按照分组返回字段，方便在模板中渲染分组表单

        Returns:
            dict: 以组名为键，字段列表为值的字典
        """
        groups = {}

        for param in self.config_params:
            group_key = param.group
            if group_key not in groups:
                groups[group_key] = []
            field = self.fields[param.name]
            is_boolean = isinstance(field, forms.BooleanField) or isinstance(
                field.widget, forms.CheckboxInput
            )
            is_password = isinstance(field.widget, forms.PasswordInput)
            field_attrs = {"id": f"id_{param.name}"}
            disabled = not self.get_perm(self.user, param.group) or param.is_readonly
            field_attrs["disabled"] = disabled
            default_class = {
                "form-control",
            }
            if not is_boolean:
                field_attrs["autocomplete"] = "off"
                field_attrs["disabled"] = disabled
            if is_password:
                default_class.add("password")
                field_attrs["autocomplete"] = "new-password"
            current_value = self.initial.get(param.name, param.default)
            if current_value:
                default_class.add("has-value")
            field_attrs["class"] = " ".join(default_class)

            # 特殊处理布尔字段
            if is_boolean:
                # 自定义渲染布尔字段的HTML
                checked = "checked" if current_value else ""
                _disabled = "disabled" if disabled or param.is_readonly else ""
                field_html = f'<input type="checkbox" name="{param.name}" id="id_{param.name}" {checked} {_disabled}>'
            else:
                field_html = field.widget.render(
                    param.name, current_value, attrs=field_attrs
                )

            groups[group_key].append(
                {
                    "name": param.name,
                    "field": field_html,
                    "param": param,
                    "value": current_value,
                    "errors": self.errors.get(param.name, []),
                    "help_text": field.help_text,
                    "label": field.label,
                    "is_boolean": is_boolean,
                }
            )

        # 按照组内的order排序
        for group_key, fields in groups.items():
            groups[group_key] = sorted(fields, key=lambda x: x["param"].order)

        return groups

    def get_perm(self, user, group):
        """
        获取用户对配置组的权限

        Args:
            user: 用户
            group: 配置组

        Returns:
            bool: 是否有权限
        """
        if group.startswith("datacenter") and user.is_superuser:
            return True
        elif group.startswith("system") and user.is_superuser:
            ADMINS = getattr(settings, "ADMINS", [])
            if not ADMINS:
                return False
            return user.email in [a[1] for a in ADMINS]
        elif group.startswith("user") and user.is_active:
            return True
        else:
            return False
