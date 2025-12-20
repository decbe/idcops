import collections

from django.utils.translation import gettext as _


class Registry(dict):
    """
    用于注册功能的中央注册表。用于管理所有的注册项。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._locked = False

    def __getitem__(self, key):
        try:
            return super().__getitem__(key)
        except KeyError:
            raise KeyError(_("无效的注册表: {key}").format(key=key))

    def __setitem__(self, key, value):
        if self._locked:
            raise TypeError(_("无法在初始化后添加注册表"))
        super().__setitem__(key, value)

    def __delitem__(self, key):
        raise TypeError(_("无法删除注册表"))

    def lock(self):
        """锁定注册表，防止添加新的顶级键"""
        self._locked = True


# 初始化全局注册表
registry = Registry(
    {
        "actions": collections.defaultdict(dict),
        "imports": collections.defaultdict(dict),
        "configs": collections.defaultdict(dict),
        "schemas": collections.defaultdict(dict),
        "counter_fields": collections.defaultdict(dict),
        "custom_fields": collections.defaultdict(dict),
        "autocomplete": collections.defaultdict(dict),
        "apis": collections.defaultdict(dict),
        "event_types": collections.defaultdict(dict),
    }
)
registry.lock()  # 锁定注册表，防止添加新的顶级键
