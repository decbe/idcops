from typing import Any, Dict, Optional

from ninja import Query, Router, Schema
from str2bool import str2bool

from django.apps import apps
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Q

from dcrm.register import registry

from ..schemas.dynamic import ErrorResponseSchema, PaginatedResponseSchema
from .utils import register_api_route

router = Router()


@router.get(
    "/{app_label}/{model_name}/",
    response={200: PaginatedResponseSchema, 404: ErrorResponseSchema},
    url_name="list_objects",
)
def list_objects(
    request,
    app_label: str,
    model_name: str,
    page: Optional[int] = Query(1, gt=0),
    per_page: Optional[int] = Query(50, gt=0, le=100),
    search: Optional[str] = None,
    ordering: Optional[str] = None,
):
    """
    动态获取模型数据列表

    参数:
    - app_label: 应用标签
    - model_name: 模型名称
    - page: 页码
    - per_page: 每页数量
    - search: 搜索关键词
    - ordering: 排序字段 (例如: "id" 或 "-created")
    - [filter]: 过滤字段(过滤字段需要根据当前模型的字段，例如 /?device=6&status=connected)
    """

    def get_filter_by(request, model):
        filters = {}
        allowed_filter_method = ["", "__in", "__isnull"]
        model_field_map = {
            f"{f.name}{method}": f"{f.name}{method}"
            for f in model._meta.get_fields()
            for method in allowed_filter_method
        }
        for param in request.GET:
            if param not in model_field_map.keys():
                continue
            if param.endswith("__isnull"):
                value = str2bool(request.GET.get(param))
            elif param.endswith("__in"):
                value = request.GET.getlist(param)
            else:
                value = request.GET.get(param)
            filters[param] = value
        return filters

    try:
        # 获取模型类
        model = apps.get_model(app_label, model_name)

        # 创建动态Schema
        name = f"{model._meta.label}Schema"
        schema = registry["schemas"][name]

        # 基础查询集
        queryset = model.objects.all()
        query = models.Q()
        # 数据中心过滤
        if hasattr(model, "data_center"):
            query = models.Q(data_center=request.user.data_center)
        if hasattr(model, "shared"):
            query |= models.Q(shared=True)

        queryset = queryset.filter(query)

        # 搜索功能
        if search:
            search_fields = []
            for field in model._meta.fields:
                if isinstance(field, (models.CharField, models.TextField)):
                    search_fields.append(field.name)

            if search_fields:
                q_objects = Q()
                for field in search_fields:
                    q_objects |= Q(**{f"{field}__icontains": search})
                queryset = queryset.filter(q_objects)
        # 过滤功能
        if query_filter := get_filter_by(request, model):
            queryset = queryset.filter(**query_filter).distinct()
        # 排序
        if ordering:
            if ordering.startswith("-"):
                field_name = ordering[1:]
            else:
                field_name = ordering

            if hasattr(model, field_name):
                queryset = queryset.order_by(ordering)

        # 分页
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)

        # 返回结果
        return {
            "total": paginator.count,
            "total_pages": paginator.num_pages,
            "current_page": page,
            "results": [serialize_object(obj, schema) for obj in page_obj],
            "pagination": {"more": page_obj.has_next()},
        }

    except (LookupError, KeyError) as err:
        return 404, {
            "error": "Model not found",
            "detail": f"Model {app_label}.{model_name} does not exist. {err}",
        }
    except Exception as e:
        return 404, {"error": "Error occurred", "detail": str(e)}


def serialize_object(obj, schema):
    """序列化对象，处理外键关系"""
    data = schema.from_orm(obj).dict()
    data.update({"_repr": str(obj)})
    return data


# 动态 API 示例 Schema
class DeviceInfoResponseSchema(Schema):
    status: str = "success"
    result: Dict[str, Any]


# 使用动态注册路由装饰器注册 API 路由
@register_api_route(
    router,
    "/devices/{device_id}/info/",
    methods=["GET"],
    response={200: DeviceInfoResponseSchema, 404: ErrorResponseSchema},
    route_name="device_info",
    summary="获取设备详细信息",
    description="根据设备ID获取设备的详细信息，包括硬件规格等",
)
def get_device_info(request, device_id: int):
    """获取设备详细信息"""
    try:
        from dcrm.models import Device

        # 数据中心过滤
        query = models.Q()
        if hasattr(Device, "data_center"):
            query = models.Q(data_center=request.user.data_center)
        if hasattr(Device, "shared"):
            query |= models.Q(shared=True)

        device = Device.objects.filter(query).get(pk=device_id)

        # 获取设备详细信息
        device_data = {
            "id": device.id,
            "name": device.name,
            "serial_number": getattr(device, "serial_number", None),
            "device_type": getattr(device, "type", None),
            "height": getattr(device, "height", None),
            "position": getattr(device, "position", None),
            "model": str(device.model) if hasattr(device, "model") else None,
            "tenant": str(device.tenant) if hasattr(device, "tenant") else None,
            "status": getattr(device, "status", None),
            "created_at": getattr(device, "created_at", None),
            "updated_at": getattr(device, "updated_at", None),
            "created_by": (
                str(device.created_by) if hasattr(device, "created_by") else None
            ),
            "__str__": str(device),
        }

        return {"status": "success", "result": device_data}
    except Device.DoesNotExist:
        return 404, {
            "status": "error",
            "message": f"Device with ID {device_id} not found",
        }
    except Exception as e:
        return 404, {"status": "error", "detail": str(e)}


