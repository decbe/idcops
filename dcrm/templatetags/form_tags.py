from django import template
from django.forms import BoundField

register = template.Library()


@register.filter
def getattribute(obj, attr):
    """获取对象的属性"""
    return getattr(obj, attr)


@register.filter
def get(dictionary, key):
    """获取字典值"""
    return dictionary.get(key, "")


@register.filter
def form_field(field, form):
    """将表单字段转换为 BoundField"""
    return BoundField(
        form,
        field,
        (
            field.html_name
            if hasattr(field, "html_name")
            else field.name if hasattr(field, "name") else field
        ),
    )


@register.filter
def get_form_field(form, field_name):
    """获取表单字段"""
    try:
        return form[field_name]
    except KeyError:
        return ""


@register.inclusion_tag("users/perm_table.html", takes_context=True)
def render_user_or_group_perms_table(context, user, group=None):
    """
    渲染用户或组权限表格

    参数说明：
        user: 用户对象
        group: 组对象
    """
    from django import forms
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType

    table_data = []
    content_types = ContentType.objects.filter(app_label="dcrm").order_by("model")

    if user.is_superuser:
        user_permissions = Permission.objects.values_list("id", flat=True)
    else:
        user_permissions = user.groups.all().values_list("permissions__id", flat=True)
    # 获取当前权限（如果是编辑现有组）
    current_permissions = set()
    if group:
        current_permissions = set(group.permissions.values_list("id", flat=True))

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

        # 获取模型的所有权限
        permissions = Permission.objects.filter(content_type=ct)
        for perm in permissions:
            field_name = f"permission_{perm.id}"

            # 确定是否应该默认选中
            is_checked = perm.id in current_permissions or (  # 编辑时保持现有选择
                not group and perm.codename.startswith("view_")
            )  # 新建时默认选中view权限

            disabled = perm.id not in user_permissions
            # 创建复选框字段
            field = forms.BooleanField(
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
