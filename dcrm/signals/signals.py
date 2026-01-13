import logging

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.signals import (
    m2m_changed,
    post_delete,
    post_migrate,
    post_save,
    pre_delete,
)
from django.dispatch import Signal, receiver
from django_rq import enqueue

from dcrm.models.base import Manufacturer
from dcrm.models.choices import (
    DevicePortStatusChoices,
    DevicePortTypeChoices,
    DeviceStatusChoices,
    IPAddressStatusChoices,
    RackPDUStatusChoices,
)
from dcrm.models.customfields import CustomField
from dcrm.models.devices import Device, DevicePort
from dcrm.models.networks import IPAddress
from dcrm.models.patchcords import PatchCord
from dcrm.models.racks import RackPDU
from dcrm.models.tenants import Tenant
from dcrm.models.users import User
from dcrm.tasks.icon import fetch_icon_task

logger = logging.getLogger(__name__)


@receiver(pre_delete, sender=CustomField)
def custom_field_pre_delete(sender, instance, **kwargs):
    """在删除CustomField之前清理相关数据
    """
    instance.remove_stale_data()


@receiver(m2m_changed, sender=CustomField.object_types.through)
def custom_field_objects_changed(
    sender, instance, action, reverse, model, pk_set, **kwargs
):
    """当CustomField的object_types发生变化时处理数据
    """
    if action == "pre_remove" and pk_set:
        content_types = ContentType.objects.filter(pk__in=pk_set)
        instance.remove_stale_data(content_types)


@receiver(pre_delete, sender=ContentType)
def content_type_pre_delete(sender, instance, **kwargs):
    """在删除ContentType之前清理相关的自定义字段数据
    """
    custom_fields = CustomField.objects.filter(
        models.Q(object_types=instance) | models.Q(related_model=instance)
    ).distinct()

    for cf in custom_fields:
        cf.remove_stale_data([instance])


@receiver(post_migrate)
def create_default_custom_fields(sender, **kwargs):
    """在迁移后创建默认的自定义字段
    """
    app_config = apps.get_app_config(sender.label)

    # 检查是否需要创建默认字段
    if not hasattr(app_config, "default_custom_fields"):
        return

    for model_name, fields in app_config.default_custom_fields.items():
        try:
            model = apps.get_model(sender.label, model_name)
            content_type = ContentType.objects.get_for_model(model)

            for field_def in fields:
                name = field_def.pop("name")
                field_type = field_def.pop("type")

                # 如果字段不存在，则创建
                if not CustomField.objects.filter(
                    name=name, object_types=content_type
                ).exists():
                    cf = CustomField.objects.create_field(
                        name=name, type=field_type, **field_def
                    )
                    cf.object_types.add(content_type)

        except (LookupError, KeyError):
            logger.error(
                f"Error creating default custom field for {model_name}: {name}"
            )
            continue


@receiver(post_save, sender=User)
def sync_default_datacenter(sender, instance, created, **kwargs):
    """在用户保存后，确保默认数据中心在数据中心列表中
    使用信号处理可以确保m2m关系表已经创建
    """
    if instance.data_center:
        # 检查默认数据中心是否在列表中
        if not instance.data_centers.filter(id=instance.data_center.id).exists():
            instance.data_centers.add(instance.data_center)
            # 清除缓存
            # instance.clear_datacenter_cache()


@receiver(post_delete, sender=Device)
def reset_device_rack_pdus_used_status(sender, instance, **kwargs):
    # instance.rack_pdus.update(is_used=False)
    instance.rack_pdus.update(status=RackPDUStatusChoices.EMPTY)
    # rack = instance.rack
    # check current rack pdus used status
    # pdus = instance.rack_pdus.all()
    mounted_devices = Device.objects.filter(
        status__in=[DeviceStatusChoices.MOUNTED, DeviceStatusChoices.MIGRATED],
        rack=instance.rack,
    )
    # current rack all pdus
    rack_pdus = instance.rack.pdus.all()
    really_used_pdus = list()
    for device in mounted_devices:
        really_used_pdus.extend(device.rack_pdus.all())
    rack_pdus.exclude(pk__in=[p.pk for p in really_used_pdus]).update(
        status=RackPDUStatusChoices.EMPTY
    )


@receiver(m2m_changed, sender=Device.ips.through)
def update_device_ips_status(
    sender, instance, action, reverse, model, pk_set, **kwargs
):
    """更新设备IP地址状态"""
    if action == "post_add":
        IPAddress.objects.filter(pk__in=pk_set).update(
            status=IPAddressStatusChoices.USED
        )
    if action == "post_remove":
        IPAddress.objects.filter(pk__in=pk_set).update(
            status=IPAddressStatusChoices.ALLOCATED
        )


