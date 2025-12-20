from django.conf import settings
from django.urls import Resolver404, resolve

from dcrm.menus import menu_registry


def menus(request):
    """菜单上下文处理器"""
    try:
        current_url_name = resolve(request.path_info).url_name
    except Resolver404:
        current_url_name = None
    context = {
        "menu_sections": menu_registry.get_sections(),
        "menu_items": menu_registry.get_menus(
            request.user, current_url_name=current_url_name
        ),
    }
    return context


def site_meta(request):
    """站点信息上下文处理器"""
    version = getattr(settings, "VERSION", "0.10.9")
    if request.user.is_authenticated and request.user.data_center:
        meta = {
            "preferences": request.user.get_all_configs(),
            "version": version,
            "sitename": str(request.user.data_center),
        }
    else:
        meta = {
            "preferences": {},
            "version": version,
            "sitename": "DCRM",
        }
    return meta