# 动态注册更多路由的函数
def register_dynamic_routes():
    """
    动态注册更多自定义路由

    这个函数可以在项目启动时或者需要时被调用，用于注册更多的自定义路由
    """
    # 示例：从配置批量注册路由
    from .utils import register_routes_batch

    # 这些配置可以从数据库或配置文件中加载
    routes_config = [
        {
            "path": "/devices/summary/",
            "methods": ["GET"],
            "handler": "get_devices_summary",
            "route_name": "devices_summary",
            "summary": "获取设备统计摘要",
            "description": "获取整个数据中心的设备统计数据，包括设备总数、各种状态的设备数量等",
            "response": {200: DeviceInfoResponseSchema, 404: ErrorResponseSchema},
        },
        {
            "path": "/devices/search/",
            "methods": ["GET"],
            "handler": "search_devices",
            "route_name": "devices_search",
            "summary": "搜索设备",
            "description": "根据关键词搜索设备，可以搜索名称、序列号等字段",
            "response": {200: PaginatedResponseSchema, 404: ErrorResponseSchema},
        },
    ]

    # 处理函数映射
    handlers = {
        "get_devices_summary": get_devices_summary,
        "search_devices": search_devices,
    }

    # 批量注册路由
    try:
        register_routes_batch(router, routes_config, handlers)
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"动态注册路由失败: {str(e)}")


# 定义处理函数
def get_devices_summary(request):
    """获取设备统计摘要"""
    try:
        from dcrm.models import Device

        # 数据中心过滤
        query = models.Q()
        if request.user.is_authenticated:
            if hasattr(Device, "data_center"):
                query = models.Q(data_center=request.user.data_center)
            if hasattr(Device, "shared"):
                query |= models.Q(shared=True)

        # 获取设备统计数据
        devices = Device.objects.filter(query)
        total_count = devices.count()

        # 按状态统计
        status_counts = {}
        if hasattr(Device, "status"):
            from django.db.models import Count

            status_counts = dict(
                devices.values("status")
                .annotate(count=Count("status"))
                .values_list("status", "count")
            )

        # 按类型统计
        type_counts = {}
        if hasattr(Device, "type"):
            from django.db.models import Count

            type_counts = dict(
                devices.values("type")
                .annotate(count=Count("type"))
                .values_list("type", "count")
            )

        return {
            "status": "success",
            "result": {
                "total_count": total_count,
                "status_counts": status_counts,
                "type_counts": type_counts,
            },
        }
    except Exception as e:
        return 404, {"status": "error", "detail": str(e)}


def search_devices(
    request,
    keyword: str = Query(None, description="搜索关键词"),
    page: int = Query(1, gt=0, description="页码"),
    per_page: int = Query(20, gt=0, le=100, description="每页数量"),
):
    """搜索设备"""
    try:
        from dcrm.models import Device

        if not keyword:
            return 404, {"status": "error", "message": "搜索关键词不能为空"}

        # 数据中心过滤
        query = models.Q()
        if request.user.is_authenticated:
            if hasattr(Device, "data_center"):
                query = models.Q(data_center=request.user.data_center)
            if hasattr(Device, "shared"):
                query |= models.Q(shared=True)

        # 搜索条件
        search_query = Q()
        search_fields = ["name", "serial_number", "model__name"]

        for field in search_fields:
            search_query |= Q(**{f"{field}__icontains": keyword})

        # 执行查询
        queryset = Device.objects.filter(query).filter(search_query)

        # 分页
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)

        # 获取设备Schema
        name = f"{Device._meta.label}Schema"
        if name in registry["schemas"]:
            schema = registry["schemas"][name]

            # 返回结果
            return {
                "total": paginator.count,
                "total_pages": paginator.num_pages,
                "current_page": page,
                "results": [serialize_object(obj, schema) for obj in page_obj],
            }
        else:
            # 手动序列化
            results = []
            for device in page_obj:
                results.append(
                    {
                        "id": device.id,
                        "name": device.name,
                        "serial_number": getattr(device, "serial_number", None),
                        "model": (
                            str(device.model) if hasattr(device, "model") else None
                        ),
                        "status": getattr(device, "status", None),
                        "_repr": str(device),
                    }
                )

            return {
                "total": paginator.count,
                "total_pages": paginator.num_pages,
                "current_page": page,
                "results": results,
            }
    except Exception as e:
        return 404, {"status": "error", "detail": str(e)}
