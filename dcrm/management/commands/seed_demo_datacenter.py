from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

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
from dcrm.models.choices import (
    DeviceStatusChoices,
    DeviceTypeChoices,
    RackTypeChoices,
    TenantTypeChoices,
)


class Command(BaseCommand):
    """Create demo seed data for a data center."""

    help = "为当前数据中心创建演示初始化数据"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--datacenter-id",
            type=int,
            help="指定要初始化的数据中心ID；不传则使用第一条数据中心",
        )
        parser.add_argument(
            "--datacenter-name",
            type=str,
            help="指定要初始化的数据中心名称；优先级低于 --datacenter-id",
        )

    def handle(self, *args, **options):
        """Execute the seed workflow."""
        data_center = self._get_data_center(options)

        with transaction.atomic():
            rooms = self._seed_rooms(data_center)
            rack_statuses = self._seed_rack_statuses(data_center)
            tenants = self._seed_tenants(data_center)
            manufacturers = self._seed_manufacturers(data_center)
            device_types = self._seed_device_types(data_center)
            device_models = self._seed_device_models(
                data_center, manufacturers, device_types
            )
            racks = self._seed_racks(data_center, rooms, rack_statuses, tenants)
            devices = self._seed_devices(
                data_center, racks, device_models, device_types, tenants
            )

        self.stdout.write(self.style.SUCCESS("演示数据初始化完成"))
        summary = (
            f"数据中心: {data_center.name} | 房间: {len(rooms)} | "
            f"机柜状态: {len(rack_statuses)} | 租户: {len(tenants)} | "
            f"厂商: {len(manufacturers)} | 设备类型: {len(device_types)} | "
            f"设备型号: {len(device_models)} | "
            f"机柜: {len(racks)} | 设备: {len(devices)}"
        )
        self.stdout.write(summary)

    def _get_data_center(self, options) -> DataCenter:
        data_center_id = options.get("datacenter_id")
        data_center_name = options.get("datacenter_name")

        if data_center_id:
            try:
                return DataCenter.objects.get(pk=data_center_id)
            except DataCenter.DoesNotExist as exc:
                raise CommandError(f"未找到数据中心 ID={data_center_id}") from exc

        if data_center_name:
            try:
                return DataCenter.objects.get(name=data_center_name)
            except DataCenter.DoesNotExist as exc:
                raise CommandError(f"未找到数据中心名称={data_center_name}") from exc

        data_center = DataCenter.objects.order_by("id").first()
        if not data_center:
            raise CommandError("当前数据库中没有可用的数据中心")
        return data_center

    def _seed_rooms(self, data_center: DataCenter) -> list[Room]:
        room_specs = [
            {
                "name": "A区-1F",
                "cname": "一楼A区",
                "description": "靠近核心配电间的主机房区域，适合承载高密度业务设备。",
                "address": data_center.physical_address or "",
                "default": True,
                "rows": 32,
                "cols": 18,
            },
            {
                "name": "B区-2F",
                "cname": "二楼B区",
                "description": "业务隔离区，主要放置测试和共享资源。",
                "address": data_center.physical_address or "",
                "rows": 28,
                "cols": 16,
            },
            {
                "name": "VIP机房",
                "cname": "VIP专用机房",
                "description": "用于重要客户与专属资源的独立小机房。",
                "address": data_center.physical_address or "",
                "rows": 20,
                "cols": 12,
            },
        ]

        rooms = []
        for spec in room_specs:
            room, _ = Room.objects.update_or_create(
                data_center=data_center,
                name=spec["name"],
                defaults=spec,
            )
            rooms.append(room)
        return rooms

    def _seed_rack_statuses(self, data_center: DataCenter) -> list[RackStatus]:
        status_specs = [
            {
                "name": "空闲",
                "description": "可直接分配给新租户或用于预留。",
                "allowed_mount": False,
                "shared": True,
            },
            {
                "name": "预留",
                "description": "已预留给客户，允许后续上架。",
                "allowed_mount": True,
                "shared": True,
            },
            {
                "name": "使用中",
                "description": "已经正式交付并允许上架设备。",
                "allowed_mount": True,
                "shared": True,
            },
            {
                "name": "已释放",
                "description": "原客户已退租，当前尚未重新分配。",
                "allowed_mount": False,
                "shared": True,
            },
        ]

        statuses = []
        for spec in status_specs:
            status, _ = RackStatus.objects.update_or_create(
                data_center=data_center,
                name=spec["name"],
                defaults=spec,
            )
            statuses.append(status)
        return statuses

    def _seed_tenants(self, data_center: DataCenter) -> list[Tenant]:
        tenant_specs = [
            {
                "name": "星云科技有限公司",
                "type": TenantTypeChoices.EXTERNAL,
                "description": "核心互联网业务客户，主要使用生产环境资源。",
                "address": "上海市浦东新区张江高科技园区",
                "website": "https://www.example.com",
            },
            {
                "name": "华南运营支持部",
                "type": TenantTypeChoices.INTERNAL,
                "description": "内部运维与平台支撑团队。",
                "address": "广州市天河区数据中心园区",
                "website": "https://intranet.example.com",
            },
            {
                "name": "海川云服务",
                "type": TenantTypeChoices.PROVIDER,
                "description": "第三方基础设施合作方，用于托管与转售资源。",
                "address": "深圳市南山区科技园",
                "website": "https://cloud.example.com",
            },
            {
                "name": "启明金融租户",
                "type": TenantTypeChoices.EXTERNAL_SHARED,
                "description": "共享型业务租户，适合演示多客户共用资源。",
                "address": "北京市海淀区中关村软件园",
                "website": "https://finance.example.com",
            },
        ]

        tenants = []
        for spec in tenant_specs:
            tenant, _ = Tenant.objects.update_or_create(
                data_center=data_center,
                name=spec["name"],
                defaults=spec,
            )
            tenants.append(tenant)
        return tenants

    def _seed_manufacturers(self, data_center: DataCenter) -> list[Manufacturer]:
        manufacturer_specs = [
            {
                "name": "Dell",
                "name_cn": "戴尔",
                "description": "服务器和存储设备制造商。",
                "website": "https://www.dell.com",
                "shared": True,
            },
            {
                "name": "Huawei",
                "name_cn": "华为",
                "description": "网络和服务器设备制造商。",
                "website": "https://www.huawei.com",
                "shared": True,
            },
            {
                "name": "H3C",
                "name_cn": "新华三",
                "description": "网络设备与企业基础架构制造商。",
                "website": "https://www.h3c.com",
                "shared": True,
            },
            {
                "name": "APC",
                "name_cn": "施耐德电气 APC",
                "description": "UPS 与供电设备制造商。",
                "website": "https://www.apc.com",
                "shared": True,
            },
        ]

        manufacturers = []
        for spec in manufacturer_specs:
            manufacturer, _ = Manufacturer.objects.update_or_create(
                data_center=data_center,
                name=spec["name"],
                defaults=spec,
            )
            manufacturers.append(manufacturer)
        return manufacturers

    def _seed_device_types(self, data_center: DataCenter) -> list[DeviceType]:
        type_specs = [
            {
                "name": "服务器",
                "code": DeviceTypeChoices.SERVER,
                "description": "用于承载计算与应用服务。",
                "shared": True,
            },
            {
                "name": "交换机",
                "code": DeviceTypeChoices.SWITCH,
                "description": "用于机柜内与网络层接入。",
                "shared": True,
            },
            {
                "name": "路由器",
                "code": DeviceTypeChoices.ROUTER,
                "description": "用于不同网络边界之间的路由互联。",
                "shared": True,
            },
            {
                "name": "UPS",
                "code": DeviceTypeChoices.UPS,
                "description": "用于机柜供电和断电保护。",
                "shared": True,
            },
        ]

        device_types = []
        for spec in type_specs:
            device_type, _ = DeviceType.objects.update_or_create(
                data_center=data_center,
                name=spec["name"],
                defaults=spec,
            )
            device_types.append(device_type)
        return device_types

    def _seed_device_models(
        self,
        data_center: DataCenter,
        manufacturers: list[Manufacturer],
        device_types: list[DeviceType],
    ) -> list[DeviceModel]:
        manufacturer_map = {item.name: item for item in manufacturers}
        device_type_map = {item.name: item for item in device_types}

        model_specs = [
            {
                "name": "PowerEdge R760",
                "manufacturer": manufacturer_map["Dell"],
                "type": device_type_map["服务器"],
                "height": 1,
                "ethernet_port_count": 2,
                "fiber_port_count": 0,
                "console_port_count": 1,
                "usb_port_count": 4,
                "power_port_count": 2,
                "mgmt_port_count": 1,
                "other_port_count": 0,
                "description": "2U 通用双路服务器，适合业务与应用演示。",
                "shared": True,
            },
            {
                "name": "CloudEngine S5735-48T4X",
                "manufacturer": manufacturer_map["Huawei"],
                "type": device_type_map["交换机"],
                "height": 1,
                "ethernet_port_count": 48,
                "fiber_port_count": 4,
                "console_port_count": 1,
                "usb_port_count": 1,
                "power_port_count": 2,
                "mgmt_port_count": 1,
                "other_port_count": 0,
                "description": "48 口万兆接入交换机，适合演示网络层设备。",
                "shared": True,
            },
            {
                "name": "MSR3620",
                "manufacturer": manufacturer_map["H3C"],
                "type": device_type_map["路由器"],
                "height": 1,
                "ethernet_port_count": 8,
                "fiber_port_count": 2,
                "console_port_count": 1,
                "usb_port_count": 1,
                "power_port_count": 2,
                "mgmt_port_count": 1,
                "other_port_count": 0,
                "description": "中小型分支路由器，适合边界互联演示。",
                "shared": True,
            },
            {
                "name": "Smart-UPS 3000",
                "manufacturer": manufacturer_map["APC"],
                "type": device_type_map["UPS"],
                "height": 2,
                "ethernet_port_count": 1,
                "fiber_port_count": 0,
                "console_port_count": 1,
                "usb_port_count": 1,
                "power_port_count": 2,
                "mgmt_port_count": 1,
                "other_port_count": 0,
                "description": "机柜级 UPS 设备，用于供电演示。",
                "shared": True,
            },
        ]

        device_models = []
        for spec in model_specs:
            device_model, _ = DeviceModel.objects.update_or_create(
                data_center=data_center,
                name=spec["name"],
                defaults=spec,
            )
            device_models.append(device_model)
        return device_models

    def _seed_racks(
        self,
        data_center: DataCenter,
        rooms: list[Room],
        statuses: list[RackStatus],
        tenants: list[Tenant],
    ) -> list[Rack]:
        room_map = {room.name: room for room in rooms}
        status_map = {status.name: status for status in statuses}
        tenant_map = {tenant.name: tenant for tenant in tenants}

        rack_specs = [
            {
                "name": "A1-R01",
                "room": room_map["A区-1F"],
                "status": status_map["使用中"],
                "tenant": tenant_map["星云科技有限公司"],
                "rack_type": RackTypeChoices.EXCLUSIVE,
                "pdu_count": 24,
                "pdu_16a_count": 8,
                "rated_power_kw": 10.0,
                "contract_power": 32,
                "opening_date": date(2025, 3, 1),
                "description": "主生产资源机柜，承载核心业务服务器。",
                "row": 1,
                "col": 1,
            },
            {
                "name": "A1-R02",
                "room": room_map["A区-1F"],
                "status": status_map["预留"],
                "tenant": tenant_map["华南运营支持部"],
                "rack_type": RackTypeChoices.SHARED,
                "pdu_count": 20,
                "pdu_16a_count": 6,
                "rated_power_kw": 8.0,
                "contract_power": 24,
                "opening_date": date(2025, 6, 15),
                "description": "内部运维共享机柜，方便演示预留和共享场景。",
                "row": 1,
                "col": 2,
            },
            {
                "name": "B2-R01",
                "room": room_map["B区-2F"],
                "status": status_map["使用中"],
                "tenant": tenant_map["海川云服务"],
                "rack_type": RackTypeChoices.EXCLUSIVE,
                "pdu_count": 24,
                "pdu_16a_count": 8,
                "rated_power_kw": 10.0,
                "contract_power": 32,
                "opening_date": date(2025, 8, 20),
                "description": "第三方合作资源机柜，适合网络设备演示。",
                "row": 2,
                "col": 1,
            },
            {
                "name": "VIP-R01",
                "room": room_map["VIP机房"],
                "status": status_map["空闲"],
                "tenant": tenant_map["启明金融租户"],
                "rack_type": RackTypeChoices.EXCLUSIVE,
                "pdu_count": 12,
                "pdu_16a_count": 4,
                "rated_power_kw": 6.0,
                "contract_power": 16,
                "opening_date": date(2025, 11, 1),
                "description": "专属客户独立机柜，当前为空闲状态。",
                "row": 1,
                "col": 1,
            },
            {
                "name": "VIP-R02",
                "room": room_map["VIP机房"],
                "status": status_map["已释放"],
                "tenant": tenant_map["启明金融租户"],
                "rack_type": RackTypeChoices.EXCLUSIVE,
                "pdu_count": 12,
                "pdu_16a_count": 2,
                "rated_power_kw": 4.4,
                "contract_power": 12,
                "opening_date": date(2024, 12, 1),
                "description": "历史机柜示例，演示已释放状态。",
                "row": 1,
                "col": 2,
            },
        ]

        racks = []
        for spec in rack_specs:
            rack, _ = Rack.objects.update_or_create(
                room=spec["room"],
                name=spec["name"],
                defaults={
                    "data_center": data_center,
                    "room": spec["room"],
                    "name": spec["name"],
                    "status": spec["status"],
                    "tenant": spec["tenant"],
                    "rack_type": spec["rack_type"],
                    "pdu_count": spec["pdu_count"],
                    "pdu_16a_count": spec["pdu_16a_count"],
                    "rated_power_kw": spec["rated_power_kw"],
                    "contract_power": spec["contract_power"],
                    "opening_date": spec["opening_date"],
                    "description": spec["description"],
                    "row": spec["row"],
                    "col": spec["col"],
                },
            )
            racks.append(rack)
        return racks

    def _seed_devices(
        self,
        data_center: DataCenter,
        racks: list[Rack],
        device_models: list[DeviceModel],
        device_types: list[DeviceType],
        tenants: list[Tenant],
    ) -> list[Device]:
        rack_map = {rack.name: rack for rack in racks}
        model_map = {model.name: model for model in device_models}
        type_map = {device_type.name: device_type for device_type in device_types}
        tenant_map = {tenant.name: tenant for tenant in tenants}

        device_specs = [
            {
                "name": "srv-a1-01",
                "serial_number": "SN-R760-0001",
                "rack": rack_map["A1-R01"],
                "position": 1,
                "model": model_map["PowerEdge R760"],
                "type": type_map["服务器"],
                "tenant": tenant_map["星云科技有限公司"],
                "status": DeviceStatusChoices.MOUNTED,
            },
            {
                "name": "srv-a1-02",
                "serial_number": "SN-R760-0002",
                "rack": rack_map["A1-R01"],
                "position": 3,
                "model": model_map["PowerEdge R760"],
                "type": type_map["服务器"],
                "tenant": tenant_map["星云科技有限公司"],
                "status": DeviceStatusChoices.MOUNTED,
            },
            {
                "name": "sw-a1-01",
                "serial_number": "SN-S5735-0001",
                "rack": rack_map["A1-R02"],
                "position": 1,
                "model": model_map["CloudEngine S5735-48T4X"],
                "type": type_map["交换机"],
                "tenant": tenant_map["华南运营支持部"],
                "status": DeviceStatusChoices.MOUNTED,
            },
            {
                "name": "rt-b2-01",
                "serial_number": "SN-MSR3620-0001",
                "rack": rack_map["B2-R01"],
                "position": 1,
                "model": model_map["MSR3620"],
                "type": type_map["路由器"],
                "tenant": tenant_map["海川云服务"],
                "status": DeviceStatusChoices.MOUNTED,
            },
            {
                "name": "ups-vip-01",
                "serial_number": "SN-UPS-0001",
                "rack": rack_map["VIP-R01"],
                "position": 1,
                "model": model_map["Smart-UPS 3000"],
                "type": type_map["UPS"],
                "tenant": tenant_map["启明金融租户"],
                "status": DeviceStatusChoices.DRAFT,
            },
            {
                "name": "sw-b2-02",
                "serial_number": "SN-S5735-0002",
                "rack": rack_map["B2-R01"],
                "position": 5,
                "model": model_map["CloudEngine S5735-48T4X"],
                "type": type_map["交换机"],
                "tenant": tenant_map["海川云服务"],
                "status": DeviceStatusChoices.MOUNTED,
            },
        ]

        devices = []
        for spec in device_specs:
            device, _ = Device.objects.update_or_create(
                data_center=data_center,
                name=spec["name"],
                defaults={
                    "data_center": data_center,
                    "rack": spec["rack"],
                    "position": spec["position"],
                    "model": spec["model"],
                    "type": spec["type"],
                    "tenant": spec["tenant"],
                    "status": spec["status"],
                    "height": spec["model"].height,
                    "serial_number": spec["serial_number"],
                },
            )
            devices.append(device)
        return devices
