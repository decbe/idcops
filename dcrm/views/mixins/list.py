import logging
from collections.abc import Generator
from datetime import datetime
from itertools import chain
from typing import Any, Never

from django import forms
from django.contrib import messages
from django.contrib.auth import get_permission_codename
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages import add_message
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import Model, QuerySet
from django.db.models.options import Options
from django.http import HttpResponse, HttpResponseBase
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.views.generic import ListView
from str2bool import str2bool

from dcrm.actions import ActionExecutor
from dcrm.constants import (
    DEFAULT_PER_PAGE,
    MAX_PAGE_SIZE,
    ORDERING_PARAM,
    ORDERING_SEP,
    PAGINATE_BY_PARAM,
)
from dcrm.forms.filters import (
    ButtonCheckboxFilterWidget,
    FilterForm,
    MultipleChoiceFilterWidget,
)
from dcrm.forms.search import SearchForm
from dcrm.models import CustomField
from dcrm.models.choices import CustomFieldVisibilityChoices
from dcrm.register import registry
from dcrm.utilities.base import camel_to_snake, lookup_field_verbose
from dcrm.utilities.lookup import LookupFields, get_select2_language, is_model_field
from dcrm.views.mixins.base import HtmxResponseMixin

logger = logging.getLogger(__name__)

__all__ = ["ListViewMixin"]


