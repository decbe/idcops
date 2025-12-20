from django import forms
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext as _

from dcrm.models.customfields import CustomField, CustomFieldTypeChoices
from dcrm.models.fields import InterfaceIPAddressField


class SearchForm(forms.Form):
    """
    列表搜索表单
    自动根据模型生成搜索字段
    """

    search = forms.CharField(
        label=_("搜索"),
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "请输入搜索关键字", "class": "form-control"}
        ),
    )

    def __init__(self, *args, **kwargs):
        self.model = kwargs.pop("model", None)
        self.data_center = kwargs.pop("data_center", None)
        self.search_fields = kwargs.pop("search_fields", [])
        self.exclude_fields = getattr(
            settings,
            "SEARCH_EXCLUDE_FIELDS",
            [
                "id",
                "created_at",
                "updated_at",
                "deleted_at",
                "created_by",
                "updated_by",
                "password",
                "data_center",
            ],
        )
        super().__init__(*args, **kwargs)

        if not self.search_fields:
            self.search_fields = self._build_search_fields()

    def _build_search_fields(self):
        search_fields = []
        can_search_fields = (
            models.CharField,
            models.SlugField,
            models.TextField,
            models.ManyToManyField,
            models.GenericIPAddressField,
            InterfaceIPAddressField,
        )
        for field in self.model._meta.get_fields():
            if field.name in self.exclude_fields:
                continue

            if isinstance(field, can_search_fields) and not isinstance(
                field, models.ManyToManyField
            ):
                search_fields.append(field.name)
            if isinstance(field, models.ForeignKey):
                related_model = field.remote_field.model
                for related_field in related_model._meta.fields:
                    if related_field.name in self.exclude_fields:
                        continue
                    if isinstance(related_field, can_search_fields):
                        search_fields.append(f"{field.name}__{related_field.name}")
            if isinstance(field, models.ManyToManyField):
                related_model = field.remote_field.model
                m2m_can_search_fields = (
                    models.CharField,
                    InterfaceIPAddressField,
                )
                for related_field in related_model._meta.fields:
                    if related_field.name in self.exclude_fields:
                        continue
                    if isinstance(related_field, m2m_can_search_fields):
                        if related_field.name == field.name:
                            continue
                        search_fields.append(f"{field.name}__{related_field.name}")
        # TODO: 支持外键
        # custom_fields = CustomField.objects.get_for_model(self.model, self.data_center, False)
        # for cf in custom_fields:
        #     if cf.type in (
        #         CustomFieldTypeChoices.TYPE_DATE, CustomFieldTypeChoices.TYPE_DATETIME,
        #         CustomFieldTypeChoices.TYPE_LONGTEXT, CustomFieldTypeChoices.TYPE_TEXT,
        #         CustomFieldTypeChoices.TYPE_URL, CustomFieldTypeChoices.TYPE_DECIMAL,
        #         CustomFieldTypeChoices.TYPE_INTEGER
        #     ):
        #         search_fields.append(f'custom_field_data__{cf.name}')
        return search_fields

    def get_search_query(self):
        """构建搜索查询条件"""
        if not self.is_valid():
            return Q()

        search_value = self.cleaned_data.get("search").strip()
        if not search_value or not self.search_fields:
            return Q()

        q = Q()
        for field in self.search_fields:
            q |= Q(**{f"{field}__icontains": search_value})
        return q
