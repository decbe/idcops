import logging

from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError

from dcrm.models import Document

from ..schemas.document import (
    ClassifierStatusResponseSchema,
    DocumentAutoClassifyResponseSchema,
    DocumentClassificationRequestSchema,
    DocumentClassificationResponseSchema,
    ErrorResponseSchema,
)

logger = logging.getLogger("dcrm.document_classifier")

router = Router()


@router.post(
    "/documents/classify-suggest/",
    response={200: DocumentClassificationResponseSchema, 400: ErrorResponseSchema},
    url_name="document_classify_suggest",
    summary="获取文档分类建议",
    description="根据文档内容获取智能分类和标签建议",
)
def get_classification_suggestions(request, data: DocumentClassificationRequestSchema):
    """获取文档分类建议

    Args:
        request: HTTP请求对象
        data: 包含文档内容的请求数据

    Returns:
        分类建议响应

    """
    try:
        if not data.content.strip():
            raise HttpError(400, "文档内容不能为空")

        # 检查用户权限
        if not request.user.is_authenticated:
            raise HttpError(401, "用户未登录")

        # 为新文档内容创建临时实例
        temp_doc = Document(
            content=data.content,
            title=data.title or "",
            data_center=request.user.data_center,
        )
        suggestions = temp_doc.get_classification_suggestions()

        # 分数映射（如果有）
        tag_scores = suggestions.get("predicted_tags_scores", {}) or {}
        cat_scores = suggestions.get("predicted_categories_scores", {}) or {}

        # 格式化返回数据
        suggested_tags = []
        for tag in suggestions.get("predicted_tags", []):
            suggested_tags.append(
                {
                    "id": tag.pk,
                    "name": tag.name,
                    "color": tag.color,
                    "score": (
                        float(tag_scores.get(tag.pk)) if tag.pk in tag_scores else None
                    ),
                }
            )

        suggested_categories = []
        for category in suggestions.get("predicted_categories", []):
            suggested_categories.append(
                {
                    "id": category.pk,
                    "name": category.name,
                    "color": category.color,
                    "score": (
                        float(cat_scores.get(category.pk))
                        if category.pk in cat_scores
                        else None
                    ),
                }
            )

        # 若包含分数，按分数降序排序
        suggested_tags.sort(
            key=lambda x: (x["score"] is not None, x["score"]), reverse=True
        )
        suggested_categories.sort(
            key=lambda x: (x["score"] is not None, x["score"]), reverse=True
        )

        return {
            "status": "success",
            "suggested_tags": suggested_tags,
            "suggested_categories": suggested_categories,
            "total_suggestions": len(suggested_tags) + len(suggested_categories),
        }

    except HttpError:
        raise
    except Exception as e:
        logger.error(f"获取分类建议失败: {str(e)}")
        raise HttpError(500, "获取分类建议失败，请稍后重试")


@router.post(
    "/documents/{document_id}/auto-classify/",
    response={
        200: DocumentAutoClassifyResponseSchema,
        400: ErrorResponseSchema,
        404: ErrorResponseSchema,
    },
    url_name="document_auto_classify",
    summary="文档自动分类",
    description="自动为指定文档分配标签和分类",
)
def auto_classify_document(request, document_id: int):
    """文档自动分类

    Args:
        request: HTTP请求对象
        document_id: 文档ID

    Returns:
        自动分类结果

    """
    try:
        # 检查用户权限
        if not request.user.is_authenticated:
            raise HttpError(401, "用户未登录")

        # 获取文档，限制在用户数据中心内
        document = get_object_or_404(
            Document.objects.filter(data_center=request.user.data_center),
            pk=document_id,
        )

        # 执行自动分类
        result = document.apply_smart_classification(auto_assign=True)

        if result.get("assigned"):
            return {
                "status": "success",
                "message": "自动分类完成",
                "assigned_tags": len(result.get("predicted_tags", [])),
                "assigned_categories": len(result.get("predicted_categories", [])),
            }
        else:
            return {
                "status": "success",
                "message": "未找到匹配的分类",
                "assigned_tags": 0,
                "assigned_categories": 0,
            }

    except Document.DoesNotExist:
        raise HttpError(404, "文档不存在")
    except Exception as e:
        logger.error(f"自动分类失败: {str(e)}")
        raise HttpError(500, "自动分类失败，请稍后重试")


@router.get(
    "/documents/classifier-status/",
    response={200: ClassifierStatusResponseSchema, 400: ErrorResponseSchema},
    url_name="document_classifier_status",
    summary="获取分类器状态",
    description="获取文档分类器的状态信息",
)
def get_classifier_status(request):
    """获取分类器状态

    Args:
        request: HTTP请求对象

    Returns:
        分类器状态信息

    """
    try:
        # 检查用户权限
        if not request.user.is_authenticated:
            raise HttpError(401, "用户未登录")

        from dcrm.apar.document_classifier import get_model_file_path, load_classifier

        model_file = get_model_file_path()
        classifier = load_classifier()

        status = {
            "model_exists": model_file.exists(),
            "classifier_loaded": classifier is not None,
            "model_size": 0,
            "last_trained": None,
            "model_version": None,
            "training_samples": 0,
            "can_train": False,
        }

        if model_file.exists():
            status["model_size"] = model_file.stat().st_size
            status["last_trained"] = model_file.stat().st_mtime

        if classifier:
            status["model_version"] = classifier.FORMAT_VERSION

        # 检查训练数据
        training_docs = (
            Document.objects.filter(
                status="published", data_center=request.user.data_center
            )
            .exclude(categories__isnull=True, tags__isnull=True)
            .count()
        )

        status["training_samples"] = training_docs
        status["can_train"] = training_docs >= 5

        return {"status": "success", "classifier_status": status}

    except Exception as e:
        logger.error(f"获取分类器状态失败: {str(e)}")
        raise HttpError(500, "获取状态失败")
