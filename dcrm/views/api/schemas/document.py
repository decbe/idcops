"""
文档分类相关的 API schemas
"""

from typing import List, Optional

from ninja import Schema


class DocumentClassificationRequestSchema(Schema):
    """文档分类请求 Schema"""

    content: str
    title: Optional[str] = None


class TagSuggestionSchema(Schema):
    """标签建议 Schema"""

    id: int
    name: str
    color: Optional[str] = None
    score: Optional[float] = None


class CategorySuggestionSchema(Schema):
    """分类建议 Schema"""

    id: int
    name: str
    color: Optional[str] = None
    score: Optional[float] = None


class DocumentClassificationResponseSchema(Schema):
    """文档分类响应 Schema"""

    status: str = "success"
    suggested_tags: List[TagSuggestionSchema]
    suggested_categories: List[CategorySuggestionSchema]
    total_suggestions: int


class DocumentAutoClassifyResponseSchema(Schema):
    """文档自动分类响应 Schema"""

    status: str = "success"
    message: str
    assigned_tags: int
    assigned_categories: int


class ClassifierStatusSchema(Schema):
    """分类器状态 Schema"""

    model_exists: bool
    classifier_loaded: bool
    model_size: int
    last_trained: Optional[float] = None
    model_version: Optional[int] = None
    training_samples: int
    can_train: bool


class ClassifierStatusResponseSchema(Schema):
    """分类器状态响应 Schema"""

    status: str = "success"
    classifier_status: ClassifierStatusSchema


class ErrorResponseSchema(Schema):
    """错误响应 Schema"""

    status: str = "error"
    message: str
