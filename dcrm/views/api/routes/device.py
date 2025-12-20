from ninja import Router

from django.apps import apps
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from ..schemas.dynamic import (
    DevicePredictRequestSchema,
    DevicePredictResponseSchema,
    ErrorResponseSchema,
)

router = Router()


@router.post(
    "/devices/model/predict/",
    response={200: DevicePredictResponseSchema, 404: ErrorResponseSchema},
    url_name="predict_device_model",
)
def predict_device_model(request, data: DevicePredictRequestSchema):
    return 404, {"status": "error", "detail": "免费版本暂不支持此功能"}
