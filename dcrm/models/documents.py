import logging
import os

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _

from .base import BaseModel, NestedGroupModel
from .mixins import ColorMixin, CustomFieldsMixin
from .utils import md5sum_file, tag_limit_filter, upload_to

logger = logging.getLogger(__name__)

__all__ = ["Attachment", "Category", "Document"]


class Attachment(BaseModel):
    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.CASCADE,
        verbose_name=_("数据中心"),
        help_text=_("附件所属的数据中心"),
    )
    name = models.CharField(
        max_length=255,
        verbose_name=_("文件名称"),
        help_text=_("附件名称"),
    )
    file = models.FileField(
        upload_to=upload_to,
        verbose_name=_("文件"),
        help_text=_("文件"),
    )
    md5sum = models.SlugField(
        editable=False,
        blank=True,
        null=True,
        verbose_name=_("md5sum"),
        help_text=_("文件md5sum"),
    )
    mime_type = models.CharField(
        max_length=255,
        default="unknown",
        verbose_name=_("文件类型"),
        help_text=_("文件类型"),
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("元数据"),
    )
    _icon = "fa fa-files"
    display_link_field = "name"
    search_fields = ["name", "md5sum"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.file and not self.md5sum:
            self.md5sum = md5sum_file(self.file.path)
            self.save()

    def file_exists(self):
        """
        检查附件文件是否在文件系统中实际存在

        Returns:
            bool: 如果文件存在返回True，否则返回False
        """
        try:
            if not self.file:
                return False

            if not hasattr(self.file, "path"):
                return False

            file_path = self.file.path
            return os.path.exists(file_path) and os.path.isfile(file_path)
        except Exception as e:
            logger.error(f"检查文件存在性时出错: ID={self.id}, 错误={str(e)}")
            return False

    def get_file_info(self):
        """
        获取文件详细信息

        Returns:
            dict: 包含文件详细信息的字典
        """
        file_exists = self.file_exists()
        file_size = 0
        file_path = None

        try:
            if file_exists and self.file:
                file_size = self.file.size
                file_path = self.file.path
        except Exception as e:
            logger.error(f"获取文件信息时出错: ID={self.id}, 错误={str(e)}")

        return {
            "id": self.id,
            "name": self.name,
            "exists": file_exists,
            "size": file_size,
            "path": file_path,
            "url": self.file.url if self.file else None,
            "md5sum": self.md5sum,
            "mime_type": self.mime_type,
        }

    class Meta:
        verbose_name = _("附件")
        verbose_name_plural = _("媒体附件")
        ordering = ["-created_at"]


class Category(NestedGroupModel, ColorMixin, CustomFieldsMixin):
    """文档分类"""

    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.CASCADE,
        verbose_name=_("数据中心"),
        help_text=_("文档分类所属的数据中心"),
    )
    shared = models.BooleanField(
        default=True,
        blank=True,
        verbose_name=_("是否共享"),
        help_text=_("是否共享给其他数据中心引用"),
    )
    _icon = "fa fa-folder"
    display_link_field = "name"
    search_fields = ["name"]

    def __str__(self) -> str:
        return self.name

    class Meta:
        verbose_name = _("文档分类")
        verbose_name_plural = _("文档分类")
        ordering = ["tree_id", "lft"]


