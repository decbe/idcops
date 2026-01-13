import logging

from django.apps import apps
from django.db.models import Count, F, OuterRef, Subquery
from django.db.models.signals import post_delete, post_save, pre_delete

from dcrm.models.fields import CounterCacheField
from dcrm.register import registry

logger = logging.getLogger(__name__)


def get_counters_for_model(model):
    """返回注册到指定模型的所有计数字段的字段映射。
    """
    return registry["counter_fields"][model].items()


def update_counter(model, pk, counter_name, value):
    """对由模型和主键（PK）标识的对象的计数字段进行自增或自减。正值为自增，负值为自减。
    """
    model.objects.filter(pk=pk).update(**{counter_name: F(counter_name) + value})


def update_counts(model, field_name, related_query):
    """对指定模型和计数字段执行批量更新。例如：

        update_counts(Device, '_interface_count', 'interfaces')

    实际上会执行：

        Device.objects.update(_interface_count=Count('interfaces'))
    """
    subquery = Subquery(
        model.objects.filter(pk=OuterRef("pk"))
        .annotate(_count=Count(related_query))
        .values("_count")
    )
    return model.objects.update(**{field_name: subquery})


#
# 信号处理器
#


def post_save_receiver(sender, instance, created, **kwargs):
    """当 TrackingModelMixin 的子类被创建或修改时，更新相关对象的计数字段。
    """
    if getattr(instance, "_counter_updated", False):
        return  # 本次 save 已经计数过，直接跳过
    instance._counter_updated = True

    for field_name, counter_name in get_counters_for_model(sender):
        parent_model = sender._meta.get_field(field_name).related_model
        new_pk = getattr(instance, field_name, None)
        has_old_field = field_name in instance.tracker
        old_pk = instance.tracker.get(field_name) if has_old_field else None

        # 根据需要更新旧父对象和/或新父对象的计数
        if old_pk is not None:
            update_counter(parent_model, old_pk, counter_name, -1)

        if new_pk is not None and (has_old_field or created):
            update_counter(parent_model, new_pk, counter_name, 1)


def pre_delete_receiver(sender, instance, origin, **kwargs):
    model = instance._meta.model
    if not model.objects.filter(pk=instance.pk).exists():
        instance._previously_removed = True


def post_delete_receiver(sender, instance, origin, **kwargs):
    """当 TrackingModelMixin 的子类被删除时，更新相关对象的计数字段。
    """
    if getattr(instance, "_counter_deleted", False):
        return  # 本次 save 已经计数过，直接跳过
    instance._counter_deleted = True
    for field_name, counter_name in get_counters_for_model(sender):
        parent_model = sender._meta.get_field(field_name).related_model
        parent_pk = getattr(instance, field_name, None)

        # 将父对象的计数减一
        if parent_pk is not None and not hasattr(instance, "_previously_removed"):
            update_counter(parent_model, parent_pk, counter_name, -1)


#
# 注册
#


def connect_counters(*models):
    """注册计数字段，并为受影响的模型连接 post_save 和 post_delete 信号处理器。
    """
    for model in models:

        # 查找模型上的所有 CounterCacheField 字段
        counter_fields = [
            field
            for field in model._meta.get_fields()
            if type(field) is CounterCacheField
        ]

        for field in counter_fields:
            to_model = apps.get_model(field.to_model_name)

            # 在注册表中注册计数器
            change_tracking_fields = registry["counter_fields"][to_model]
            change_tracking_fields[f"{field.to_field_name}_id"] = field.name

            # 连接 post_save 和 post_delete 处理器
            post_save.connect(
                post_save_receiver,
                sender=to_model,
                weak=False,
                dispatch_uid=f"{model._meta.label}.{field.name}",
            )
            pre_delete.connect(
                pre_delete_receiver,
                sender=to_model,
                weak=False,
                dispatch_uid=f"{model._meta.label}.{field.name}",
            )
            post_delete.connect(
                post_delete_receiver,
                sender=to_model,
                weak=False,
                dispatch_uid=f"{model._meta.label}.{field.name}",
            )


def tracker_models_register():
    dcrm_app = apps.get_app_config("dcrm")
    models = []
    for model in dcrm_app.get_models():
        # 检查模型是否支持导入
        if not getattr(model, "tracker_model", True):
            logger.info(f"INFO: 计数跟踪跳过模型: {model._meta.model_name}")
            continue
        models.append(model)
    connect_counters(*models)
