from django.db.models.query_utils import DeferredAttribute

from dcrm.register import registry


class Tracker:
    """
    一个临时实例，用于记录实例中哪些被跟踪的字段已被修改。
    """

    def __init__(self):
        self._changed_fields = {}

    def __contains__(self, item):
        return item in self._changed_fields

    def set(self, name, value):
        """
        标记某个属性已被更改，并记录其原始值。
        """
        self._changed_fields[name] = value

    def get(self, name):
        """
        返回已更改字段的原始值。如果未找到字段名则抛出 KeyError。
        """
        return self._changed_fields[name]

    def clear(self, *names):
        """
        清除所有已记录为更改的字段。
        """
        if names:
            for name in names:
                self._changed_fields.pop(name, None)
        else:
            self._changed_fields = {}


class TrackingModelMixin:

    tracker_model = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 标记实例已初始化，以启用自定义的 __setattr__()
        self._initialized = True

    @property
    def tracker(self):
        """
        返回该实例的 Tracker 实例，如有必要则先创建。
        """
        if not hasattr(self._state, "_tracker"):
            self._state._tracker = Tracker()
        return self._state._tracker

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        update_fields = kwargs.get("update_fields", None)
        if update_fields:
            self.tracker.clear(*update_fields)
        else:
            self.tracker.clear()

    def __setattr__(self, name, value):
        if hasattr(self, "_initialized"):
            # 记录对被跟踪字段的任何更改
            if name in registry["counter_fields"][self.__class__]:
                if name not in self.tracker:
                    # 属性已被创建或更改
                    if name in self.__dict__:
                        old_value = getattr(self, name)
                        if value != old_value:
                            self.tracker.set(name, old_value)
                    else:
                        self.tracker.set(name, DeferredAttribute)
                elif value == self.tracker.get(name):
                    # 先前更改的属性已被还原
                    self.tracker.clear(name)

        super().__setattr__(name, value)