class FilterMixin:
    """过滤混入类"""

    filter_fields = []  # 手动配置的过滤字段
    exclude_filter_fields = [
        "custom_field_data",
        "id",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "data_center",
        "lft",
        "rght",
        "tree_id",
        "level",
        # "parent",
    ]  # 排除的过滤字段类型

    def get_filter_form(self):
        """获取过滤表单实例"""
        form_class = self.get_filter_form_class()
        if form_class:
            return form_class(data=self.request.GET or None, model=self.model)
        return None

    def get_filter_form_class(self):
        """获取过滤表单类"""
        exclude_filter_fields = getattr(self, "exclude_filter_fields", []).copy()
        filter_fields = getattr(self, "filter_fields", []).copy()

        class DynamicFilterForm(FilterForm):
            def __init__(self, *args, **kwargs):
                self.exclude_filter_fields = exclude_filter_fields
                self.data = kwargs.get("data", None)
                super().__init__(*args, **kwargs)
                default_filter_fields = [
                    f
                    for f in chain(
                        self.model._meta.fields, self.model._meta.many_to_many
                    )
                ]
                available_fields = (
                    filter_fields.copy() if filter_fields else default_filter_fields
                )
                # 收集并排序字段
                field_groups = {
                    "choice": [],  # 权重 1: choices 字段
                    "date": [],  # 权重 2: 日期字段
                    "foreign": [],  # 权重 3: 外键字段 移除外键，不然会影响性能
                    "many": [],  # 权重 4: 多对多字段
                }

                # 分类收集字段
                for field in available_fields:
                    if field.name in exclude_filter_fields:
                        continue
                    if hasattr(field, "choices") and field.choices:
                        field_groups["choice"].append(field)
                    elif isinstance(field, (models.DateTimeField, models.DateField)):
                        field_groups["date"].append(field)
                    elif isinstance(field, models.ForeignKey):
                        field_groups["foreign"].append(field)
                    elif isinstance(field, models.ManyToManyField):
                        field_groups["many"].append(field)
                # 按顺序添加字段
                for group in ["choice", "date", "foreign", "many"]:
                    for field in field_groups[group]:
                        initial = (
                            self.data.getlist(field.name, None) if self.data else None
                        )
                        filter_field = self._create_filter_field(field, initial)
                        if filter_field:
                            self.fields[field.name] = filter_field

        # 将方法移到类中
        DynamicFilterForm._create_filter_field = self._create_filter_field
        DynamicFilterForm.filter_fields = self.filter_fields

        # 创建表单实例检查是否有过滤字段
        temp_form = DynamicFilterForm(data=None, model=self.model)
        if temp_form.fields:
            return DynamicFilterForm
        return None

    def _create_filter_field(self, model_field, initial=None):
        """根据模型字段创建过滤字段"""
        if hasattr(model_field, "choices") and model_field.choices:
            field = forms.MultipleChoiceField(
                choices=model_field.choices,
                label=model_field.verbose_name,
                required=False,
                initial=initial,
                widget=ButtonCheckboxFilterWidget(),
            )
            field.is_button_group = True
            return field

        # 只处理外键字段
        if isinstance(model_field, (models.ForeignKey, models.ManyToManyField)):
            # 使用 model 直接查询而不是 get_queryset()
            if model_field.related_model is ContentType:
                return None

            tags = all(
                [
                    isinstance(model_field, models.ManyToManyField),
                    model_field.name == "tags",
                ]
            )
            foreign = isinstance(model_field, models.ForeignKey)
            related_model = model_field.related_model
            if tags or foreign:
                content_type = ContentType.objects.get_for_model(
                    self.model, for_concrete_model=True
                )
                opts = self.model._meta.concrete_model._meta
                model_name = camel_to_snake(model_field.related_model._meta.object_name)
                base_query = (
                    f"?object_types={content_type.id}&{opts.model_name}__isnull=0"
                )
                attrs = {
                    "data-ajax--cache": "true",
                    "data-ajax--delay": 250,
                    "data-ajax--type": "GET",
                    "data-ajax-url": reverse_lazy(f"{model_name}_autocomplete")
                    + base_query,
                    "data-allow-clear": "true",
                    "data-language": get_select2_language(),
                }
                return forms.ModelMultipleChoiceField(
                    queryset=related_model.objects.none(),
                    label=model_field.verbose_name,
                    required=False,
                    initial=initial,
                    widget=MultipleChoiceFilterWidget(attrs=attrs),
                )
            else:
                return forms.IntegerField(
                    label=model_field.verbose_name,
                    required=False,
                    initial=initial,
                    widget=forms.HiddenInput(),
                )

        return None

    def get_filter_queryset(self) -> dict[str, Any]:
        """应用过滤条件"""
        form = self.get_filter_form()
        _filter = {}
        if form and form.is_valid():
            for field_name, value in form.cleaned_data.items():
                if not value:
                    continue

                # 处理日期范围过滤
                if isinstance(value, str) and "::" in value:  # 改回使用 '::' 判断
                    field_name, date_range = value.split("::")
                    if date_range:
                        try:
                            start_date, end_date = date_range.split(" - ")
                            start_date = datetime.strptime(
                                start_date.strip(), "%Y-%m-%d"
                            )
                            end_date = datetime.strptime(
                                end_date.strip(), "%Y-%m-%d 23:59:59"
                            )
                            _filter.update(
                                {
                                    f"{field_name}__range": (start_date, end_date),
                                }
                            )
                        except (ValueError, AttributeError):
                            pass
                # 处理多选过滤
                elif isinstance(value, (list, tuple, set, models.QuerySet)):
                    if value:
                        # 确保值的唯一性
                        unique_values = list(dict.fromkeys(value))
                        _filter.update({f"{field_name}__in": unique_values})
                # 处理其他过滤条件
                else:
                    _filter.update({field_name: value})
        else:
            logger.debug(f"{self.model._meta.model_name} filter form is not valid.")
        return _filter

    def get_context_data(self, **kwargs):
        """添加过滤表单到上下文"""
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.get_filter_form()
        return context


