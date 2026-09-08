"""seed_demo_datacenter 管理命令的 Django 测试。"""

from django.core.management import call_command
from django.test import TestCase

from dcrm.models import (
    DataCenter,
    Device,
    DeviceModel,
    DeviceType,
    Manufacturer,
    Rack,
    RackStatus,
    Room,
    Tenant,
)


class TestSeedDemoDatacenter(TestCase):
    def test_seed_demo_datacenter_creates_demo_data_and_is_idempotent(self):
        """验证演示数据中心种子数据可被重复创建（幂等）。"""
        data_center = DataCenter.objects.create(name="演示数据中心")

        call_command("seed_demo_datacenter", datacenter_id=data_center.id, verbosity=0)

        self.assertEqual(Room.objects.filter(data_center=data_center).count(), 3)
        self.assertEqual(RackStatus.objects.filter(data_center=data_center).count(), 4)
        self.assertEqual(Tenant.objects.filter(data_center=data_center).count(), 4)
        self.assertEqual(Manufacturer.objects.filter(data_center=data_center).count(), 4)
        self.assertEqual(DeviceType.objects.filter(data_center=data_center).count(), 4)
        self.assertEqual(DeviceModel.objects.filter(data_center=data_center).count(), 4)
        self.assertEqual(Rack.objects.filter(data_center=data_center).count(), 5)
        self.assertEqual(Device.objects.filter(data_center=data_center).count(), 6)

        call_command("seed_demo_datacenter", datacenter_id=data_center.id, verbosity=0)

        self.assertEqual(Room.objects.filter(data_center=data_center).count(), 3)
        self.assertEqual(RackStatus.objects.filter(data_center=data_center).count(), 4)
        self.assertEqual(Tenant.objects.filter(data_center=data_center).count(), 4)
        self.assertEqual(Manufacturer.objects.filter(data_center=data_center).count(), 4)
        self.assertEqual(DeviceType.objects.filter(data_center=data_center).count(), 4)
        self.assertEqual(DeviceModel.objects.filter(data_center=data_center).count(), 4)
        self.assertEqual(Rack.objects.filter(data_center=data_center).count(), 5)
        self.assertEqual(Device.objects.filter(data_center=data_center).count(), 6)

        mounted_devices = Device.objects.filter(
            data_center=data_center, rack__isnull=False
        )
        self.assertEqual(mounted_devices.count(), 6)
        self.assertEqual(mounted_devices.exclude(model__isnull=True).count(), 6)
        self.assertEqual(mounted_devices.exclude(type__isnull=True).count(), 6)
        self.assertEqual(mounted_devices.exclude(tenant__isnull=True).count(), 6)
