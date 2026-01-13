
from ninja import Router, Schema

from dcrm.utilities.base import expand_regex_pattern

router = Router()


class ErrorResponse(Schema):
    status: str = "error"
    message: str
    count: int = 0
    result: list[str] = []


class SuccessResponse(Schema):
    status: str = "success"
    result: list[str]
    count: int


class RegexPatternRequest(Schema):
    pattern: str


@router.post(
    "/expand-regex/",
    response={200: SuccessResponse, 400: ErrorResponse},
    url_name="expand_regex_pattern_api",
)
def expand_regex_pattern_api(request, data: RegexPatternRequest):
    """展开正则表达式模式为具体字符串列表

    Args:
        data: 包含正则表达式模式的请求数据

    Returns:
        包含展开结果的响应

    """
    if not data.pattern:
        return {
            "status": "error",
            "message": "pattern is required",
            "count": 0,
            "result": [],
        }

    try:
        result = sorted(list(set(expand_regex_pattern(data.pattern, limit=100))))
        return {"status": "success", "result": result, "count": len(result)}
    except Exception as e:
        return 400, {"status": "error", "message": str(e), "count": 0, "result": []}
