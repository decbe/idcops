from ninja import NinjaAPI
from ninja.security import django_auth

from .routes.codingrule import router as codingrule_router
from .routes.device import router as device_router
from .routes.document import router as document_router

# 导入路由
from .routes.dynamic import router as dynamic_router
from .routes.rack import router as rack_router

ninja_api = NinjaAPI(
    title="DCRM API",
    version="0.1",
    auth=django_auth,
    csrf=True,
    docs_url="/docs",
)

# 注册路由 - 注意：具体路由要在通用路由之前注册
ninja_api.add_router("/v1/", document_router)  # 移到最前面
ninja_api.add_router("/v1/", device_router)
ninja_api.add_router("/v1/", codingrule_router)
ninja_api.add_router("/v1/", rack_router)
ninja_api.add_router("/v1/", dynamic_router)  # 动态路由放在最后
