import logging
from typing import Dict, List, Tuple, Type

from django.apps import apps
from django.db import models
from django.urls import path, reverse_lazy
from django.urls.resolvers import URLPattern

from dcrm.register import registry
from dcrm.utilities.base import camel_to_snake
from dcrm.views.imports.views import BulkImportView

logger = logging.getLogger(__name__)

__all__ = [
    "register_import_views",
    "get_import_urls",
    "create_import_view",
    "get_importable_models",
    "import_registry",
]


class ImportRegistry:
    def __init__(self):
        self._registry: Dict[Type[models.Model], Type["BulkImportView"]] = registry[
            "imports"
        ]

    def register(
        self, model_class: Type[models.Model], import_view: Type["BulkImportView"]
    ) -> None:
        """注册模型的导入视图"""
        name = model_class._meta.label
        self._registry[name] = import_view

    def get_import_view(
        self, model_class: Type[models.Model]
    ) -> Type["BulkImportView"]:
        """获取模型的导入视图"""
        name = model_class._meta.label
        return self._registry.get(name)

    def register_models(
        self, model_import_map: Dict[str, Type["BulkImportView"]]
    ) -> None:
        """
        批量注册模型的导入视图
        model_import_map: {'app_label.model_name': ImportViewClass}
        """
        for model_path, import_view in model_import_map.items():
            try:
                app_label, model_name = model_path.split(".")
                model = apps.get_model(app_label, model_name)
                self.register(model, import_view)
            except (LookupError, ValueError) as e:
                logger.error(f"无法注册导入视图 {model_path}: {str(e)}")


# 创建全局单例
import_registry = ImportRegistry()


def create_import_view(model) -> Type[BulkImportView]:
    """
    动态创建导入视图类
    """
    class_name = f"{model.__name__}ImportView"
    url_name = f"{camel_to_snake(model._meta.object_name)}_list"
    # logger.info(f"DEBUG: 创建导入视图类: {class_name}")
    # logger.info(f"DEBUG: 创建导入视图URL: {url_name}")
    return type(
        class_name,
        (BulkImportView,),
        {"model": model, "success_url": reverse_lazy(url_name)},
    )


# 自定义导入视图映射
CUSTOM_IMPORT_VIEWS = {
    # 'dcrm.device': DeviceBulkImportView,
    # 'dcrm.onlinedevice': OnlineDeviceBulkImportView,
    # 'dcrm.devicemodel': DeviceModelBulkImportView,
    # 'dcrm.subnet': SubnetBulkImportView,
    # ... 其他自定义导入视图
}


# 自定义URL配置
CUSTOM_URL_PATTERNS = {
    # 'dcrm.device': {
    #     'path': 'devices/import/',  # 自定义路径
    #     'name': 'device_import'     # 自定义名称
    # },
    # 'dcrm.onlinedevice': {
    #     'path': 'devices/online/import/',
    #     'name': 'online_device_import'
    # },
    # 'dcrm.devicemodel': {
    #     'path': 'devices/model/import/',
    #     'name': 'device_model_import'
    # },
    # 'dcrm.subnet': {
    #     'path': 'networks/subnet/import/',
    #     'name': 'subnet_import'
    # }
}


def get_importable_models() -> Tuple[Dict[str, Type[BulkImportView]], List[URLPattern]]:
    """
    获取所有可导入的模型和对应的URL patterns
    返回: (import_map, url_patterns)
    """
    import_map = {}
    url_patterns = []

    # 首先添加自定义的导入视图
    import_map.update(CUSTOM_IMPORT_VIEWS)

    # 获取 dcrm 应用下的所有模型
    dcrm_app = apps.get_app_config("dcrm")

    # 排除的模型列表
    excluded_models = {
        "datacenter",  # 数据中心
        "datacentergroup",  # 数据中心组
        "logentry",  # 日志条目
        "customfield",  # 自定义字段
    }

    for model in dcrm_app.get_models():
        if not getattr(model, "data_center", False):
            continue

        model_path = f"{model._meta.app_label}.{model._meta.model_name}"

        # 跳过被排除的模型
        if model._meta.model_name in excluded_models:
            continue

        # 检查模型是否支持导入
        if not getattr(model, "supports_import", True):
            logger.info(f"INFO: 导入视图跳过模型: {model._meta.model_name}")
            continue

        # 如果已经有自定义视图，使用自定义视图
        if model_path in import_map:
            view_class = import_map[model_path]
        else:
            # 为没有自定义视图的模型创建默认导入视图
            view_class = create_import_view(model)
            import_map[model_path] = view_class

        # 检查是否有自定义URL配置
        custom_url = CUSTOM_URL_PATTERNS.get(model_path)
        if custom_url:
            url_pattern = path(
                custom_url["path"], view_class.as_view(), name=custom_url["name"]
            )
        else:
            # 使用默认URL模式
            # logger.info(f"DEBUG: 使用默认URL模式: {model._meta.model_name}")
            model_name = camel_to_snake(model._meta.object_name)
            url_pattern = path(
                f'{model_name.replace("_", "-")}/import/',
                view_class.as_view(),
                name=f"{model_name}_import",
            )

        url_patterns.append(url_pattern)

    return import_map, url_patterns


def register_import_views():
    """注册所有导入视图"""
    # 获取所有可导入的模型和对应的导入视图
    model_import_map, _ = get_importable_models()

    # 注册到注册表
    import_registry.register_models(model_import_map)


# 导出URL patterns供urls.py使用
def get_import_urls() -> List[URLPattern]:
    """获取所有导入视图的URL patterns"""
    _, url_patterns = get_importable_models()
    return url_patterns
