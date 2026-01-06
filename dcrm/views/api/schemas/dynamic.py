from typing import Any

from django.db import models
from ninja import Schema
from ninja.orm import create_schema

from dcrm.models.fields import InterfaceIPAddressField


class DevicePredictRequestSchema(Schema):
    sn: str
    count: int | None = 5


class DevicePredictResponseSchema(Schema):
    """预测设备型号Schema"""

    status: str
    result: list[tuple]


class PaginatedResponseSchema(Schema):
    """分页响应的基础Schema"""

    total: int
    total_pages: int
    current_page: int
    results: list[dict[str, Any]]
    pagination: dict[str, bool]


class ErrorResponseSchema(Schema):
    """错误响应Schema"""

    error: str
    detail: str | None = None


def create_dynamic_schema(model: type[models.Model]) -> type[Schema]:
    """动态创建模型的Schema
    """
    exclude = ["data_center", "password", "_password"]
    name = f"{model._meta.label}Schema"
    # 创建Schema
    fields = [
        f.name
        for f in model._meta.fields
        if f.name not in exclude
        and not isinstance(f, models.JSONField)
        and not isinstance(f, InterfaceIPAddressField)
    ]
    return create_schema(model, name=name, fields=fields)


def register_ninja_schema():
    """将模型的Schema注册到系统注册表中
    """
    from django.apps import apps

    from dcrm.register import registry

    models = apps.get_models()

    for model in models:
        name = f"{model._meta.label}Schema"
        schema = create_dynamic_schema(model)
        if name not in registry["schemas"]:
            registry["schemas"][name] = schema
    return registry["schemas"]
