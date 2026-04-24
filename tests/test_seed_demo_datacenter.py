import pytest
from django.core.management import call_command

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


@pytest.mark.django_db
def test_seed_demo_datacenter_creates_demo_data_and_is_idempotent():
    """Verify the demo seed can be created repeatedly."""
    data_center = DataCenter.objects.create(name="演示数据中心")

    call_command("seed_demo_datacenter", datacenter_id=data_center.id, verbosity=0)

    assert Room.objects.filter(data_center=data_center).count() == 3
    assert RackStatus.objects.filter(data_center=data_center).count() == 4
    assert Tenant.objects.filter(data_center=data_center).count() == 4
    assert Manufacturer.objects.filter(data_center=data_center).count() == 4
    assert DeviceType.objects.filter(data_center=data_center).count() == 4
    assert DeviceModel.objects.filter(data_center=data_center).count() == 4
    assert Rack.objects.filter(data_center=data_center).count() == 5
    assert Device.objects.filter(data_center=data_center).count() == 6

    call_command("seed_demo_datacenter", datacenter_id=data_center.id, verbosity=0)

    assert Room.objects.filter(data_center=data_center).count() == 3
    assert RackStatus.objects.filter(data_center=data_center).count() == 4
    assert Tenant.objects.filter(data_center=data_center).count() == 4
    assert Manufacturer.objects.filter(data_center=data_center).count() == 4
    assert DeviceType.objects.filter(data_center=data_center).count() == 4
    assert DeviceModel.objects.filter(data_center=data_center).count() == 4
    assert Rack.objects.filter(data_center=data_center).count() == 5
    assert Device.objects.filter(data_center=data_center).count() == 6

    mounted_devices = Device.objects.filter(data_center=data_center, rack__isnull=False)
    assert mounted_devices.count() == 6
    assert mounted_devices.exclude(model__isnull=True).count() == 6
    assert mounted_devices.exclude(type__isnull=True).count() == 6
    assert mounted_devices.exclude(tenant__isnull=True).count() == 6
