"""API 路由工具函数
提供动态注册和管理 API 路由的功能
"""

from collections.abc import Callable
from functools import wraps
from typing import Any

from ninja import Router

from dcrm.register import registry


def register_api_route(
    router: Router,
    path: str,
    *,
    methods: list[str] = None,
    response: dict[int, type] = None,
    auth: Callable | list[Callable] | None = None,
    tags: list[str] = None,
    summary: str = None,
    description: str = None,
    operation_id: str = None,
    api_key_name: str = None,
    route_name: str = None,  # 路由名称，用于后续获取
    **options: dict[str, Any],
):
    """动态注册 API 路由装饰器

    这个装饰器允许你动态地注册一个函数为 API 路由，
    同时将路由函数注册到全局 registry 中，以便后续使用。

    使用方法:

    @register_api_route(
        router,
        "/my-route/{param}/",
        methods=["GET"],
        response={200: ResponseSchema},
        route_name="my_custom_route"
    )
    def my_route_function(request, param: str):
        # 函数实现
        return {"result": "success"}

    # 之后可以通过 route_name 获取注册的函数
    my_func = registry["apis"].get("my_custom_route")

    参数:
        router: Ninja Router 实例
        path: API 路径，与 router.get/post 等方法的 path 参数相同
        methods: HTTP 方法列表，默认为 ["GET"]
        response: 响应模式映射，与 router 方法的 response 参数相同
        auth: 认证处理函数
        tags: API 标签列表
        summary: API 摘要
        description: API 描述
        operation_id: 操作 ID
        api_key_name: API 密钥名称
        route_name: 路由名称，用于在 registry 中唯一标识该路由
        **options: 其他选项

    返回:
        装饰器函数
    """
    methods = methods or ["GET"]

    def decorator(func):
        # 注册到全局 registry 中
        if route_name:
            registry["apis"][route_name] = func

        # 根据 methods 选择合适的 router 方法
        for method in methods:
            method = method.lower()
            if method == "get":
                router_method = router.get
            elif method == "post":
                router_method = router.post
            elif method == "put":
                router_method = router.put
            elif method == "delete":
                router_method = router.delete
            elif method == "patch":
                router_method = router.patch
            else:
                continue

            # 使用选定的 router 方法装饰函数
            func = router_method(
                path,
                response=response,
                auth=auth,
                tags=tags,
                summary=summary,
                description=description,
                operation_id=operation_id,
                **options,
            )(func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator


def get_registered_api_route(route_name: str) -> Callable | None:
    """获取已注册的 API 路由函数

    参数:
        route_name: 路由名称

    返回:
        注册的路由函数，如果不存在则返回 None
    """
    return registry["apis"].get(route_name)


def register_route_from_config(
    router: Router, route_config: dict[str, Any], handler_func: Callable
):
    """从配置字典注册路由

    这个函数允许从配置字典中注册路由，方便从数据库或配置文件加载路由定义

    参数:
        router: Ninja Router 实例
        route_config: 路由配置字典，包含路径、HTTP方法等
        handler_func: 处理函数

    例子:
        config = {
            "path": "/api/test/{param}/",
            "methods": ["GET"],
            "response": {200: ResponseSchema},
            "route_name": "test_route",
            "summary": "测试路由",
            "description": "这是一个测试路由"
        }

        def handler(request, param: str):
            return {"result": param}

        register_route_from_config(router, config, handler)
    """
    path = route_config.pop("path")
    methods = route_config.pop("methods", ["GET"])

    return register_api_route(router, path, methods=methods, **route_config)(
        handler_func
    )


def register_routes_batch(
    router: Router,
    routes_config: list[dict[str, Any]],
    handlers_map: dict[str, Callable],
):
    """批量注册路由

    从配置列表和处理函数映射中批量注册路由

    参数:
        router: Ninja Router 实例
        routes_config: 路由配置列表
        handlers_map: 处理函数映射，键是处理函数名，值是处理函数

    例子:
        configs = [
            {
                "path": "/api/test1/",
                "methods": ["GET"],
                "handler": "test_handler1",
                "route_name": "test1"
            },
            {
                "path": "/api/test2/",
                "methods": ["POST"],
                "handler": "test_handler2",
                "route_name": "test2"
            }
        ]

        handlers = {
            "test_handler1": lambda request: {"result": "test1"},
            "test_handler2": lambda request, data: {"result": data}
        }

        register_routes_batch(router, configs, handlers)
    """
    for config in routes_config:
        handler_name = config.pop("handler")
        if handler_name not in handlers_map:
            raise ValueError(f"Handler function '{handler_name}' not found")

        register_route_from_config(router, config, handlers_map[handler_name])
