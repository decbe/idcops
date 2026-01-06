"""文档分类相关的 API schemas
"""


from ninja import Schema


class DocumentClassificationRequestSchema(Schema):
    """文档分类请求 Schema"""

    content: str
    title: str | None = None


class TagSuggestionSchema(Schema):
    """标签建议 Schema"""

    id: int
    name: str
    color: str | None = None
    score: float | None = None


class CategorySuggestionSchema(Schema):
    """分类建议 Schema"""

    id: int
    name: str
    color: str | None = None
    score: float | None = None


class DocumentClassificationResponseSchema(Schema):
    """文档分类响应 Schema"""

    status: str = "success"
    suggested_tags: list[TagSuggestionSchema]
    suggested_categories: list[CategorySuggestionSchema]
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
    last_trained: float | None = None
    model_version: int | None = None
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