@receiver(m2m_changed, sender=Device.rack_pdus.through)
def change_pdus_is_used_status(
    sender, instance, action, reverse, model, pk_set, **kwargs
):
    """当设备关联的PDU发生变化时更新PDU的is_used字段
    instance: 设备对象
    model: RackPDU模型
    pk_set: PDU的主键集合
    """
    # queryset = RackPDU.objects.filter(pk__in=pk_set)
    if action in ["pre_remove", "post_remove"]:
        # RackPDU.objects.filter(pk__in=pk_set).update(is_used=False)
        RackPDU.objects.filter(pk__in=pk_set).update(status=RackPDUStatusChoices.EMPTY)
    if action == "pre_add":
        # 检查PDU是否已经关联到其他设备，如果关联到其他设备，则抛出异常
        if RackPDU.objects.filter(
            pk__in=pk_set, status=RackPDUStatusChoices.USED
        ).exists():
            raise ValueError("PDU已经关联到其他设备，不能重复关联")
    if action == "post_add":
        # RackPDU.objects.filter(pk__in=pk_set).update(is_used=True)
        RackPDU.objects.filter(pk__in=pk_set).update(status=RackPDUStatusChoices.USED)

    # 更新PDU使用情况
    # TODO: Fix 电源关联PDU对象不稳定。
    if action.startswith("post_"):
        # pass
        pdu_count = instance.rack_pdus.count()
        max_pdu_count = instance.model.power_port_count
        if pdu_count > max_pdu_count:
            raise ValueError(f"PDU数量不能超过{max_pdu_count}")
        else:
            device_power_ports = list(
                DevicePort.objects.filter(
                    device=instance, port_type=DevicePortTypeChoices.POWER
                ).values_list("id", flat=True)
            )
            power_ports = DevicePort.objects.filter(pk__in=device_power_ports)
            power_ports.update(status=DevicePortStatusChoices.DISCONNECTED)
            powers = power_ports.filter(pk__in=device_power_ports[:pdu_count])
            powers.update(status=DevicePortStatusChoices.CONNECTED)
            for index, power in enumerate(powers):
                power.connected_to = ContentType.objects.get_for_model(RackPDU)
                power.connected_object_id = instance.rack_pdus.all()[index].id
                power.save(update_fields=["connected_to", "connected_object_id"])


patch_cord_status_changed = Signal()


def connect_node_ports(patch_cord):
    """连接补丁线的端口，确保每个端口只连接到一个其他端口

    Args:
        patch_cord: PatchCord 实例

    """
    nodes = patch_cord.nodes.all()
    ports = [node.port_name for node in nodes if node.port_name]
    # 检查端口数量是否足够进行配对
    if len(ports) < 2:
        logger.warning(f"补丁线 {patch_cord} 的端口数量不足，无法完成配对")
        return

    # 确保端口数量为偶数
    port_count = (len(ports) // 2) * 2

    # 获取 DevicePort 的 ContentType
    port_content_type = ContentType.objects.get_for_model(ports[0].__class__)

    # 成对连接端口
    for i in range(0, port_count, 2):
        port_a = ports[i]
        port_b = ports[i + 1]

        # 连接端口A到端口B
        port_a.connected_to = port_content_type
        port_a.connected_object_id = port_b.id
        port_a.status = DevicePortStatusChoices.CONNECTED
        port_a.save(update_fields=["connected_to", "connected_object_id", "status"])

        # 连接端口B到端口A
        port_b.connected_to = port_content_type
        port_b.connected_object_id = port_a.id
        port_b.status = DevicePortStatusChoices.CONNECTED
        port_b.save(update_fields=["connected_to", "connected_object_id", "status"])


@receiver(patch_cord_status_changed)
def change_patch_cord_node_port_status(sender, instance, **kwargs):
    """处理补丁链节点端口状态变更"""
    connect_node_ports(instance)


@receiver(pre_delete, sender=PatchCord)
def handle_patch_cord_node_changes(sender, instance, **kwargs):
    """处理补丁线节点的变更
    当节点被创建、更新或删除时触发
    """
    for node in instance.nodes.all():
        port = node.port_name
        port.connected_to = None
        port.connected_object_id = None
        port.status = DevicePortStatusChoices.DISCONNECTED
        port.save(update_fields=["connected_to", "connected_object_id", "status"])


def fetch_and_save_icon(sender, instance, **kwargs):
    if instance.website and not instance.icon_exists():
        # 将图标获取任务放入队列
        enqueue(fetch_icon_task, instance)


post_save.connect(fetch_and_save_icon, sender=Manufacturer)
post_save.connect(fetch_and_save_icon, sender=Tenant)