class ListViewMixin(HtmxResponseMixin, PermissionRequiredMixin, FilterMixin, ListView):
    """列表视图 Mixin
    """

    opts: Options | None = None
    search_fields: list[str] = []
    filter_fields: list[str] = []
    ordering = ["-id"]  # 添加默认排序
    list_fields: list[str] = []  # 添加这个类属性来定义基础列表字段
    paginate_by = DEFAULT_PER_PAGE  # 添加这个默认值
    empty_value_display = "-"  # 添加空值显示默认值
    extra_urls: list[dict] = []
    custom_fields_maps: dict | None = None

    def get_permission_required(self) -> tuple[Never]:
        codename = get_permission_codename("view", self.opts)
        self.permission_required = f"{self.opts.app_label}.{codename}"
        return super().get_permission_required()

    def get_template_names(self) -> list[str]:
        """根据请求类型返不同的模板
        """
        model_name = camel_to_snake(self.opts.object_name)
        if self.request.htmx:
            return [f"{model_name}/list_htmx.html", "list_htmx.html"]
        else:
            return [f"{model_name}/list.html", "list.html"]

    def get_table_headers(self) -> list[dict]:
        """获取表头配置"""
        current_ordering = self.get_ordering()
        can_sort_fields = [
            f.name for f in self.opts.fields if not f.many_to_many and not f.one_to_many
        ]
        headers = []
        for field in self._get_list_fields():
            classes = ["col-" + field]
            if field in ["first", "second", "last"]:
                header = {
                    "field": field,
                    "label": self.get_special_field_label(field),
                    "sortable": False,
                    "sort_url": "",
                    "sort_icon": "",
                    "remove_url": "",
                    "sort_tooltip": "",
                    "classes": " ".join(classes),
                }
                headers.append(header)
                continue
            else:
                # 处理常规模型段
                try:
                    field_obj = self.opts.get_field(field)
                    if isinstance(field_obj, GenericForeignKey):
                        raise AttributeError
                    classes = ["col-" + field]
                    if field in can_sort_fields:
                        is_sorted = (
                            field in current_ordering or f"-{field}" in current_ordering
                        )
                        header = {
                            "field": field,
                            "label": field_obj.verbose_name,
                            "sortable": True,
                            "sort_url": self.get_sort_url(field, current_ordering),
                            "sort_icon": self.get_sort_icon(field, current_ordering),
                            "remove_url": (
                                self.get_remove_sort_url(field, current_ordering)
                                if is_sorted
                                else ""
                            ),
                            "sort_tooltip": self.get_sort_tooltip(
                                field, current_ordering
                            ),
                            "classes": " ".join(
                                classes + (["sorted"] if is_sorted else [])
                            ),
                        }
                    else:
                        header = {
                            "field": field,
                            "label": field_obj.verbose_name,
                            "sortable": False,
                            "sort_url": "",
                            "sort_icon": "",
                            "remove_url": "",
                            "sort_tooltip": "",
                            "classes": " ".join(classes),
                        }
                except (FieldDoesNotExist, AttributeError):
                    label = lookup_field_verbose(
                        self.model, self.custom_fields, field, self.custom_fields_maps
                    )
                    header = {
                        "field": field,
                        "label": label,
                        "sortable": False,
                        "sort_url": "",
                        "sort_icon": "",
                        "remove_url": "",
                        "sort_tooltip": "",
                        "classes": f"col-{field}",
                    }

            headers.append(header)
        return headers

    def render_table_rows(self, objects: QuerySet) -> Generator[dict, None, None]:
        """渲染表格行（使用生成器）"""
        fields = [h["field"] for h in self.table_headers]
        for index, obj in enumerate(objects, start=1):
            # 使用 lookup 批量获取字段值
            field_values = self.lookup.get_field_values(obj, html=True)

            cells = []
            for field in fields:
                # 处理特殊字段
                if field == "first":
                    value = format_html(
                        '<input type="checkbox" name="pk" value="{}">', obj.pk
                    )
                elif field == "second":
                    value = f"{index}."
                elif field == "last":
                    value = self.render_row_actions(obj)

                else:
                    # 使用 lookup 获取的值
                    value = field_values.get(field, self.empty_value_display)

                cells.append(
                    {
                        "field": field,
                        "value": value,
                        "classes": f"field-{field} text-nowrap",
                    }
                )

            yield {"pk": obj.pk, "cells": cells}

    def render_row_actions(self, obj: Model) -> str:
        """渲染行操作按钮"""
        actions = []

        # 编辑按钮
        base_href = f"{camel_to_snake(self.opts.object_name)}"
        codename = (
            f"{self.opts.app_label}.{get_permission_codename('change', self.opts)}"
        )
        can_change = self.request.user.has_perm(codename)
        if can_change:
            try:
                href = reverse(
                    f"{base_href}_update", args=[getattr(obj, self.opts.pk.attname)]
                )
            except Exception:
                href = "#"
            if not href == "#":
                actions.append(
                    format_html(
                        '<a href="{}" title="编辑">'
                        '<span class="label label-warning margin-r-5">编辑</span></a>',
                        href,
                    )
                )

        # 删除按钮
        codename = (
            f"{self.opts.app_label}.{get_permission_codename('delete', self.opts)}"
        )
        can_delete = self.request.user.has_perm(codename)
        if can_delete:
            try:
                href = reverse(
                    f"{base_href}_delete", args=[getattr(obj, self.opts.pk.attname)]
                )
            except Exception:
                href = "#"
            if not href == "#":
                actions.append(
                    format_html(
                        '<a href="{}" title="删除">'
                        '<span class="label label-danger">删除</span></a>',
                        href,
                    )
                )
        template = """
          <div class="btn-group" style="display: inline-flex;">
    <button type="button" class="btn btn-warning btn-xs"><i class="fa fa-pencil"></i></button>
    <button type="button" class="btn btn-warning btn-xs dropdown-toggle" data-toggle="dropdown" aria-expanded="true">
      <span class="caret"></span>
      <span class="sr-only">Toggle Dropdown</span>
    </button>
    <ul class="dropdown-menu dropdown-menu-right" role="menu">
      <li><a href="#">操作1</a></li>
      <li><a href="#">操作2</a></li>
      <li><a href="#">操作3</a></li>
      <li class="divider"></li>
      <li><a href="#">分隔操作</a></li>
    </ul>
  </div>"""
        # return format_html(template)
        return mark_safe("".join(actions))

    def get_config_field_label(self, field: str) -> str:
        """获取配置字段的标签"""
        field_config_url = reverse(
            "user_field_config", args=[self.opts.model_name, "list"]
        )
        template = """<span class="margin-r-5">操作</span> <span
            class="no-print hidden-xs"
            style="cursor: pointer; margin-left: 10px; padding: 0 10px;"
            id="field-config-toggle"
            data-toggle="control-sidebar"
            data-drawer-width="960"
            data-drawer-title="字段显示&排序配置"
            hx-get="{}"
            hx-push-url="false"
            hx-target=".drawer-content">
            <i class="fa fa-cog"></i>
        </span>
        """
        return template.format(field_config_url)

    def get_special_field_label(self, field: str) -> str:
        """获取特殊字段的标签"""
        if field == "first":
            return format_html('<input type="checkbox" class="checkbox-toggle">')
        elif field == "second":
            return "#"
        elif field == "last":
            return format_html(self.get_config_field_label(field))
        return ""

    def _build_url_with_params(self, base_url: str, params: dict) -> str:
        """构建带参数的 URL"""
        query_params = self.request.GET.copy()
        for key, value in params.items():
            if value is None:
                query_params.pop(key, None)
            else:
                query_params[key] = value

        if query_params:
            return f"{base_url}?{query_params.urlencode(safe=ORDERING_SEP)}"
        return base_url

    def get_sort_url(self, field: str, current_ordering: list[str]) -> str:
        """生成排序 URL"""
        current_ordering = [
            f for f in current_ordering if f.lstrip("-") in self.get_list_fields()
        ]

        is_sorted = field in current_ordering or f"-{field}" in current_ordering
        is_desc = f"-{field}" in current_ordering

        orders = current_ordering.copy()
        if is_sorted:
            old_order = f"-{field}" if is_desc else field
            new_order = field if is_desc else f"-{field}"
            if old_order in orders:
                orders[orders.index(old_order)] = new_order
        else:
            orders.append(field)

        return self._build_url_with_params(
            self.request.path,
            {ORDERING_PARAM: ORDERING_SEP.join(orders) if orders else None},
        )

    def get_remove_sort_url(self, field: str, current_ordering: list[str]) -> str:
        """生成移除排序 URL"""
        orders = [
            f
            for f in current_ordering
            if f.lstrip("-") in self.get_list_fields() and f.lstrip("-") != field
        ]

        return self._build_url_with_params(
            self.request.path,
            {ORDERING_PARAM: ORDERING_SEP.join(orders) if orders else None},
        )

    def get_sort_tooltip(self, field: str, current_ordering: list[str]) -> str:
        """获取排序提示文本"""
        is_sorted = field in current_ordering or f"-{field}" in current_ordering
        is_desc = f"-{field}" in current_ordering
        try:
            field_obj = self.opts.get_field(field)
            help_text = field_obj.help_text
        except (FieldDoesNotExist, AttributeError):
            if is_sorted:
                help_text = "点击切换升序/降序" if is_desc else "点击切换降序/升序"
            else:
                help_text = "点击排序"
        return help_text

    def get_sort_icon(self, field: str, current_ordering: list[str]) -> str:
        """获取排序图标"""
        is_sorted = field in current_ordering or f"-{field}" in current_ordering
        is_desc = f"-{field}" in current_ordering

        if is_sorted:
            # 已排序状态，显当前排序方向
            return format_html(
                '<i class="fa fa-sort-alpha-{}" title="{}"></i>',
                "desc" if is_desc else "asc",
                "降序" if is_desc else "升序",
            )
        return ""

    @property
    def table_headers(self):
        return self.get_table_headers()

    @cached_property
    def lookup(self):
        """获取字段处理器"""
        if not hasattr(self, "_lookup"):
            self._lookup = LookupFields(
                model=self.model,
                fields=self.get_list_fields(),
                custom_fields=self.custom_fields,
                empty_value_display=self.empty_value_display,
                primary_link=True,
            )
        return self._lookup

    @cached_property
    def custom_fields(self) -> QuerySet["CustomField"]:
        """获取当前模型的自定义字段"""
        if not self.has_model:
            return CustomField.objects.none()
        if not hasattr(self, "_custom_fields"):
            self._custom_fields = CustomField.objects.filter(
                data_center=self.request.user.data_center,
                object_types=ContentType.objects.get_for_model(self.model),
                ui_visible=CustomFieldVisibilityChoices.LIST_AND_DETAIL,
            )
            self.custom_fields_maps = {
                field.name: field for field in self._custom_fields
            }
        return self._custom_fields

    def _get_list_fields(self) -> list[str]:
        """获取所有列表字段，包括 first、second 和自定义字段，确保 last 在最后
        """
        fields = ["first", "second"]  # 确保这两个特殊字段在最前面
        fields.extend(self.get_list_fields())
        fields.append("last")  # 确保 last 在最后
        return fields

    def get_list_fields(self) -> list[str]:
        """获取列表字段，包含用户配置字段"""
        user = self.request.user
        default_fields = [
            field.name
            for field in self.opts.fields
            if isinstance(field, (models.CharField, models.SlugField))
        ]
        # 从用户配置中获取
        if hasattr(user, "configure") and user.configure:
            list_config_key = f"list.{camel_to_snake(self.opts.object_name)}"
            configure = user.configure.get(list_config_key, {})
            if configure:
                return configure
        # 如果没有用户配置，使用默认字段
        fields = self.list_fields or default_fields
        return fields

    def get_htmx_push_url(self):
        """获取推送 URL"""
        url = super().get_htmx_push_url()

        ordering = self.request.GET.get(ORDERING_PARAM, "")
        if ordering:
            list_fields = self.get_list_fields()
            ordering_fields = [f.lstrip("-") for f in ordering.split(ORDERING_SEP)]

            if not any(field in list_fields for field in ordering_fields):
                return self._build_url_with_params(url, {ORDERING_PARAM: None})

        return self._build_url_with_params(url, {})

    def get_filter_by(self) -> dict[str, Any]:
        """获取过滤条件"""
        # 默认过滤条件
        filters = {}
        model_field_map = {
            f.name: f.attname for f in self.opts.fields + self.opts.many_to_many
        }
        for field_name, value in model_field_map.items():
            if field_name in self.request.GET:
                _value = self.request.GET.getlist(field_name)
                if _value and _value != "all":
                    filters[f"{value}__in"] = _value
                if "__isnull" in field_name:
                    filters[value] = str2bool(_value)
        return filters

    def get_search_form(self) -> SearchForm:
        """获取搜索表单"""
        form = SearchForm(
            model=self.model,
            search_fields=self.search_fields,
            data_center=self.request.user.data_center,
            data=self.request.GET or None,
        )
        return form

    def optimize_queryset(self, queryset: QuerySet) -> QuerySet:
        """优化查询集"""
        list_fields = self.get_list_fields()
        select_related: list[str] = [
            f.name
            for f in self.opts.fields
            if f.is_relation and f.many_to_one and f.name in list_fields
        ]
        prefetch_related: list[str] = [
            f.name
            for f in self.opts.get_fields()
            if f.is_relation and f.many_to_many and f.name in list_fields
        ]
        defer_fields: list[str] = [
            f"{f.name}__{field}"
            for f in self.opts.fields
            if f.is_relation and f.many_to_one
            for field in [
                "created_by",
                "updated_by",
                "data_center",
                "custom_field_data",
                "updated_at",
                "created_at",
                # "configure",
            ]
            if hasattr(f.related_model, field)
        ]
        if select_related:
            queryset = queryset.select_related(*select_related)
        if prefetch_related:
            queryset = queryset.prefetch_related(*prefetch_related)
        return queryset.defer(*defer_fields)

    def get_queryset(self) -> QuerySet:
        """获取查询集"""
        # 限制查询
        default_filter = models.Q()
        if is_model_field(self.model, "data_center") and self.request.user.data_center:
            default_filter |= models.Q(data_center=self.request.user.data_center)
        if hasattr(self.model, "shared"):
            default_filter |= models.Q(shared=True)
        queryset = self.model._default_manager.filter(default_filter)
        # 添加过滤
        # _filter = self.get_filter_queryset()
        _filter = self.get_filter_by()
        if _filter:
            queryset = queryset.filter(**_filter)
        queryset = self.optimize_queryset(queryset)
        # 添加搜索条件
        search_query = self.get_search_form().get_search_query()
        if search_query:
            queryset = queryset.filter(search_query).distinct()
        # 添加排序
        ordering = self.get_ordering()
        # 添加排序
        if ordering:
            if isinstance(ordering, str):
                ordering = (ordering,)
            queryset = queryset.order_by(*ordering)
        else:
            # 如果没有指定排序，使用默认排序
            queryset = queryset.order_by(*self.ordering)
        return queryset

    def post(self, request, *args, **kwargs):
        """处理 POST 请求"""
        return self.htmx_post(request, *args, **kwargs)

    def htmx_post(self, request, *args, **kwargs):
        """处理来自 action post 请求
        """
        action_type = request.POST.get("action")
        if request.POST.get("_all"):
            pk_list = [obj.pk for obj in self.get_queryset()]
        else:
            pk_list = [int(pk) for pk in request.POST.getlist("pk")]
        executor = ActionExecutor(self.request, self.model, action_type)
        instances = self.get_queryset().filter(id__in=pk_list)
        if not instances.exists():
            add_message(request, messages.WARNING, _("没有选择任何对象"))
            return self.htmx_get(request)
        result = executor.execute(self.request, instances=instances)
        # 直接返回get请求的响应
        if result and isinstance(result, HttpResponseBase):
            return result
        return self.htmx_get(request)

    def htmx_get(self, request, *args, **kwargs):
        """处理 HTMX GET 请求"""
        self.object_list = self.get_queryset()
        context = self.get_context_data()
        content = render_to_string(
            template_name=self.get_template_names(),
            context=context,
            request=self.request,
        )
        return HttpResponse(content)

    def get_paginate_by(self, queryset):
        """获取分页大小（带参数验证）"""
        PAGINATION_PER_PAGE = self.request.user.get_config(
            "PAGINATION_PER_PAGE", DEFAULT_PER_PAGE
        )
        try:
            per_page = self.request.GET.get(PAGINATE_BY_PARAM, PAGINATION_PER_PAGE)
            per_page = int(per_page)
            if per_page < 1:
                per_page = PAGINATION_PER_PAGE
            elif per_page > MAX_PAGE_SIZE:
                per_page = MAX_PAGE_SIZE
            return per_page
        except (TypeError, ValueError):
            return PAGINATION_PER_PAGE

    def make_paginate_nav(self):
        """生成分页导航"""
        per_page_size = [25, 50, 100, 200, 500]
        nav_html = ""
        for per in per_page_size:
            if per > MAX_PAGE_SIZE:
                break
            params = self.get_query_string(remove_keys=[PAGINATE_BY_PARAM])
            url = f"{self.request.path}?{params}&{PAGINATE_BY_PARAM}={per}"
            nav_html += f'<li><a href="{url}" hx-get="{url}" hx-swap="innerHTML show:window:top" hx-target="#list-post-form" hx-push-url="true">每页显示{per}条</a></li>'
        return nav_html

    def get_ordering(self):
        """获取排序字段列表"""
        ordering = self.request.GET.get(ORDERING_PARAM, "")  # 已修改
        if ordering:
            # 使用 ORDERING_SEP 常量分割排序字段
            order_fields = [x for x in ordering.split(ORDERING_SEP) if x]  # 已修改

            # 获取可排序的列表字段
            list_fields = self.get_list_fields()

            # 只保留在列表字段中的排序字段
            valid_order_fields = [
                field for field in order_fields if field.lstrip("-") in list_fields
            ]

            if valid_order_fields:
                return list(
                    filter(lambda x: x not in self.opts.ordering, valid_order_fields)
                )
        return self.opts.ordering or self.ordering

    def get_query_string(self, remove_keys: list[str] = []) -> str:
        """获取查询参数，并移除指定键"""
        query_params = self.request.GET.copy()
        for key in remove_keys:
            query_params.pop(key, None)
        return query_params.urlencode(safe=ORDERING_SEP)

    def get_extra_urls(self, request):
        """返回扩展urls列表，
        配置如下：
        extra_urls = [
            {
                "name": "room_rack_maps",
                "lable": "房间机柜视图",
                "url": reverse_lazy("room_rack_maps"),
                "icon": "fa fa-building-o",
                "next_url": next_url, # update this key
            },
        ]
        """
        if not self.extra_urls:
            return
        next_url = request.GET.get("next_url")
        for extra_url in self.extra_urls:
            if next_url:
                extra_url.update(dict(next_url=next_url))
        return self.extra_urls

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        objects = context.get("object_list")
        # 无论是否是 HTMX 请求，都添加表格数据
        context["table_headers"] = self.table_headers
        context["table_rows"] = self.render_table_rows(objects)
        # 添加过滤表单
        context["filter_form"] = self.get_filter_form()
        # 添加分页数据
        context["per_page_li"] = self.make_paginate_nav()

        import_view = registry["imports"].get(self.opts.label, None)

        context["has_import"] = import_view is not None
        if import_view:
            model_name = camel_to_snake(self.model._meta.object_name)
            context["import_url"] = reverse(f"{model_name}_import")
        # 添加当前查询参数
        if self.request.GET:
            query_params = self.get_query_string(remove_keys=["page"])
            context["current_params"] = query_params
        context["extra_urls"] = self.get_extra_urls(self.request)
        return context