class Document(BaseModel, CustomFieldsMixin):
    data_center = models.ForeignKey(
        "dcrm.DataCenter",
        on_delete=models.CASCADE,
        verbose_name=_("数据中心"),
        help_text=_("文档所属的数据中心"),
    )
    title = models.CharField(
        max_length=255,
        verbose_name=_("文档标题"),
        help_text=_("文档标题"),
    )
    content = models.TextField(
        verbose_name=_("文档内容"),
        help_text=_("文档内容"),
    )
    raw_content = models.TextField(
        verbose_name=_("原始内容"),
        help_text=_("原始内容，未经过渲染的内容"),
        blank=True,
        editable=False,
    )
    status = models.SlugField(
        choices=[("draft", "草稿"), ("published", "已发布")],
        default="draft",
        verbose_name=_("文档状态"),
        help_text=_("文档状态"),
    )
    shared = models.BooleanField(
        default=False,
        verbose_name=_("是否分享"),
        help_text=_("是否分享到数据中心"),
    )
    template_to = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to=models.Q(app_label="dcrm"),
        verbose_name=_("模板到"),
        help_text=_("设为模板到哪个内容类型"),
    )
    is_template = models.BooleanField(
        default=False,
        verbose_name=_("是否为模板"),
        help_text=_("是否设置为模板"),
    )
    attachments = models.ManyToManyField(
        Attachment,
        blank=True,
        verbose_name=_("附件"),
        help_text=_("文档附件"),
    )
    categories = models.ManyToManyField(
        Category,
        blank=True,
        verbose_name=_("文档分类"),
        help_text=_("文档分类"),
    )
    tags = models.ManyToManyField(
        "dcrm.Tag",
        blank=True,
        limit_choices_to=tag_limit_filter("dcrm", "document"),
        verbose_name=_("标签"),
        help_text=_("文档标签"),
    )
    _icon = "fa fa-file-text"
    display_link_field = "title"
    search_fields = ["title"]

    def __str__(self) -> str:
        return self.title

    class Meta:
        verbose_name = _("文档")
        verbose_name_plural = _("文档管理")
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        """
        保存文档时检查是否设置为模板，并确保 raw_content 在通过解析产生时被保留。
        如果设置了 template_to 字段，则将 is_template 设置为 True。
        """
        is_template = bool(getattr(self, "template_to", False))
        self.is_template = is_template
        # 如果表单清洗阶段已经设置了 raw_content，则直接保存；否则不强行覆盖
        return super().save(*args, **kwargs)

    def apply_smart_classification(self, auto_assign: bool = True) -> dict:
        """
        对文档应用智能分类

        Args:
            auto_assign: 是否自动分配预测的标签和分类

        Returns:
            dict: 包含预测结果的字典
        """
        from dcrm.apar.document_classifier import load_classifier
        from dcrm.models import Category, Tag

        result = {
            "predicted_tags": [],
            "predicted_categories": [],
            "assigned": False,
            "predicted_tags_scores": {},
            "predicted_categories_scores": {},
        }

        if not self.content:
            return result

        # 使用机器学习分类器预测（如果可用）
        classifier = load_classifier()
        if classifier:
            try:
                predictions = classifier.predict_all_with_scores(self.content)

                # 获取预测的标签和分类对象，限制在当前数据中心
                if predictions.get("tags"):
                    tag_ids = [item["id"] for item in predictions["tags"]]
                    predicted_tags = Tag.objects.filter(
                        pk__in=tag_ids, data_center=self.data_center
                    )
                    result["predicted_tags"] = list(predicted_tags)
                    result["predicted_tags_scores"] = {
                        int(item["id"]): float(item["score"])
                        for item in predictions["tags"]
                    }

                if predictions.get("categories"):
                    cat_ids = [item["id"] for item in predictions["categories"]]
                    predicted_categories = Category.objects.filter(
                        pk__in=cat_ids, data_center=self.data_center
                    )
                    result["predicted_categories"] = list(predicted_categories)
                    result["predicted_categories_scores"] = {
                        int(item["id"]): float(item["score"])
                        for item in predictions["categories"]
                    }
            except Exception:
                # 分类器预测失败，继续进行后续处理
                pass

        # 如果机器学习没有结果，推荐当前数据中心最常用的标签和分类
        if not result["predicted_tags"] and not result["predicted_categories"]:
            # 获取当前数据中心使用最多的标签（限制前5个）
            popular_tags = (
                Tag.objects.filter(
                    data_center=self.data_center, document__data_center=self.data_center
                )
                .annotate(usage_count=models.Count("document"))
                .order_by("-usage_count")[:5]
            )
            result["predicted_tags"] = list(popular_tags)
            # 归一化得分（按最大使用次数）
            max_tag_usage = max([t.usage_count for t in popular_tags], default=0)
            if max_tag_usage > 0:
                result["predicted_tags_scores"] = {
                    int(t.pk): float(t.usage_count) / float(max_tag_usage)
                    for t in popular_tags
                }
            else:
                result["predicted_tags_scores"] = {int(t.pk): 0.5 for t in popular_tags}

            # 获取当前数据中心使用最多的分类（限制前3个）
            popular_categories = (
                Category.objects.filter(
                    data_center=self.data_center, document__data_center=self.data_center
                )
                .annotate(usage_count=models.Count("document"))
                .order_by("-usage_count")[:3]
            )
            result["predicted_categories"] = list(popular_categories)
            max_cat_usage = max([c.usage_count for c in popular_categories], default=0)
            if max_cat_usage > 0:
                result["predicted_categories_scores"] = {
                    int(c.pk): float(c.usage_count) / float(max_cat_usage)
                    for c in popular_categories
                }
            else:
                result["predicted_categories_scores"] = {
                    int(c.pk): 0.5 for c in popular_categories
                }

        # 自动分配（如果设置了auto_assign）
        if auto_assign and (result["predicted_tags"] or result["predicted_categories"]):
            # 依据分数阈值筛选
            TAG_THRESHOLD = 0.65
            CAT_THRESHOLD = 0.65

            # 准备有序的预测集合（按分数降序）
            tag_scores_map = result.get("predicted_tags_scores") or {}
            cat_scores_map = result.get("predicted_categories_scores") or {}

            predicted_tags_sorted = sorted(
                result.get("predicted_tags", []),
                key=lambda t: float(tag_scores_map.get(int(t.pk), 0.0)),
                reverse=True,
            )
            predicted_categories_sorted = sorted(
                result.get("predicted_categories", []),
                key=lambda c: float(cat_scores_map.get(int(c.pk), 0.0)),
                reverse=True,
            )

            # 应用：分类最多1个，分数>=65%
            assigned_any = False
            categories_to_assign = []
            for c in predicted_categories_sorted:
                score = float(cat_scores_map.get(int(c.pk), 0.0))
                if score >= CAT_THRESHOLD:
                    categories_to_assign.append(c)
                if len(categories_to_assign) >= 1:
                    break
            if categories_to_assign:
                self.categories.add(*categories_to_assign)
                assigned_any = True

            # 应用：标签1-3个，分数>=65%
            tags_to_assign = []
            for t in predicted_tags_sorted:
                score = float(tag_scores_map.get(int(t.pk), 0.0))
                if score >= TAG_THRESHOLD:
                    tags_to_assign.append(t)
                if len(tags_to_assign) >= 3:
                    break
            if tags_to_assign:
                self.tags.add(*tags_to_assign)
                assigned_any = True

            result["assigned"] = assigned_any

        return result

    def get_classification_suggestions(self) -> dict:
        """
        获取分类建议（不自动分配）

        Returns:
            dict: 分类建议
        """
        return self.apply_smart_classification(auto_assign=False)
