from django.http import HttpRequest, JsonResponse
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from dcrm.forms.document import DocumentBaseForm
from dcrm.models import Category, Document
from dcrm.utilities.doc_convert import (
    convert_docx,
    convert_markdown,
    guess_title_from_html,
    guess_title_from_markdown,
    localize_images_in_html,
)

from .mixins.base import BaseRequestMixin
from .mixins.delete import DeleteViewMixin
from .mixins.detail import DetailViewMixin
from .mixins.edit import CreateViewMixin, FieldSet, UpdateViewMixin
from .mixins.list import ListViewMixin


class DocumentListView(BaseRequestMixin, ListViewMixin, ListView):
    model = Document
    list_fields = [
        "title",
        "data_center",
        "is_template",
        "shared",
        "status",
        "categories",
        "tags",
        "created_at",
        "created_by",
    ]


class DocumentDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = Document
    fields = "__all__"


class DocumentCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = Document
    form_class = DocumentBaseForm
    template_name = "document/create.html"
    success_url = reverse_lazy("document_list")
    clone_fields = []
    fields = [
        "title",
        "content",
        "status",
        "shared",
        # "is_template",
        "categories",
        "tags",
    ]

    fieldsets = [
        FieldSet(
            name=_("标题&内容"),
            fields=["title", "content"],
            description=_("文章的标题和内容信息"),
            col=9,
        ),
        FieldSet(
            name=_("分类&标签"),
            col=3,
            fields=[
                "upload_file",
                "categories",
                "tags",
                "status",
                "shared",
                # "is_template",
                "template_to",
            ],
            description=_("共享状态、模板状态、分类、标签"),
            collapse=False,
        ),
    ]


class DocumentUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = Document
    form_class = DocumentBaseForm
    template_name = "document/create.html"
    success_url = reverse_lazy("document_list")
    clone_fields = []
    fields = [
        "title",
        "content",
        "status",
        "shared",
        # "is_template",
        "categories",
        "tags",
    ]

    fieldsets = [
        FieldSet(
            name=_("标题和内容"),
            fields=["title", "content"],
            description=_("文章的标题和内容信息"),
            col=9,
        ),
        FieldSet(
            name=_("分类&标签"),
            fields=[
                "upload_file",
                "categories",
                "tags",
                "status",
                "shared",
                # "is_template",
                "template_to",
            ],
            description=_("共享状态、模板状态、分类、标签"),
            collapse=False,
            col=3,
        ),
    ]


class DocumentDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    model = Document
    success_url = reverse_lazy("document_list")


class CategoryListView(BaseRequestMixin, ListViewMixin, ListView):
    model = Category
    list_fields = [
        "name",
        "color_with_html",
        "description",
        "parent",
        "shared",
        "created_at",
        "created_by",
    ]


class CategoryDetailView(BaseRequestMixin, DetailViewMixin, DetailView):
    model = Category
    fields = "__all__"


class CategoryCreateView(BaseRequestMixin, CreateViewMixin, CreateView):
    model = Category
    success_url = reverse_lazy("category_list")
    fields = [
        "name",
        "color",
        "description",
        "parent",
        "shared",
    ]
    fieldsets = [
        FieldSet(
            name="基本信息",
            fields=["name", "color", "description", "parent", "shared"],
        ),
    ]


class CategoryUpdateView(BaseRequestMixin, UpdateViewMixin, UpdateView):
    model = Category
    success_url = reverse_lazy("category_list")
    fields = [
        "name",
        "color",
        "description",
        "parent",
        "shared",
    ]
    fieldsets = [
        FieldSet(
            name="基本信息",
            fields=["name", "color", "description", "parent", "shared"],
        ),
    ]


class CategoryDeleteView(BaseRequestMixin, DeleteViewMixin, DeleteView):
    model = Category
    success_url = reverse_lazy("category_list")


class DocumentConvertUploadView(BaseRequestMixin, View):
    """将上传的 .md 或 .docx 转为 HTML/原始文本并返回 JSON。"""

    def post(self, request: HttpRequest, *args, **kwargs):
        file = request.FILES.get("upload_file") or request.FILES.get("file")
        if not file:
            return JsonResponse(
                {"status": "false", "message": "未收到文件"}, status=400
            )

        filename = getattr(file, "name", "").lower()
        try:
            if filename.endswith(".md"):
                md_text = file.read().decode("utf-8", errors="ignore")
                html, raw_text = convert_markdown(md_text)
                title_guess = guess_title_from_markdown(
                    md_text
                ) or guess_title_from_html(html)
            elif filename.endswith(".docx"):
                html, raw_text = convert_docx(file)
                title_guess = guess_title_from_html(html) or (
                    raw_text.strip().splitlines()[0] if raw_text.strip() else None
                )
            else:
                return JsonResponse(
                    {"status": "false", "message": "不支持的文件类型"}, status=400
                )

            # 图片本地化：data: 与 http(s) 链接
            html_localized, changed = localize_images_in_html(
                html, request.user, request.user.data_center
            )
            html = html_localized
        except Exception as e:
            return JsonResponse({"status": "false", "message": str(e)}, status=500)

        return JsonResponse(
            {
                "status": "true",
                "html": html,
                "raw_content": raw_text,
                "title": title_guess or "",
            }
        )
