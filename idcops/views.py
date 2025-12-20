from django.http import JsonResponse


def health_check(request) -> JsonResponse:
    return JsonResponse({"status": "OK"})
