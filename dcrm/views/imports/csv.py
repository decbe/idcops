from django import forms
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from dcrm.utilities.base import get_content_type_by_labeled_name


class CSVModelChoiceField(forms.ModelChoiceField):
    """
    用于CSV导入的ModelChoiceField，支持通过多个字段查找关联对象
    """

    default_error_messages = {
        "invalid_choice": _("未找到匹配的: %(value)s"),
    }

    def __init__(self, *args, **kwargs):
        # 添加search_fields参数，用于指定查找字段
        self.search_fields = kwargs.pop("search_fields", ["name"])
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if not value:
            return None

        if self.queryset.model is ContentType:
            return get_content_type_by_labeled_name(value)

        try:
            # 构建查询条件
            query = Q()
            for field in self.search_fields:
                query |= Q(**{field: value})

            # 尝试查找对象
            obj = self.queryset.filter(query).first()
            if obj:
                return obj

            # 如果找不到对象，尝试通过ID查找
            if value.isdigit():
                return self.queryset.filter(pk=value).first()

            raise self.queryset.model.DoesNotExist()

        except (ValueError, TypeError, self.queryset.model.DoesNotExist):
            raise forms.ValidationError(
                self.error_messages["invalid_choice"],
                code="invalid_choice",
                params={"value": value},
            )


class CSVChoiceField(forms.ChoiceField):
    """
    用于CSV导入的ChoiceField，处理选项字段
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.choices = self.choices

    def to_python(self, value):
        if not isinstance(value, str):
            raise forms.ValidationError(_("无效的值: {value}").format(value=value))
        value = value.strip()
        if not value:
            return None
        value_to_key_map = {c[1]: c[0] for c in self.choices}
        if value in value_to_key_map.keys():
            return value_to_key_map.get(value)
        elif value in value_to_key_map.values():
            return value
        else:
            raise forms.ValidationError(_("无效的值: {value}").format(value=value))


class CSVMultipleChoiceField(forms.MultipleChoiceField):
    """
    用于CSV导入的MultipleChoiceField，支持逗号分隔的多选值
    """

    def to_python(self, value):
        if not value:
            return []
        if not isinstance(value, str):
            raise forms.ValidationError(_("无效的值: {value}").format(value=value))
        return value.split(",")


class CSVModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    """
    用于CSV导入的ModelMultipleChoiceField，支持逗号分隔的多个关联对象
    """

    default_error_messages = {
        "invalid_choice": _("未找到匹配的: %(value)s"),
    }

    def __init__(self, *args, **kwargs):
        self.search_fields = kwargs.pop("search_fields", ["name"])
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if not value:
            return []

        values = value.split(",") if isinstance(value, str) else value
        objects = []

        if self.queryset.model is ContentType:
            for val in values:
                objects.append(get_content_type_by_labeled_name(val))
            return objects

        for val in values:
            try:
                # 构建查询条件
                query = Q()
                for field in self.search_fields:
                    query |= Q(**{field: val.strip()})

                # 尝试查找对象
                obj = self.queryset.filter(query).first()
                if obj:
                    objects.append(obj)
                    continue

                # 如果找不到对象，尝试通过ID查找
                if val.strip().isdigit():
                    obj = self.queryset.filter(pk=val.strip()).first()
                    if obj:
                        objects.append(obj)
                        continue

                raise self.queryset.model.DoesNotExist()

            except (ValueError, TypeError, self.queryset.model.DoesNotExist):
                raise forms.ValidationError(
                    self.error_messages["invalid_choice"],
                    code="invalid_choice",
                    params={"value": val},
                )

        return objects
