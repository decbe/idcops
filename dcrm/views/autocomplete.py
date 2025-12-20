import logging
from typing import Any, Dict, List, Tuple, Type

from str2bool import str2bool

from django.apps import apps
from django.core.exceptions import PermissionDenied
from django.db.models import JSONField, Q
from django.http import JsonResponse
from django.http.response import JsonResponse
from django.urls import path
from django.urls.resolvers import URLPattern
from django.views.generic.list import BaseListView

from dcrm.register import registry
from dcrm.utilities.base import camel_to_snake

from .api.routes.dynamic import serialize_object
from .mixins.base import BaseRequestMixin

logger = logging.Logger(__name__)


class BaseAutocompleteView(BaseRequestMixin, BaseListView):
    """
    基础自动完成视图
    自动生成url路由表
    url规范：/{app_label}/{model_name}/
    """

    paginate_by = 50

    def get(self, request, *args, **kwargs) -> JsonResponse:
        if not self.has_permission(request):
            raise PermissionDenied

        self.term = request.GET.get("term", "")
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        self.mode = request.GET.get("mode", "simple")
        items = context["object_list"]

        # 创建动态Schema
        name = f"{self.model._meta.label}Schema"
        schema = registry["schemas"][name]

        return JsonResponse(
            {
                "results": [serialize_object(item, schema) for item in items],
                "pagination": {"more": context["page_obj"].has_next()},
            }
        )

    def has_permission(self, request) -> bool:
        """检查权限"""
        opts = self.model._meta
        permission = f"{opts.app_label}.view_{opts.model_name}"
        verify = all([request.user.is_authenticated, request.user.has_perm(permission)])
        return verify

    def get_model_fields(self) -> list:
        exclude = ["data_center", "password", "_password"]

        return [
            f.name
            for f in self.model._meta.fields
            if f.name not in exclude and not isinstance(f, JSONField)
        ]

    def get_queryset(self) -> Any:
        """获取查询集"""
        query = Q()
        if hasattr(self.model, "data_center"):
            query = Q(data_center=self.request.user.data_center)
        if hasattr(self.model, "shared"):
            query |= Q(shared=True)

        qs = self.model.objects.filter(query)
        if self.term:
            qs = self.search_results(qs, self.term)
        if filters := self.get_filters(self.request):
            qs = qs.filter(**filters)
        return qs.distinct()

    def get_filters(self, request):
        filters = {}
        allowed_filter_method = [
            "",
            "__in",
            "__isnull",
            "__iexact",
            "__gt",
            "__in",
            "__range",
        ]
        model_field_map = {
            f"{f.name}{method}": f"{f.name}{method}"
            for f in self.model._meta.get_fields()
            for method in allowed_filter_method
        }
        for field_name, value in model_field_map.items():
            if field_name in request.GET:
                _value = request.GET.get(field_name)
                if _value != "all":
                    filters[value] = _value
                if "__isnull" in field_name:
                    filters[value] = str2bool(_value)
                if "__in" in field_name:
                    filters[value] = _value.split(",")
        return filters

    def search_results(self, qs, term):
        """搜索结果"""
        return qs

    def serialize_result(self, obj):
        """序列化结果"""
        return {"id": str(obj.pk), "text": str(obj)}


def create_autocomplete_view(model) -> Type[BaseAutocompleteView]:
    """
    动态创建导入视图类
    """
    class_name = f"{model.__name__}AutoCompleteView"
    return type(
        class_name,
        (BaseAutocompleteView,),
        {"model": model},
    )


def get_autocomplete_models() -> (
    Tuple[Dict[str, Type[BaseAutocompleteView]], List[URLPattern]]
):
    """
    获取所有可导入的模型和对应的URL patterns
    返回: (autocomplete_map, url_patterns)
    """
    autocomplete_map = {}
    url_patterns = []

    # 获取 dcrm 应用下的所有模型
    dcrm_app = apps.get_app_config("dcrm")

    # 排除的模型列表
    excluded_models = {
        "datacenter",  # 数据中心
        "datacentergroup",  # 数据中心组
    }

    for model in dcrm_app.get_models():
        if not getattr(model, "data_center", False):
            continue

        model_path = f"{model._meta.app_label}.{model._meta.model_name}"

        # 跳过被排除的模型
        if model._meta.model_name in excluded_models:
            continue

        # 为没有自定义视图的模型创建默认导入视图
        view_class = create_autocomplete_view(model)
        autocomplete_map[model_path] = view_class

        # 使用默认URL模式
        # logger.info(f"DEBUG: 使用默认URL模式: {model._meta.model_name}")
        model_name = camel_to_snake(model._meta.object_name)
        url_prefix = camel_to_snake(model._meta.object_name, "-")
        url_pattern = path(
            f"{url_prefix}/autocomplete/",
            view_class.as_view(),
            name=f"{model_name}_autocomplete",
        )

        url_patterns.append(url_pattern)

    return autocomplete_map, url_patterns


def register_or_get_autocomplete_views(get_urls=False):
    """注册所有导入视图"""
    # 获取所有可导入的模型和对应的导入视图
    model_import_map, url_patterns = get_autocomplete_models()

    # 注册到注册表
    for model_path, view in model_import_map.items():
        try:
            registry["autocomplete"][model_path] = view
        except (LookupError, ValueError) as e:
            logger.error(f"无法注册导入视图 {model_path}: {str(e)}")
    if get_urls:
        return url_patterns


def register_autocomplete_views():
    """注册所有导入视图"""
    # 获取所有可导入的模型和对应的导入视图
    model_import_map, _ = get_autocomplete_models()

    # 注册到注册表
    for model_path, view in model_import_map.items():
        try:
            registry["autocomplete"][model_path] = view
        except (LookupError, ValueError) as e:
            logger.error(f"无法注册导入视图 {model_path}: {str(e)}")


# 导出URL patterns供urls.py使用
def get_autocomplete_urls() -> List[URLPattern]:
    """获取所有导入视图的URL patterns"""
    _, url_patterns = get_autocomplete_models()
    return url_patterns
