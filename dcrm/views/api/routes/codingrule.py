import json

from django.apps import apps
from django.db.models import Case, IntegerField, When
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _
from ninja import Router, Schema
from ninja.errors import HttpError
from ninja.parser import Parser

from dcrm.models import CodingRule, Device, DevicePort

router = Router()


# 自定义解析器来处理请求体
class SafeParser(Parser):
    def parse_body(self, request: HttpRequest):
        if not request.body:
            return {}
        try:
            return json.loads(request.body)
        except ValueError as e:
            raise HttpError(400, f"Invalid JSON data, {e}")


# 请求 Schema
class AvailableCodesRequest(Schema):
    to_field: str
    count: int = 1


# 成功响应 Schema
class AvailableCodesResponse(Schema):
    status: str = "success"
    result: dict[str, list[str]]


# 错误响应 Schema
class ErrorResponse(Schema):
    status: str = "error"
    message: str


@router.post(
    "/coding-rules/{model_name}/available_codes/",
    response={200: AvailableCodesResponse, 400: ErrorResponse},
    url_name="get_available_codes",
)
def get_available_codes(
    request, model_name: str, payload: AvailableCodesRequest
) -> dict:
    """获取可用编码

    Args:
        request: HTTP请求对象
        model_name: 模型名称
        payload: 请求体数据

    Returns:
        包含可用编码的响应数据

    Raises:
        HttpError: 当发生错误时抛出，包含错误信息

    """
    try:
        # 获取模型类
        model = apps.get_model("dcrm", model_name)
    except LookupError:
        raise HttpError(400, _("未找到指定模型"))

    try:
        # 获取数据中心和编码规则
        data_center = request.user.data_center
        rules = CodingRule.objects.get_for_model(model, data_center)

        # 获取特定字段的编码规则
        rule = rules.filter(to_field=payload.to_field).first()
        if not rule:
            raise HttpError(400, _("未找到对应的编码规则"))

        # 生成可用编码
        available_codes = rule.get_available_codes(payload.count)

        # 返回成功响应
        return {"status": "success", "result": {payload.to_field: available_codes}}

    except ValueError as e:
        raise HttpError(400, str(e))
    except Exception as e:
        raise HttpError(400, str(e))


class CableLabelRequest(Schema):
    by_field: str
    apoint: int
    zpoint: int


class CableLabelResponse(Schema):
    status: str
    results: dict[int, str]


@router.post(
    "/generate_cable_label_by_nodes/",
    response={200: CableLabelResponse, 400: ErrorResponse},
    url_name="get_cable_labels",
)
def generate_cable_label_by_nodes(request, payload: CableLabelRequest):
    from dcrm.utilities.lookup import generate_cable_label_by_nodes

    ids = [payload.apoint, payload.zpoint]
    preserved_order = Case(
        *[When(id=pk, then=pos) for pos, pk in enumerate(ids)],
        output_field=IntegerField(),
    )
    if payload.by_field == "device":
        queryset = Device.objects.filter(pk__in=ids).order_by(preserved_order)
    else:
        queryset = DevicePort.objects.filter(pk__in=ids).order_by(preserved_order)
    result = generate_cable_label_by_nodes(payload.by_field, queryset[0], queryset[1])
    return {"status": "success", "results": result}
