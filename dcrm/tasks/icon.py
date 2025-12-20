import logging

from django.core.files.base import ContentFile

from dcrm.utilities.favicon import icon_fetcher

logger = logging.getLogger(__name__)


def fetch_icon_task(instance):
    """
    获取制造商或租户的图标
    instance: 制造商或租户实例 Manufacturer，Tenant
    """
    # 使用更可靠的防重复机制
    if hasattr(instance, "_icon_fetching") and instance._icon_fetching:
        return

    # 设置标记，防止重复执行
    instance._icon_fetching = True

    try:
        _, file_name, content = icon_fetcher.get_website_favicon(instance.website)
        logger.info(f"获取图标成功: {instance.name}")
        if file_name and content:
            # 保存文件到本地，但不触发 save 信号
            instance.icon.save(file_name, ContentFile(content), save=False)
            instance.__class__.objects.filter(pk=instance.pk).update(
                icon=instance.icon.name
            )
    except Exception as e:
        logger.error(f"获取图标失败: {instance.name}, 错误: {e}")
    finally:
        # 确保标记被清除
        instance._icon_fetching = False
