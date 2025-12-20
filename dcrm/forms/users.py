from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import gettext_lazy as _

from dcrm.models.users import Group, User

from .base import BaseModelFormMixin


class CreateFirstSuperUserForm(UserCreationForm):
    """首次创建超级管理员的表单"""

    email = forms.EmailField(
        label=_("电子邮箱"),
        required=True,
        widget=forms.EmailInput(attrs={"class": "form-control", "autocomplete": "off"}),
    )

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]
        widgets = {
            "username": forms.TextInput(
                attrs={"class": "form-control", "autocomplete": "off"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 设置密码字段的样式
        self.fields["password1"].widget.attrs.update(
            {"class": "form-control", "autocomplete": "new-password"}
        )
        self.fields["password2"].widget.attrs.update(
            {"class": "form-control", "autocomplete": "new-password"}
        )


class UserCreateForm(UserCreationForm, BaseModelFormMixin):
    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "email",
            "mobile",
            "groups",
            "data_centers",
            "leader",
            "is_active",
        ]

    """用户创建表单"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 优先使用类属性中存储的用户信息
        self.current_user = self.request.user
        # 设置表单字段
        self._setup_form_fields()

    def _setup_form_fields(self):
        """设置表单字段的属性和权限"""
        if self._meta.model.USERNAME_FIELD in self.fields:
            self.fields[self._meta.model.USERNAME_FIELD].widget.attrs.update(
                {"autofocus": True}
            )

        for field in self.fields:
            if field in ["password1", "password2"]:
                attrs = {"autocomplete": "new-password", "class": "form-control"}
            else:
                attrs = {"autocomplete": "off", "class": "form-control"}
            self.fields[field].widget.attrs.update(attrs)
            if isinstance(self.fields[field], forms.fields.BooleanField):
                self.fields[field].widget.attrs.update(
                    {"data-boolean": "true", "class": "checkbox"}
                )
        if self.current_user and not self.current_user.is_superuser:
            self.fields["data_centers"].queryset = self.current_user.data_centers.all()
            self.fields["groups"].queryset = self.current_user.groups.all()

    # def save(self, commit=True):
    #     user = super().save(commit=False)
    #     if commit:
    #         user.save()
    #         if user.groups:
    #             # 同步组权限到用户权限中，使用 m2m.add，避免清楚用户原有权限
    #             perms = user.groups.all().values_list("permissions__id", flat=True)
    #             if perms:
    #                 user.user_permissions.set(perms)
    #     return user


class UserUpdateForm(BaseModelFormMixin):
    """用户编辑表单"""

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "email",
            "mobile",
            "groups",
            "data_centers",
            "leader",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 优先使用类属性中存储的用户信息
        self.current_user = self.request.user
        # 设置表单字段
        self._setup_form_fields()

    def _setup_form_fields(self):
        """设置表单字段的属性和权限"""
        if self._meta.model.USERNAME_FIELD in self.fields:
            self.fields[self._meta.model.USERNAME_FIELD].widget.attrs.update(
                {"autofocus": True}
            )

        for field in self.fields:
            attrs = {"autocomplete": "off", "class": "form-control"}
            self.fields[field].widget.attrs.update(attrs)
            if isinstance(self.fields[field], forms.fields.BooleanField):
                self.fields[field].widget.attrs.update(
                    {"data-boolean": "true", "class": "checkbox"}
                )
        if self.current_user and not self.current_user.is_superuser:
            self.fields["data_centers"].queryset = self.current_user.data_centers.all()
            self.fields["groups"].queryset = self.current_user.groups.all()

    # def save(self, commit=True):
    #     user = super().save(commit=False)
    #     if commit:
    #         user.save()
    #         if user.groups:
    #             # 同步组权限到用户权限中，使用 m2m.add，避免清楚用户原有权限
    #             perms = user.groups.all().values_list("permissions__id", flat=True)
    #             if perms:
    #                 user.user_permissions.set(perms)
    #     return user


class GroupForm(BaseModelFormMixin):
    """自定义组权限管理表单"""

    class Meta:
        model = Group
        fields = ["name", "description", "permissions"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 设置基础字段属性
        for field_name in ["name", "description"]:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update(
                    {"class": "form-control", "autocomplete": "off"}
                )

        # 获取当前权限（如果是编辑现有组）
        self.current_permissions = set()
        if self.instance.pk:
            self.current_permissions = set(
                self.instance.permissions.values_list("id", flat=True)
            )

        # 准备权限表格数据
        self.permissions_table = self._prepare_permissions_table()

        # 删除原始权限字段
        if "permissions" in self.fields:
            del self.fields["permissions"]

    def _prepare_permissions_table(self):
        """准备权限表格数据"""
        table_data = []

        # 一次性查询所有dcrm应用的content types
        content_types = ContentType.objects.filter(app_label="dcrm").order_by("model")

        # 一次性查询所有权限，按content_type分组
        all_permissions = (
            Permission.objects.filter(content_type__in=content_types)
            .select_related("content_type")
            .order_by("content_type", "codename")
        )

        # 将权限按content_type分组
        permissions_by_ct = {}
        for perm in all_permissions:
            ct_id = perm.content_type_id
            if ct_id not in permissions_by_ct:
                permissions_by_ct[ct_id] = []
            permissions_by_ct[ct_id].append(perm)

        # 一次性获取用户权限
        if self.request.user.is_superuser:
            user_permissions = set(Permission.objects.values_list("id", flat=True))
        else:
            user_permissions = set(
                self.request.user.groups.all().values_list("permissions__id", flat=True)
            )

        # 处理每个content type
        for ct in content_types:
            model_class = ct.model_class()
            if not model_class:
                continue

            row = {
                "model": ct.model,
                "verbose_name": model_class._meta.verbose_name,
                "permissions": {
                    "view": None,
                    "add": None,
                    "change": None,
                    "delete": None,
                    "custom": [],
                },
            }

            # 获取当前content type的所有权限
            permissions = permissions_by_ct.get(ct.id, [])

            for perm in permissions:
                field_name = f"permission_{perm.id}"

                # 确定是否应该默认选中
                is_checked = (
                    perm.id in self.current_permissions  # 编辑时保持现有选择
                    or (
                        not self.instance.pk and perm.codename.startswith("view_")
                    )  # 新建时默认选中view权限
                )

                disabled = perm.id not in user_permissions
                # 创建复选框字段
                self.fields[field_name] = forms.BooleanField(
                    required=False,
                    initial=is_checked,
                    widget=forms.CheckboxInput(
                        attrs={
                            "class": "checkbox-input",
                            "data-perm-type": (
                                perm.codename.split("_")[0]
                                if "_" in perm.codename
                                else "custom"
                            ),
                            "disabled": disabled,
                        }
                    ),
                )

                # 根据权限类型分类
                perm_info = {
                    "field_name": field_name,
                    "name": perm.name.replace("Can ", ""),
                    "codename": perm.codename,
                }

                # 将权限放入对应类型
                if perm.codename.startswith("view_"):
                    row["permissions"]["view"] = perm_info
                elif perm.codename.startswith("add_"):
                    row["permissions"]["add"] = perm_info
                elif perm.codename.startswith("change_"):
                    row["permissions"]["change"] = perm_info
                elif perm.codename.startswith("delete_"):
                    row["permissions"]["delete"] = perm_info
                else:
                    row["permissions"]["custom"].append(perm_info)

            table_data.append(row)

        return table_data

    def save(self, commit=True):
        group = super().save(commit=False)

        if commit:
            group.save()
            group.permissions.clear()

            selected_permissions = []
            for field_name, value in self.cleaned_data.items():
                if field_name.startswith("permission_") and value:
                    permission_id = int(field_name.replace("permission_", ""))
                    selected_permissions.append(permission_id)

            if selected_permissions:
                group.permissions.add(*selected_permissions)

        return group


class UserProfileBoundField(forms.BoundField):

    custom_class = "form-group"

    def css_classes(self, extra_classes=None):
        result = super().css_classes(extra_classes)
        if self.custom_class not in result:
            result += f" {self.custom_class}"
        return result.strip()


class UserProfileForm(forms.ModelForm):
    """用户个人资料表单"""

    bound_field_class = UserProfileBoundField

    password1 = forms.CharField(
        label=_("新密码"),
        required=False,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "new-password"}
        ),
        help_text=_("如果不想修改密码，请留空"),
    )
    password2 = forms.CharField(
        label=_("确认新密码"),
        required=False,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "new-password"}
        ),
    )
    current_password = forms.CharField(
        label=_("当前密码"),
        required=False,
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "autocomplete": "off"}
        ),
        help_text=_("修改密码时需要验证当前密码"),
    )

    class Meta:
        model = User
        fields = [
            "avatar",
            "data_center",
            "username",
            "email",
            "mobile",
            "password1",
            "password2",
            "current_password",
        ]
        widgets = {
            "username": forms.TextInput(
                attrs={"class": "form-control", "autocomplete": "off"}
            ),
            "email": forms.EmailInput(
                attrs={"class": "form-control", "autocomplete": "off"}
            ),
            "mobile": forms.TextInput(
                attrs={"class": "form-control", "autocomplete": "off"}
            ),
            "data_center": forms.Select(
                attrs={"class": "form-control", "autocomplete": "off"}
            ),
            "avatar": forms.FileInput(
                attrs={
                    "class": "form-control",
                    "accept": "image/*",
                    "style": "display: none;",
                }
            ),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].disabled = True  # 用户名不允许修改
        self.fields["username"].help_text = ""
        if not user.is_superuser:
            self.fields["data_center"].queryset = user.data_centers.all()

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        current_password = cleaned_data.get("current_password")

        if password1 or password2:
            if not current_password:
                raise forms.ValidationError(_("修改密码需要验证当前密码"))

            if not self.instance.check_password(current_password):
                raise forms.ValidationError(_("当前密码不正确"))

            if password1 != password2:
                raise forms.ValidationError(_("两次输入的新密码不一致"))

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)

        # 如果提供了新密码，则更新密码
        password1 = self.cleaned_data.get("password1")
        if password1:
            user.set_password(password1)

        if commit:
            user.save()

        return user


class UserPreference(forms.Form):
    """
    用户偏好表单，根据配置参数进行渲染表单。DYNAMIC_SETTINGS
    """

    ...
