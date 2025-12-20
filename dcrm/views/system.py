import json
import logging
from collections import namedtuple
from typing import Any, Optional

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import models
from django.db.models.fields.reverse_related import ManyToManyRel
from django.http.response import HttpResponseRedirect, JsonResponse
from django.urls import reverse, reverse_lazy
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)

from dcrm import models as dcrm_models
from dcrm.forms.config import ConfigParamForm
from dcrm.forms.users import GroupForm, UserCreateForm, UserProfileForm, UserUpdateForm
from dcrm.models import CustomField, Group, User
from dcrm.models.base import DataCenter
from dcrm.models.choices import CustomFieldVisibilityChoices
from dcrm.params import CONFIG_GROUPS, DYNAMIC_SETTINGS
from dcrm.utilities.base import camel_to_snake, lookup_field_verbose
from dcrm.utilities.lookup import get_model_view_url_name, get_view_info_by_url_name

from .mixins.base import BaseRequestMixin, HtmxResponseMixin
from .mixins.delete import DeleteViewMixin
from .mixins.detail import DetailViewMixin
from .mixins.edit import CreateViewMixin, FieldSet, UpdateViewMixin
from .mixins.list import ListViewMixin

logger = logging.Logger(__name__)

__all__ = [
    "GroupListView",
    "GroupCreateView",
    "GroupUpdateView",
    "GroupDetailView",
    "GroupDeleteView",
    "ConfigurationView",
]


class GroupListView(BaseRequestMixin, ListViewMixin, ListView):
    model = Group
    list_fields = [
        "name",
        "description",
    ]


class GroupCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = Group
    template_name = "users/group_form.html"
    form_class = GroupForm

    def get_success_url(self):
        return reverse("group_list")


class GroupUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = Group
    template_name = "users/group_form.html"
    form_class = GroupForm

    def get_success_url(self):
        return reverse("group_list")


class GroupDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = Group
    template_name = "users/group_detail.html"
    fields = ["name", "description"]
    fieldsets = [{"title": _("基本信息"), "fields": ["name", "description"]}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = GroupForm(
            **{"request": self.request, "instance": self.object}
        )
        return context


class GroupDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    model = Group

    def get_success_url(self):
        return reverse("group_list")


class UserListView(BaseRequestMixin, ListViewMixin, ListView):
    model = User
    list_fields = [
        "username",
        "email",
        "mobile",
        "leader",
        "data_center",
        "is_active",
        "is_superuser",
        "last_login",
        "groups",
        "date_joined",
    ]


class UserCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = User
    form_class = UserCreateForm
    fieldsets = [
        FieldSet(
            "用户信息",
            fields=[
                "username",
                "password1",
                "password2",
                "email",
                "mobile",
            ],
        ),
        FieldSet("权限信息", fields=["is_active", "groups", "leader", "data_centers"]),
    ]


class UserUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    fieldsets = [
        FieldSet(
            "用户信息",
            fields=[
                "username",
                "email",
                "mobile",
            ],
        ),
        FieldSet("权限信息", fields=["is_active", "groups", "leader", "data_centers"]),
    ]

    def get_form_kwargs(self):
        """获取表单参数"""
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs


class UserDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = User
    fields = [
        "username",
        "email",
        "groups",
        "avatar",
        "mobile",
        "data_center",
        "date_joined",
        "last_login",
        "is_active",
        "is_staff",
        "is_superuser",
        "leader",
        "data_centers",
    ]
    fieldsets = [
        {
            "title": "用户信息",
            "fields": [
                "username",
                "email",
                "avatar",
                "mobile",
                "leader",
                "data_center",
                "data_centers",
                "date_joined",
                "last_login",
            ],
        },
        {
            "title": "权限&分组",
            "fields": [
                "is_active",
                "is_staff",
                "is_superuser",
                "groups",
            ],
        },
    ]
    enable_related_objects = False


class UserDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    model = User
    success_url = reverse_lazy("user_list")


class UserCustomFieldConfigView(LoginRequiredMixin, HtmxResponseMixin, TemplateView):
    """
    用户自定义配置字段
    1. 列表，支持排序
    2. 编辑，支持字段排序
    3. url: /system/users/configure/<str:model_name>/<str:view_name>/
    """

    exclude_fields = ["id", "custom_field_data", "level", "lft", "rght", "tree_id"]
    template_name = "system/user_list_field_config.html"

    def dispatch(self, request, *args, **kwargs):
        # 视图名称，默认list
        from django.apps import apps
        from django.http import Http404

        try:
            model_name = kwargs.get("model_name")
            if model_name:
                self.model = apps.get_model("dcrm", model_name)
                self.opts = self.model._meta
        except Exception as e:
            logger.error(f"获取模型失败: {str(e)}")
            raise Http404("模型不存在")
        self.view_name = kwargs.get("view_name", "list")
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def configure_key(self):
        key = f"{self.view_name}.{camel_to_snake(self.opts.object_name)}"
        return key

    def get_user_configure(self) -> Optional[dict]:
        """
        获取当前用户的配置数据
        """
        return getattr(self.request.user, "configure", {})

    def get_success_url(self):
        url_name = get_model_view_url_name(self.model, "list")
        return reverse(url_name)

    def get_default_list_fields(self, view_type: str = "list") -> list[str]:
        """
        获取默认字段列表
        """
        url_name = get_model_view_url_name(self.model, view_type)
        view = get_view_info_by_url_name(url_name)
        if hasattr(view.func.view_class, "list_fields"):
            return view.func.view_class.list_fields
        return [f.name for f in self.opts.fields if f.name not in self.exclude_fields]

    def get_user_list_fields(self) -> list[str]:
        """
        获取用户当前配置字段
        1. 从 User 模型中的 configure JSONField 字段获取
        2. 使用默认字段列表，如果用户未配置
        3. 返回字段 List[str] field_name 列表
        """
        user_configure = self.get_user_configure()
        if user_configure and self.configure_key in user_configure:
            return user_configure[self.configure_key]
        return self.get_default_list_fields()

    def save_user_configure(self, fields: list[str]):
        """
        保存用户配置字段
        """
        user = self.request.user
        if not hasattr(user, "configure") or user.configure is None:
            user.configure = {}
        user.configure[self.configure_key] = fields
        user.save(update_fields=["configure"])
        # TODO: 使用信号量, 更新用户配置

    def post(self, request, *args, **kwargs):
        """
        处理字段排序配置的保存
        """
        # 处理重置视图默认的字段
        reset = "resetDefaultButton" in request.POST
        if reset and self.configure_key in request.user.configure:
            swap_configure = request.user.configure.copy()
            del swap_configure[self.configure_key]
            request.user.configure = swap_configure
            request.user.save(update_fields=["configure"])
            messages.success(request, _("自定义列表字段顺序已重置"))
            url_name = get_model_view_url_name(self.model, "list")
            return HttpResponseRedirect(reverse(url_name))

        try:

            field_order = json.loads(request.POST.get("field_order", "[]"))
            if isinstance(field_order, list):
                self.save_user_configure(field_order)
                url_name = get_model_view_url_name(self.model, "list")
                return HttpResponseRedirect(reverse(url_name))
            return self.render_to_response(
                self.get_context_data(error=True, message="无效的字段配置数据")
            )
        except json.JSONDecodeError:
            return self.render_to_response(
                self.get_context_data(error=True, message="字段配置数据格式错误")
            )
        except Exception as e:
            return self.render_to_response(
                self.get_context_data(error=True, message=f"保存配置失败: {str(e)}")
            )

    def custom_fields(self):
        data_center = self.request.user.data_center
        custom_fields = CustomField.objects.get_for_model(self.model, data_center)
        return custom_fields.filter(
            ui_visible=CustomFieldVisibilityChoices.LIST_AND_DETAIL
        )

    def get_model_all_fields(self) -> list[dict]:
        """
        获取模型所有可以在list中使用的字段字典列表
        """
        model_fields = [
            f.name
            for f in self.model._meta.get_fields()
            if f.name not in self.exclude_fields
            and not f.one_to_many
            and not type(f) == ManyToManyRel
        ]
        default_fields = self.get_default_list_fields()
        custom_fields = [field.name for field in self.custom_fields()]
        fields = list(set(model_fields).union(default_fields).union(custom_fields))
        return self.lookup_fields(fields)

    def lookup_fields(self, fields: list[str]) -> list[dict]:
        """
        解析字段列表, 获取字段信息
        """

        def get_field_type(field_name):
            try:
                field = self.model._meta.get_field(field_name)
                if hasattr(field, "get_internal_type"):
                    field_type = field.get_internal_type()
                else:
                    field_type = "ExtraField"
            except FieldDoesNotExist:
                field_type = "ExtraField(remote or short description)"
            return field_type

        field_list = [
            {
                "name": field_name,
                "label": lookup_field_verbose(
                    self.model, self.custom_fields(), field_name
                ),
                "type": get_field_type(field_name),
            }
            for field_name in fields
        ]
        return field_list

    def htmx_get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["all_fields"] = self.get_model_all_fields()
        context["current_fields"] = self.lookup_fields(self.get_user_list_fields())
        context["default_fields"] = self.get_default_list_fields()
        context["can_reset"] = self.configure_key in self.request.user.configure
        return context


class UserProfileView(BaseRequestMixin, HtmxResponseMixin, UpdateView):
    model = User
    template_name = "system/user_profile.html"
    form_class = UserProfileForm
    success_url = reverse_lazy("user_profile")

    def get_object(self) -> Any:
        return self.request.user

    def post(self, request, *args, **kwargs):
        """处理POST请求，支持Ajax头像上传"""
        # 如果是Ajax头像上传请求
        if (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            and "avatar" in request.FILES
        ):
            return self.handle_avatar_upload(request)

        # 否则进行正常的表单处理
        return super().post(request, *args, **kwargs)

    def handle_avatar_upload(self, request):
        """处理Ajax头像上传"""
        try:
            user = request.user
            avatar_file = request.FILES["avatar"]

            # 验证文件类型
            if not avatar_file.content_type.startswith("image/"):
                return JsonResponse(
                    {"success": False, "message": "请上传有效的图片文件"}
                )

            # 验证文件大小 (5MB)
            if avatar_file.size > 5 * 1024 * 1024:
                return JsonResponse(
                    {"success": False, "message": "头像文件不能超过5MB"}
                )

            # 保存旧头像以便删除
            old_avatar = user.avatar

            # 更新头像
            user.avatar = avatar_file
            user.save()

            # 刷新用户对象以获取最新的头像URL
            user.refresh_from_db()

            # 使用 avatar_url 属性获取正确的头像URL
            avatar_url = user.avatar_url

            # 删除旧头像文件
            if old_avatar:
                try:
                    old_avatar.delete(save=False)
                except Exception:
                    pass  # 忽略删除失败

            # 记录操作日志
            from dcrm.models.base import LogEntry
            from dcrm.models.choices import ChangeActionChoices

            LogEntry.objects.log_action(
                user=request.user,
                action=ChangeActionChoices.UPDATE,
                object_repr=user,
                message=_("{} 更新了头像").format(user.username),
                action_type="update_avatar",
                extra_data={
                    "ipaddr": getattr(request, "ipaddr", "") or "",
                    "user_agent": request.META.get("HTTP_USER_AGENT", ""),
                },
            )

            return JsonResponse(
                {
                    "success": True,
                    "message": "头像更新成功",
                    "avatar_url": avatar_url,
                }
            )

        except Exception as e:
            return JsonResponse(
                {"success": False, "message": f"头像上传失败：{str(e)}"}
            )

    def change_data_center(self) -> None: ...

    def get_logentries(self) -> list:
        """
        获取用户日志条目并按日期分组，使用高效方法减少查询次数
        返回格式: [{'date': date_obj, 'data': queryset}, ...]
        """
        # from django.db.models.functions import TruncDate
        # from collections import defaultdict

        logs = dcrm_models.LogEntry.objects.filter(
            created_by=self.request.user, data_center=self.request.user.data_center
        )

        # 获取所有唯一的日期（按日期截断）
        dates = logs.datetimes("created_at", "hour", "DESC")[:2]

        # 获取所有日志条目（一次性查询）
        all_logs = logs.select_related().order_by("-created_at")
        # 构建结果列表
        result = []
        for date in dates:
            query = dict(
                created_at__year=date.year,
                created_at__month=date.month,
                created_at__day=date.day,
                created_at__hour=date.hour,
            )
            result.append({"date": date, "data": all_logs.filter(**query)})
        return result

    def get_related_objects(self) -> list:
        """获取对象的所有关联对象配置"""

        related_models = [
            dcrm_models.Device,
            dcrm_models.Rack,
            dcrm_models.Room,
            dcrm_models.NetworkProduct,
            dcrm_models.IPAddress,
            dcrm_models.VLAN,
            dcrm_models.Subnet,
            dcrm_models.DeviceModel,
            dcrm_models.Manufacturer,
            dcrm_models.Tenant,
            dcrm_models.InventoryItem,
            dcrm_models.ItemCategory,
            dcrm_models.PatchCord,
            dcrm_models.Tag,
            dcrm_models.CodingRule,
            dcrm_models.CustomField,
            dcrm_models.Group,
            dcrm_models.LogEntry,
        ]
        related_objects = []

        # 获取所有关联字段
        for field in self.model._meta.get_fields():

            if isinstance(
                field, (models.ForeignKey, models.ManyToManyField, models.OneToOneField)
            ):
                continue

            # 处理反向关系
            if field.auto_created and field.is_relation:
                related_model = field.related_model
                if related_model not in related_models:
                    continue
                # 获取关联模型的列表视图URL
                try:
                    model_name = camel_to_snake(related_model._meta.object_name)
                    url_name = f"{model_name}_list"
                    list_url = reverse(url_name)

                    related_objects.append(
                        {
                            "name": field.name,
                            "model": related_model,
                            "verbose_name": field.related_model._meta.verbose_name_plural,
                            "url": list_url,
                            "filter_field": field.field.name,
                            "icon": (
                                related_model._icon
                                if hasattr(related_model, "_icon")
                                else "fa fa-list"
                            ),
                        }
                    )
                except Exception as e:
                    logger.warning(f"无法获取 {related_model} 的列表URL: {str(e)}")

        return related_objects

    def form_valid(self, form) -> HttpResponseRedirect:
        response = super().form_valid(form)
        if form.changed_data:
            messages.success(self.request, "个人资料已更新")
        return response

    def get_form_kwargs(self) -> dict[str, Any]:
        """准备表单构造参数"""
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs) -> Any:
        context = super().get_context_data(**kwargs)
        objects_collections = []
        for related in self.get_related_objects():
            filter_field = related["filter_field"]
            if not filter_field == "created_by":
                continue
            if isinstance(related["model"], DataCenter):
                continue
            filter_kwargs = {
                filter_field: self.request.user,
                "data_center": self.request.user.data_center,
            }
            count = related["model"].objects.filter(**filter_kwargs).count()
            if count > 0:
                related["count"] = count
                related["url"] = related["url"] + f"?created_by={self.request.user.id}"
                objects_collections.append(related)
        context["objects_collections"] = objects_collections
        return context


