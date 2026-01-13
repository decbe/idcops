from django.contrib.auth.models import AbstractUser, Permission, UserManager
from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
)
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from .choices import ChangeActionChoices
from .mixins import BaseModel, ConfigurableMixin
from .tracking import TrackingModelMixin
from .utils import upload_to

__all__ = ["User", "Group"]


class GroupManager(models.Manager):
    """The manager for the auth's Group model.
    """

    use_in_migrations = True

    def get_by_natural_key(self, data_center, name):
        return self.get(data_center=data_center, name=name)


class Group(BaseModel):
    """自定义用户组模型，支持数据中心隔离
    """

    data_center = models.ForeignKey(
        "DataCenter",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("数据中心"),
        help_text=_("用户组所属的数据中心"),
    )
    name = models.CharField(
        max_length=150,
        verbose_name=_("名称"),
    )
    permissions = models.ManyToManyField(
        Permission,
        blank=True,
        related_name="group_permissions",
        related_query_name="group",
        verbose_name=_("权限"),
        help_text=_("该组具有的特定权限"),
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("描述"),
    )

    display_link_field = "name"
    _icon = "fa fa-users"
    search_fields = ["name"]

    objects = GroupManager()

    class Meta:
        verbose_name = _("用户组")
        verbose_name_plural = _("用户组")
        unique_together = [["name", "data_center"]]
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.name}"

    def natural_key(self):
        return (self.data_center, self.name)


class CustomUserManager(UserManager):
    def get_by_natural_key(self, username):
        return self.get(**{self.model.USERNAME_FIELD: username})

    def get_queryset(self) -> models.QuerySet:
        # 默认添加 select_related('data_center') 以优化查询
        return super().get_queryset().select_related("data_center")


class User(BaseModel, AbstractUser, ConfigurableMixin, TrackingModelMixin):
    """用户模型"""

    data_centers = models.ManyToManyField(
        "DataCenter",
        related_name="users",
        blank=True,
        verbose_name=_("数据中心"),
        help_text=_("用户可以访问的数据中心"),
    )
    data_center = models.ForeignKey(
        "DataCenter",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("默认数据中心"),
        help_text=_("用户当前所在的数据中心"),
    )
    leader = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("上级"),
    )
    mobile = models.CharField(
        max_length=15,
        unique=True,
        null=True,
        blank=True,
        verbose_name=_("手机号"),
    )
    avatar = models.ImageField(
        upload_to=upload_to,
        null=True,
        blank=True,
        verbose_name=_("头像"),
    )
    configure = models.JSONField(
        default=dict,
        blank=True,
        null=True,
        verbose_name=_("用户配置"),
        help_text=_("存储用户扩展配置，例如：语言、菜单布局、列表字段顺序、操作权限等"),
    )
    groups = models.ManyToManyField(
        Group,
        blank=True,
        related_name="groups",
        related_query_name="group",
        verbose_name=_("用户组"),
        help_text=_("用户所属的组。一个用户将获得其所属组的所有权限"),
    )

    objects = CustomUserManager()

    form_help_mode = False

    _icon = "fa fa-user"
    display_link_field = "username"
    search_fields = ["username", "email", "mobile"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["-pk"]

    def clean(self):
        super().clean()
        model = self._meta.model
        if (
            model.objects.exclude(pk=self.pk)
            .filter(username__iexact=self.username)
            .exists()
        ):
            raise ValidationError(_("A user with this username already exists."))

    # def save(self, *args, **kwargs):
    #     # 保存时清除缓存
    #     super().save(*args, **kwargs)
    #     UserConfigureCache.delete(self.id)

    def get_configure(self) -> dict:
        """获取configure(带缓存)"""
        return self.configure or {}

    def set_configure(self, configure: dict):
        """设置configure"""
        swap_configure = self.configure.copy()
        swap_configure.update(configure)
        self.configure = swap_configure
        self.save()

    def get_action_permissions(self) -> dict:
        """获取action权限配置(带缓存)"""
        if self.is_superuser:
            return {"*": True}  # 超级用户拥有所有权限
        return self.get_configure().get("actions", {})

    @property
    def avatar_url(self) -> str:
        """获取头像URL"""
        if self.avatar and self.avatar.name:
            try:
                return self.avatar.url
            except ValueError:
                # 处理文件不存在的情况
                pass
        return "/static/adminlte/img/avatar04.png"

    def set_action_permissions(self, permissions: dict):
        """设置action权限"""
        configure = self.get_configure()
        actions = configure.get("actions", {})
        actions.update(permissions)
        configure["actions"] = actions
        self.set_configure(configure)


@receiver(user_logged_in)
def user_logged_in_handler(sender, user, request, **kwargs):
    """当用户登录时，记录登录日志
    """
    if not user:
        return
    if not user.data_center:
        return
    extra_data = {
        "ipaddr": getattr(request, "ipaddr", "") or "",
        "user_agent": request.META.get("HTTP_USER_AGENT"),
    }
    from dcrm.models import LogEntry

    LogEntry.objects.log_action(
        user=user,
        action_type=_("user_login"),
        action=ChangeActionChoices.ACTION_LOGIN,
        object_repr=user,
        message=f"登录成功: ({user.username})",
        extra_data=extra_data,
    )


# @receiver(user_login_failed)
# def user_login_failed_handler(sender, credentials, request, **kwargs):
#     """
#     当用户登录失败时，记录登录失败日志
#     """
#     ipaddr = getattr(request, 'ipaddr', '') or ''
#     user_agent = request.META.get('HTTP_USER_AGENT')
#     from django.contrib.auth.models import AnonymousUser
#     user = request.user
#     if not user.is_authenticated:
#         user = AnonymousUser()
#         user.username = 'AnonymousUser'
#     from dcrm.actions import log_action
#     log_action(user, 'login_failed', ipaddr=ipaddr, user_agent=user_agent)


@receiver(user_logged_out)
def user_logged_out_handler(sender, user, request, **kwargs):
    """当用户退出登录时，记录退出登录日志
    """
    if not user:
        return
    if not user.data_center:
        return
    extra_data = {
        "ipaddr": getattr(request, "ipaddr", "") or "",
        "user_agent": request.META.get("HTTP_USER_AGENT"),
    }
    from dcrm.models import LogEntry

    LogEntry.objects.log_action(
        user=user,
        action_type=_("user_logged_out"),
        action=ChangeActionChoices.ACTION_LOGOUT,
        object_repr=user,
        message=f"退出登录: ({user.username})",
        extra_data=extra_data,
    )


# 信号接收器 - 在创建用户后初始化默认配置
@receiver(post_save, sender=User)
def initialize_user_configs(sender, instance, created, **kwargs):
    """当创建新用户时，自动初始化默认配置
    """
    if created:
        instance.initialize_default_configs()
