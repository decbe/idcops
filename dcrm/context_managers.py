from contextlib import contextmanager
from threading import local

_thread_locals = local()


@contextmanager
def current_user_context(user):
    """
    用于测试或脚本中模拟当前用户的上下文管理器

    使用示例:
    with current_user_context(user):
        device = Device.objects.create(name='test')
    """
    previous_user = getattr(_thread_locals, "user", None)
    try:
        _thread_locals.user = user
        yield
    finally:
        if previous_user is not None:
            _thread_locals.user = previous_user
        else:
            del _thread_locals.user
