import uuid
from threading import local
from typing import Any

from dcrm.utilities.request import get_request_ip

_thread_locals = local()


class CoreMiddleware:
    """当前用户中间件
    - 使用线程本地存储保存当前请求的用户
    - 每个请求结束后清理线程本地变量
    """

    def __init__(self, get_response) -> None:
        self.get_response = get_response

    def __call__(self, request) -> Any:

        request.id = uuid.uuid4()
        request.ipaddr = str(get_request_ip(request))

        if request.user.is_authenticated:
            _thread_locals.user = request.user

        response = self.get_response(request)
        # 添加Vary头, 用于HTMX响应的缓存
        response["Vary"] = "HX-Request"
        # 添加 X-Request-ID 头，用于请求链跟踪
        response["X-Request-ID"] = request.id

        self.cleanup_locals()

        return response

    def cleanup_locals(self) -> None:
        """清理线程本地变量"""
        if hasattr(_thread_locals, "user"):
            del _thread_locals.user


def get_current_user() -> Any | None:
    """获取当前线程的用户
    在模型和其他地方使用
    """
    return getattr(_thread_locals, "user", None)
