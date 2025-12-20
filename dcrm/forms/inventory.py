import json
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.forms import formset_factory
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from dcrm.models import (
    InventoryItem,
    ItemCategory,
    ItemInstance,
    ItemInstanceHistory,
    Manufacturer,
)

from .base import BaseModelFormMixin
from .forms import CustomFieldModelForm
from .mixins import AutoSequenceMixin


class InventoryItemBaseForm(BaseModelFormMixin):
    """物品信息基础表单"""

    class Meta:
        model = InventoryItem
        fields = ["name", "manufacturer", "category", "tags"]


class ItemInstanceCreateForm(
    AutoSequenceMixin, CustomFieldModelForm, BaseModelFormMixin
):
    """物品实例创建表单，包含物品信息字段"""

    # InventoryItem 相关字段
    item_name = forms.CharField(
        label=_("物品名称"),
        required=True,
        help_text=_("输入物品名称，如不存在将自动创建"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    manufacturer = forms.CharField(
        label=_("品牌/制造商"),
        required=True,
        widget=forms.Select(
            attrs={
                "class": "form-control select",
                "data-create-option": "true",
            }
        ),
    )
    category = forms.CharField(
        label=_("物品类别"),
        required=True,
        widget=forms.Select(
            attrs={
                "class": "form-control select",
                "data-create-option": "true",
            }
        ),
    )

    # 添加隐藏字段
    image = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        help_text=_("物品图片URL"),
    )
    raw_text = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        help_text=_("OCR识别的原始文本"),
    )

    class Meta:
        model = ItemInstance
        fields = [
            "manufacturer",
            "category",
            "item_name",
            "identifier",
            "quantity",
            "code",
            "tenant",
            "warehouse",
            "location",
            "tags",
            "image",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        empty_label = ("", "---------")
        shared_query = models.Q(data_center=self.data_center) | models.Q(shared=True)
        self.fields["manufacturer"].widget.choices = [
            empty_label,
            *[
                (
                    m.id,
                    f"{m.name} ({m.name_cn})" if m.name_cn else f"{m.name}",
                )
                for m in Manufacturer.objects.filter(shared_query)
            ],
        ]
        self.fields["category"].widget.choices = [
            empty_label,
            *[(m.id, m.name) for m in ItemCategory.objects.filter(shared_query)],
        ]
        self.fields["identifier"].widget = forms.Textarea(
            attrs={"class": "form-control", "rows": 2}
        )

    def clean_manufacturer(self):
        manufacturer_value = self.cleaned_data["manufacturer"]
        try:
            if manufacturer_value.isdigit():
                # 如果是ID，说明选择了现有选项
                return Manufacturer.objects.get(id=manufacturer_value)
            else:
                # 如果是文本，创建新的制造商
                manufacturer, created = Manufacturer.objects.get_or_create(
                    name=manufacturer_value,
                    defaults={
                        "data_center": self.request.user.data_center,
                        "created_by": self.request.user,
                        "shared": False,
                    },
                )
                return manufacturer
        except (Manufacturer.DoesNotExist, ValueError):
            raise forms.ValidationError(_("无效的制造商"))

    def clean_category(self):
        value = self.cleaned_data["category"]
        try:
            if value.isdigit():
                # 如果是ID，说明选择了现有选项
                return ItemCategory.objects.get(id=value)
            else:
                # 如果是文本，创建新的制造商
                category, created = ItemCategory.objects.get_or_create(
                    name=value,
                    defaults={
                        "data_center": self.request.user.data_center,
                        "created_by": self.request.user,
                        "unit": "个",
                        "shared": False,
                        "description": "选择框中创建",
                    },
                )
                return category
        except (ItemCategory.DoesNotExist, ValueError):
            raise forms.ValidationError(_("无效的物品类别"))

    def clean_quantity(self):
        quantity = self.cleaned_data.get("quantity")
        if quantity is not None and quantity <= 0:
            raise ValidationError(_("数量必须大于0"))
        return quantity

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image:
            image = json.loads(image)
        return image

    def clean(self):
        cleaned_data = super().clean()
        identifier = cleaned_data.get("identifier")
        if identifier:
            identifiers = [x.strip() for x in identifier.split(",") if x]
            for item in identifiers:
                existing = ItemInstance.objects.filter(
                    data_center=self.data_center, identifier__icontains=item
                )
                if existing:
                    self.add_error(
                        "identifier", _(f"唯一标识: {item} 的库存物品已存在")
                    )
        # clean metadata
        cleaned_data["metadata"] = {
            "raw_text": cleaned_data["raw_text"] or None,
            "image": cleaned_data["image"] or None,
        }
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        # 获取或创建 InventoryItem
        item_name = self.cleaned_data["item_name"]
        item, created = InventoryItem.objects.get_or_create(
            name=item_name,
            category=self.cleaned_data.get("category"),
            manufacturer=self.cleaned_data.get("manufacturer"),
            defaults={
                "data_center": self.cleaned_data["data_center"],
                "created_by": instance.created_by,
            },
        )

        instance.item = item
        instance.metadata = self.cleaned_data["metadata"]

        if commit:
            instance.save()
            self.save_m2m()

        return instance


class ItemInstanceFormSetBase(forms.BaseFormSet):
    def add_fields(self, form: Any, index: Any) -> None:
        super().add_fields(form, index)
        if "ORDER" in form.fields:
            form.fields["ORDER"].widget = forms.HiddenInput()
        if "DELETE" in form.fields:
            form.fields["DELETE"].widget = forms.HiddenInput()
        for field_name in ["manufacturer", "category", "item_name"]:
            field = form.fields[field_name]
            form.fields[field_name].label = format_html(
                '{}<span class="text-red" style="margin-left: 5px;">*</span>',
                field.label or field_name.title(),
            )
            form.fields[field_name].required = True


# 更新批量表单集
BatchItemInstanceFormSet = formset_factory(
    form=ItemInstanceCreateForm,
    formset=ItemInstanceFormSetBase,
    min_num=1,
    max_num=10,
    validate_min=True,
    can_delete=True,
    extra=0,
)


class ItemInstanceHistoryStockOutForm(BaseModelFormMixin):
    class Meta:
        model = ItemInstanceHistory
        fields = ["item_instance", "reason", "quantity"]

    def __init__(self, *args, **kwargs):
        is_initial = kwargs.pop("is_initial", False)
        super().__init__(*args, **kwargs)
        if is_initial:
            quantity = self.initial["item_instance"].quantity
            self.fields["quantity"].widget.attrs.update({"min": 1, "max": quantity})
            if quantity == 1:
                self.fields["quantity"].widget.attrs.update({"readonly": True})


class ItemInstanceHistoryBorrowForm(BaseModelFormMixin):
    """
    借出物品表单
    """

    expected_return_date = forms.DateField(label=_("归还时间"))

    class Meta:
        model = ItemInstanceHistory
        fields = ["item_instance", "reason", "quantity"]

    def __init__(self, *args, **kwargs):
        is_initial = kwargs.pop("is_initial", False)
        super().__init__(*args, **kwargs)
        if is_initial:
            quantity = self.initial["item_instance"].quantity
            self.fields["quantity"].widget.attrs.update({"min": 1, "max": quantity})
            if quantity == 1:
                self.fields["quantity"].widget.attrs.update({"readonly": True})
