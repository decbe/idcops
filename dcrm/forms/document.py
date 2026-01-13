from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from dcrm.models import Document, Tag

from .base import BaseModelFormMixin
from .forms import CustomFieldModelForm

STATIC_PREFIX = getattr(settings, "STATIC_URL", "/static/")


class DocumentBaseForm(CustomFieldModelForm, BaseModelFormMixin):
    """文档创建表单"""

    upload_file = forms.FileField(
        label=_("上传文档"),
        required=False,
        help_text=_("支持 Markdown(.md)、Word(.docx) 自动转换为HTML"),
    )
    raw_content = forms.CharField(widget=forms.HiddenInput, required=False)

    # 智能分类相关字段
    auto_classify = forms.BooleanField(
        label=_("启用智能分类"),
        required=False,
        initial=True,
        help_text=_("保存时自动为文档分配标签和分类"),
    )

    suggest_classification = forms.BooleanField(
        label=_("获取分类建议"),
        required=False,
        help_text=_("仅获取分类建议，不自动分配"),
        widget=forms.CheckboxInput(attrs={"class": "suggest-btn"}),
    )

    class Meta:
        model = Document
        fields = [
            "title",
            "content",
            "status",
            "shared",
            "template_to",
            "categories",
            "tags",
        ]

    class Media:
        extend = True
        css = {"all": (f"{STATIC_PREFIX}/summernote/summernote.min.css",)}

        js = (
            f"{STATIC_PREFIX}/summernote/summernote.min.js",
            f"{STATIC_PREFIX}/summernote/lang/summernote-zh-CN.min.js",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 使用Tag管理器获取适用于Document的标签
        if hasattr(self, "instance") and self.instance.pk and self.instance.data_center:
            # 编辑现有文档时，使用文档的数据中心
            self.fields["tags"].queryset = Tag.get_available_tags(
                data_center=self.instance.data_center, model=Document
            )
        elif "initial" in kwargs and "data_center" in kwargs["initial"]:
            # 新建文档时，使用初始数据中心
            self.fields["tags"].queryset = Tag.get_available_tags(
                data_center=kwargs["initial"]["data_center"], model=Document
            )

    def save(self, commit=True):
        instance: Document = super().save(commit=False)
        raw_text = self.cleaned_data.get("raw_content")
        if raw_text is not None:
            instance.raw_content = raw_text

        if commit:
            instance.save()
            self.save_m2m()

            # 执行智能分类
            auto_classify = self.cleaned_data.get("auto_classify", False)
            if auto_classify and instance.content:
                try:
                    result = instance.apply_smart_classification(auto_assign=True)
                    if result.get("assigned"):
                        # 记录分类结果（可选）
                        import logging

                        logger = logging.getLogger("dcrm.document_classifier")
                        logger.info(f"文档 {instance.pk} 智能分类完成")
                except Exception as e:
                    # 分类失败不影响文档保存
                    import logging

                    logger = logging.getLogger("dcrm.document_classifier")
                    logger.error(f"文档 {instance.pk} 智能分类失败: {str(e)}")

        return instance

    def get_classification_suggestions(self):
        """获取分类建议（用于AJAX调用）
        """
        if hasattr(self, "instance") and self.instance.pk and self.instance.content:
            return self.instance.get_classification_suggestions()
        elif self.cleaned_data.get("content"):
            # 为新文档创建临时实例
            from dcrm.models import Document

            temp_doc = Document(
                content=self.cleaned_data["content"],
                data_center=self.initial.get("data_center")
                or getattr(self, "_data_center", None),
            )
            return temp_doc.get_classification_suggestions()
        return {}
