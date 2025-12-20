from typing import Any, Callable, Dict, List, Union

from django.apps import apps
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.db.models.base import Model
from django.utils.translation import gettext_lazy as _

from dcrm.models.choices import ActionColorChoices
from dcrm.register import registry as sys_registry

__all__ = ["registry", "ActionRegistry", "ActionError"]


class ActionError(Exception):
    """Action执行错误"""

    pass


class ActionRegistry:
    """操作注册器"""

    _actions = sys_registry["actions"]

    def register(self, **options) -> Callable[..., Callable[..., Any]]:
        """注册操作的装饰器"""

        def decorator(func: Callable) -> Callable[..., Any]:
            # 处理models选项
            action_func_name = func.__name__
            action_models = options.get("models")
            # 按模型分组
            for model in action_models:
                if not model:
                    continue
                opts = model._meta
                model_name = f"{opts.app_label}.{opts.model_name}"
                permissions = [
                    f"{opts.app_label}.{perm}_{opts.model_name}"
                    for perm in options.get("permissions")
                ]

                self._actions[model_name][action_func_name] = {
                    "action_type": action_func_name,
                    "name": options.get("name", action_func_name),
                    "description": options.get("description", ""),
                    "is_htmx": options.get("is_htmx", False),
                    "confirm_message": options.get("confirm_message", ""),
                    "permissions": permissions,
                    "color": options.get("color", ActionColorChoices.INFO),
                    "icon": options.get("icon", ""),
                    "order": options.get("order", 50),
                    "onclick": options.get("onclick", None),  # 前端JavaScript函数
                    "func": func,  # 原始函数
                }

            return func

        return decorator

    def get_model(self, model: Union[models.Model | str]) -> Any | Model | str:
        if isinstance(model, str):
            if "." not in model:
                raise ActionError(f"{model} like `dcrm.rack` string")
            app_label, model_name = model.split(".")
            model = apps.get_model(app_label, model_name)
        return model

    def get_action(self, model: Union[models.Model | str], action_type: str) -> Dict:
        """获取指定操作的配置"""
        model = self.get_model(model)
        actions = self.get_model_actions(model)
        if action_type not in actions:
            raise ActionError(f"{model} action: {action_type} no exists")
        return actions[action_type]

    def get_model_actions(self, model: Union[models.Model | str]) -> Dict:
        """获取指定模型的所有操作，已排序"""
        model = self.get_model(model)
        model_name = f"{model._meta.app_label}.{model._meta.model_name}".lower()

        if model_name not in self._actions:
            return {}

        # 获取模型的所有操作并直接返回排序结果
        model_actions = self._actions[model_name]
        return dict(sorted(model_actions.items(), key=lambda x: x[1]["order"]))

    def has_permission(self, user, model, action_type):
        if user.is_superuser:
            return True
        action = self.get_action(model, action_type)
        return user.has_perms(action["permissions"])

    def get_user_model_actions(
        self, user, model: Union[models.Model | str]
    ) -> List[Dict]:
        """获取指定用户在指定模型下的所有操作权限

        Args:
            user: User实例
            model: 模型类或模型名称字符串(例如: 'dcrm.rack')

        Returns:
            List[Dict]: 包含操作信息和权限的列表
        """
        model = self.get_model(model)
        # 获取模型的所有操作
        model_actions = self.get_model_actions(model)

        user_actions = list(
            filter(
                lambda action: user.has_perms(action["permissions"]),
                model_actions.values(),
            )
        )
        return user_actions


class ActionExecutor:
    """操作执行器"""

    def __init__(self, request, model: Union[models.Model | str], action_type: str):
        self.request = request
        self.user = request.user
        self.action_type = action_type
        self.action = registry.get_action(model, action_type)

        # 检查权限
        if not registry.has_permission(self.user, model, self.action_type):
            raise PermissionDenied(
                f"User {self.user} doesn't have permissions to execute {self.action_type}"
            )

    def execute(self, request, instances, **kwargs) -> Any:
        """
        执行操作

        Args:
            instances: 操作对象(单个对象或QuerySet)
            **kwargs: 操作参数
                atomic: 是否使用事务(默认True)
        """
        use_atomic = kwargs.pop("atomic", True)

        try:
            # 执行操作
            if use_atomic:
                with transaction.atomic():
                    result = self.action["func"](request, instances, **kwargs)
            else:
                result = self.action["func"](request, instances, **kwargs)
            return result

        except Exception as e:
            raise ActionError(str(e))


# 全局注册器实例
registry = ActionRegistry()