class ConfigurationView(BaseRequestMixin, FormView):
    """
    批量配置视图，用于管理系统配置的基类。

    该视图允许同时编辑多个配置参数，并根据配置组提供不同的表单。

    FormView 最佳实践说明：
    1. 通常情况下，不需要覆盖 FormView 的 get 和 post 方法，而是通过其他钩子方法如
       get_form_class, get_form_kwargs, form_valid, form_invalid 来定制行为
    2. 如果需要特殊的 GET/POST 处理逻辑，应尽量在适当的钩子方法中实现，保持代码的组织性
    3. FormView 已经实现了基础的表单处理流程，应尽量复用这些逻辑
    4. 当处理多个表单或需要动态表单时，可以考虑以下方法：
       a. 使用 FormSet 来处理多个相同类型的表单
       b. 在 get_context_data 中创建额外表单
       c. 使用 MultiFormMixin 模式（需要自定义）
    """

    template_name = "system/configuration.html"
    success_url = None
    form_class = ConfigParamForm
    groups = CONFIG_GROUPS.items()

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.active_tab = (
            request.GET.get("active_tab", "user")
            if request.method == "GET"
            else request.POST.get("active_tab", "user")
        )
        self.is_system = self.active_tab.startswith("system")

    def get_form(self, form_class=None):
        """
        重写get_form方法，确保表单总是正确创建
        """
        form_class = self.get_form_class()
        kwargs = self.get_form_kwargs()
        return form_class(**kwargs)

    def form_invalid(self, form):
        """处理表单验证失败的情况"""
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(self.request, f"字段 '{field}': {error}")
        return self.render_to_response(self.get_context_data(form=form))

    def post(self, request, *args, **kwargs):
        is_ajax = request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest"
        if is_ajax and self.active_tab == "user" and "SIDEBAR_COLLAPSE" in request.POST:
            SIDEBAR_COLLAPSE = (
                True if request.POST.get("SIDEBAR_COLLAPSE") == "on" else False
            )
            updates = dict(SIDEBAR_COLLAPSE=SIDEBAR_COLLAPSE)
            self.request.user.update_configs(updates)
            return JsonResponse({"message": "已保存"})
        else:
            return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        """处理表单验证成功的情况，保存配置"""
        changed_data = form.changed_data
        if not changed_data:
            messages.info(self.request, "没有更改任何配置")
            return self.render_to_response(self.get_context_data(form=form))

        active_tab = self.request.POST.get("active_tab", "user")
        if hasattr(self.request.user, "data_center") and self.request.user.data_center:
            data_center = self.request.user.data_center
        else:
            raise ValidationError("当前用户没有关联的数据中心")

        success_updates = []
        failed_updates = []

        # 收集要更新的配置
        updates = {}

        for field_name in changed_data:
            value = form.cleaned_data[field_name]
            updates[field_name] = value
        try:
            # 根据配置类型使用不同的更新方法
            if self.active_tab.startswith("system"):
                # 系统配置使用 DataCenter 实例 代理逐个更新
                for field_name, value in updates.items():
                    try:
                        data_center.set_config(field_name, value, is_system=True)
                        success_updates.append(field_name)
                    except Exception as e:
                        failed_updates.append((field_name, str(e)))
            elif self.active_tab.startswith("datacenter"):
                # 数据中心配置批量更新
                data_center.update_configs(updates)
                success_updates.extend(updates.keys())
            elif self.active_tab.startswith("user"):
                # 用户配置批量更新
                self.request.user.update_configs(updates)
                success_updates.extend(updates.keys())
            else:
                raise ValueError(f"未知的配置类型: {active_tab}")
        except Exception as e:
            messages.error(self.request, f"更新配置失败: {str(e)}")
            return self.render_to_response(self.get_context_data(form=form))

        # 显示操作结果消息
        if success_updates:
            messages.success(
                self.request,
                f"成功更新 {len(success_updates)} 个配置",
            )

        if failed_updates:
            for field_name, error in failed_updates:
                form.add_error(field_name, error)

        return super().form_valid(form)

    def get_success_url(self):
        """获取成功提交后的跳转URL"""
        return reverse("configuration") + f"?active_tab={self.active_tab}"

    def get_form_kwargs(self):
        """准备表单构造参数"""
        kwargs = super().get_form_kwargs()

        # 根据活动的Tab获取对应的参数
        params = self.get_config_params(self.active_tab)
        values = self.get_param_values(params)

        # 更新参数
        kwargs["params"] = params
        kwargs["initial"] = values
        kwargs["user"] = self.request.user
        return kwargs

    def get_config_params(self, group_prefix):
        """
        获取指定分组前缀的配置参数

        Args:
            group_prefix: 分组前缀，例如"system"、"datacenter"等

        Returns:
            list: 配置参数对象列表
        """
        return [
            param for param in DYNAMIC_SETTINGS if param.group.startswith(group_prefix)
        ]

    def get_param_values(self, params):
        """
        获取配置参数的当前值

        Args:
            params: 配置参数列表

        Returns:
            dict: 参数名到值的映射
        """
        datacenter = self.request.user.data_center
        get_config_func = {
            "system": datacenter.get_config,
            "datacenter": datacenter.get_config,
            "user": self.request.user.get_config,
        }
        values = {}
        for param in params:
            values[param.name] = get_config_func[self.active_tab](
                param.name, param.default, self.is_system
            )
        return values

    def get_context_data(self, **kwargs):
        """
        准备模板上下文数据

        注意：根据 FormView 最佳实践，当需要多个表单时：
        1. 主表单应通过 form 参数传递（由 FormView 自动处理）
        2. 辅助表单可以在 get_context_data 中创建并添加到上下文
        3. 可以使用 setup 方法预先确定激活的选项卡，减少代码重复
        """
        context = super().get_context_data(**kwargs)
        Tab = namedtuple("Tab", ["name", "label"])
        tabs = [Tab(name, group["name"]) for name, group in self.groups]
        # 准备基本的上下文数据
        context.update(
            {
                "title": "配置管理",
                "breadcrumbs": [
                    {
                        "name": _("仪表盘"),
                        "url": reverse("index"),
                        "icon": "fa fa-dashboard",
                    },
                    {
                        "name": "配置管理",
                        "url": reverse("configuration"),
                        "icon": "fa-cogs",
                    },
                ],
                "CONFIG_GROUPS": CONFIG_GROUPS,
                "active_tab": self.active_tab,
                "tabs": tabs,
                "active_form": self.get_form().get_fields_by_group(),
            }
        )

        return context
