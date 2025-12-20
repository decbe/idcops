from functools import wraps

from django.conf import settings
from django.core.cache import cache

CACHE_TIMEOUT = getattr(settings, "USER_CONFIGURE_CACHE_TIMEOUT", 3600)  # 1小时
CACHE_KEY_PREFIX = "user_configure:"


def cache_user_configure(func):
    """用户configure缓存装饰器"""

    @wraps(func)
    def wrapper(self, user, *args, **kwargs):
        cache_key = f"{CACHE_KEY_PREFIX}{user.id}"
        cached_value = cache.get(cache_key)

        if cached_value is not None:
            return cached_value

        value = func(self, user, *args, **kwargs)
        cache.set(cache_key, value, CACHE_TIMEOUT)
        return value

    return wrapper


class UserConfigureCache:
    """用户configure缓存管理"""

    @staticmethod
    def get_cache_key(user_id: int) -> str:
        return f"{CACHE_KEY_PREFIX}{user_id}"

    @classmethod
    def get(cls, user_id: int) -> dict:
        """获取用户configure"""
        return cache.get(cls.get_cache_key(user_id))

    @classmethod
    def set(cls, user_id: int, configure: dict):
        """设置用户configure"""
        cache.set(cls.get_cache_key(user_id), configure, CACHE_TIMEOUT)

    @classmethod
    def delete(cls, user_id: int):
        """删除用户configure缓存"""
        cache.delete(cls.get_cache_key(user_id))

    @classmethod
    def bulk_delete(cls, user_ids: list):
        """批量删除用户configure缓存"""
        cache.delete_many([cls.get_cache_key(user_id) for user_id in user_ids])
