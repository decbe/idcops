import json
from collections import defaultdict

from django.core.cache import cache
from django.utils.functional import cached_property
from django.views.generic import DetailView
from PIL import Image

from dcrm.models import DevicePort, OnlineDevice, PatchCordNode, Rack
from dcrm.models.choices import ColorChoices, DeviceTypeChoices

from .mixins.base import BaseRequestMixin


class DeviceTopologyView(BaseRequestMixin, DetailView):
    model = OnlineDevice
    template_name = "topology/device_topology.html"
    CACHE_TIMEOUT = 180  # 缓存30分钟
    devices = set()

    @cached_property
    def get_port_ids(self):
        port_ids = self.object.ports.filter(
            connected_object_id__isnull=False,
            connected_to__app_label="dcrm",
            connected_to__model="deviceport",
        ).values_list("connected_object_id", flat=True)
        return port_ids

    def _get_graph_data(self, target_device):
        """获取设备拓扑关系图数据，优先从缓存获取"""
        cache_key = f"topology_graph_alal_{target_device.id}"
        graph_data = cache.get(cache_key)

        if not graph_data:
            graph_data = self._create_topology_data(target_device)
            cache.set(cache_key, graph_data, self.CACHE_TIMEOUT)
        return self._create_topology_data(target_device)

    def _create_topology_data(self, target_device):
        """创建拓扑图数据"""
        nodes = []
        edges = []
        connected_ports = DevicePort.objects.filter(
            pk__in=self.get_port_ids
        ).select_related("device")

        rack_groups = defaultdict(list)
        for port in connected_ports:
            rack_groups[port.device.rack.name].append(port)

        if target_device.rack.name not in rack_groups.keys():
            rack_groups.update({target_device.rack.name: []})

        processed_devices = set()

        # 记录设备间的连接数量
        connection_counts = {}

        def get_connection_key(source_id, target_id):
            """获取连接的唯一键（确保顺序一致）"""
            return tuple(sorted([source_id, target_id]))

        def get_curveness(source_id, target_id, index):
            """计算连接线的曲率"""
            key = get_connection_key(source_id, target_id)
            total = connection_counts.get(key, 1)
            if total == 1:
                return 0  # 只有一条连接时使用直线

            # 多条连接时使用不同的曲率
            if total == 2:
                # 两条线时，一条向上弯曲(0.2)，一条向下弯曲(-0.2)
                return 0.2 if index == 0 else -0.2
            else:
                # 三条或更多连接时，在 -0.3 到 0.3 之间平均分布
                max_curveness = 0.3
                if total == 3:
                    # 三条线：-0.3, 0, 0.3
                    return max_curveness * (index - 1)
                else:
                    # 四条或更多：在 -0.3 到 0.3 之间均匀分布
                    step = (2 * max_curveness) / (total - 1)
                    return max_curveness - (step * index)

        group_devices = {}

        def calculate_x_position(group, spacing=50):
            """计算节点的水平位置"""
            idx_map = {key: i for i, key in enumerate(rack_groups)}
            index = idx_map.get(group)
            groups = range(-spacing, (len(rack_groups) - 1) * spacing, spacing)
            counter = group_devices.get(group, 0) + 1
            group_devices[group] = counter
            x_position = list(groups)[index]
            if x_position == 0:
                x_position = -1.25
            return x_position * counter

        def add_device_node(device, is_target=False):
            """添加设备节点"""
            node_id = f"device_{device.id}"
            if node_id in processed_devices:
                return node_id, 0

            processed_devices.add(node_id)

            # 计算节点位置
            y = device.position  # 减小垂直间距，原来是 100
            x = calculate_x_position(device.rack.name, 20)
            width, height = [60, 60]
            im = Image.open(device.type.icon.path)
            width, height = im.size
            im.close()
            nodes.append(
                {
                    "id": node_id,
                    "name": f"{str(device.rack)}#{device.position:02d}U ({str(device.tenant)})",
                    "symbol": self._get_device_symbol(device.type.icon.url),
                    "symbolSize": [width, height],
                    "category": device.type.name,
                    "value": f"{device.name}#{device.position:02d}U",
                    "itemStyle": {
                        "color": ColorChoices.to_hex_color(device.type.color)
                    },
                    "label": {"show": True, "position": "bottom"},
                    "x": x,
                    "y": -y,
                }
            )
            return node_id, x

        # 添加目标设备
        target_node_id, target_x = add_device_node(target_device, is_target=True)

        # 按层级顺序处理连接的设备
        for group, ports in rack_groups.items():
            level_devices = []
            for port in ports:
                if not isinstance(port.connected_object, DevicePort):
                    continue
                self.devices.add(port.device)
                connected_port = port.connected_object
                connected_device = connected_port.device
                key = get_connection_key(
                    f"device_{target_device.id}",
                    f"device_{port.device.id}",
                )
                connection_counts[key] = connection_counts.get(key, 0) + 1

                level_devices.append((port.device, port, connected_port))
            # 处理当前层级的所有设备
            connection_indices = {}  # 记录每对设备间的连接索引
            for connected_device, port, connected_port in level_devices:

                connected_node_id, connected_x = add_device_node(connected_device)

                # 获取连接索引
                key = get_connection_key(target_node_id, connected_node_id)
                index = connection_indices.get(key, 0)
                connection_indices[key] = index + 1

                # 计算曲率
                curveness = get_curveness(target_node_id, connected_node_id, index) / 2
                # 添加连接关系
                edges.append(
                    {
                        "id": f"edge_{port.id}",
                        "source": target_node_id,
                        "target": connected_node_id,
                        "name": (
                            f"{str(port.device.rack.name)}#{port.device.position:02d}U -> {str(connected_port.device.rack.name)}#{connected_port.device.position:02d}U"
                        ),
                        "value": (f"{str(port.name)} -> {str(connected_port.name)}"),
                        "lineStyle": {
                            "color": self._get_connection_color(
                                port.patch_cord_nodes.all()
                            ),
                            "width": 3,
                            "cap": "round",
                            "curveness": curveness,
                        },
                        "label": {
                            "show": False,
                            "formatter": "{c}",
                            "fontSize": 10,
                            "color": "#666",
                            "backgroundColor": "rgba(255, 255, 255, 0.7)",
                            "padding": [4, 8],
                        },
                        "symbol": ["none", "none"],
                        "symbolSize": [0, 0],
                    }
                )
        return {"nodes": nodes, "edges": edges}

    def _get_device_symbol(self, url):
        """返回设备类型对应的图标URL"""
        host = self.request.build_absolute_uri("/").removesuffix("/")
        return f"image://{host}{url}"

    def _get_connection_color(self, nodes_queryset):
        """返回连接状态对应的颜色"""
        node = nodes_queryset.first()
        return ColorChoices.to_hex_color(node.color)

    def get_context_data(self, **kwargs):
        """准备ECharts所需的数据"""
        context = super().get_context_data(**kwargs)

        try:
            target_device = self.object

            # 获取拓扑数据
            graph_data = self._get_graph_data(target_device)

            # 准备设备类型分类数据
            categories = [
                {
                    "name": str(device.type),
                    "icon": self._get_device_symbol(device.type.icon.url),
                }
                for device in self.devices
            ]

            # 将数据转换为JSON字符串
            context.update(
                {
                    "nodes_json": json.dumps(graph_data["nodes"], ensure_ascii=False),
                    "edges_json": json.dumps(graph_data["edges"], ensure_ascii=False),
                    "categories_json": json.dumps(categories, ensure_ascii=False),
                    "return_url": self.object.get_absolute_url(),
                }
            )

        except Exception as e:
            import traceback

            print("Error:", str(e))
            print("Traceback:", traceback.format_exc())
            context["error"] = str(e)

        return context


class RackTopologyView(BaseRequestMixin, DetailView):
    """机柜拓扑图
    只显示机柜与机柜直接有多少个设备节点连接，
    本机柜内部的设备节点也显示，但是不显示连接线
    """

    model = Rack
    template_name = "topology/rack_topology.html"
    CACHE_TIMEOUT = 1  # 缓存30分钟

    def _get_graph_data(self, target_rack):
        """获取机柜拓扑关系图数据，优先从缓存获取"""
        cache_key = f"rack_topology_graph_{target_rack.id}"
        graph_data = cache.get(cache_key)

        if not graph_data:
            graph_data = self._create_topology_data(target_rack)
            cache.set(cache_key, graph_data, self.CACHE_TIMEOUT)

        return graph_data

    def _get_rack_symbol(self):
        """返回机柜图标URL"""
        icon_file = DeviceTypeChoices.get_symbol("rack")
        return f"image://{icon_file}"

    def _create_topology_data(self, target_rack):
        """创建机柜拓扑图数据"""
        nodes = []
        edges = []
        processed_racks = set()

        def add_rack_node(rack, is_target=False):
            """添加机柜节点"""
            node_id = f"rack_{rack.id}"
            if node_id in processed_racks:
                return node_id

            processed_racks.add(node_id)

            # 获取机柜内的设备数量
            device_count = rack.mounted_devices.count()
            patch_cord_count = PatchCordNode.objects.filter(rack=rack).count()
            nodes.append(
                {
                    "id": node_id,
                    "name": f"{device_count} 设备, {patch_cord_count} 跳线节点",
                    "symbol": "rect",
                    "symbolSize": [90, 150],
                    "value": (f"{rack.name} - {patch_cord_count} 节点"),
                    "itemStyle": {
                        "color": ColorChoices.to_hex_color(rack.status.color),
                        "borderWidth": 2,
                        "borderColor": "#333",
                    },
                    "label": {
                        "show": True,
                        "position": "bottom",
                        "formatter": "{c}",
                        "fontSize": 12,
                    },
                }
            )
            return node_id

        # 添加目标机柜节点
        target_node_id = add_rack_node(target_rack, is_target=True)

        # 获取与目标机柜相连的其他机柜
        connected_racks = set()
        for device in target_rack.mounted_devices.all():
            for port in device.ports.filter(connected_object_id__isnull=False):
                if not isinstance(port.connected_object, DevicePort):
                    continue
                connected_device = port.connected_object.device
                if connected_device.rack != target_rack:
                    connected_racks.add(connected_device.rack)

        # 添加相连机柜的节点和连接
        for connected_rack in connected_racks:
            connected_node_id = add_rack_node(connected_rack)

            # 计算两个机柜之间的连接数量
            connection_count = 0
            for device in target_rack.mounted_devices.all():
                for port in device.ports.filter(connected_object_id__isnull=False):
                    if not isinstance(port.connected_object, DevicePort):
                        continue
                    if port.connected_object.device.rack == connected_rack:
                        connection_count += 1

            # 添加连接关系
            edges.append(
                {
                    "source": target_node_id,
                    "target": connected_node_id,
                    "value": f"{connection_count} 连接",
                    "symbolSize": [10, 10],
                    "lineStyle": {
                        "width": min(
                            connection_count, 8
                        ),  # 连接线宽度随连接数增加而增加，但最大为8
                        "color": "#666",
                        "type": "solid",
                    },
                    "label": {
                        "show": True,
                        "formatter": "{c}",
                        "fontSize": 12,
                        "color": "#666",
                    },
                }
            )

        return {"nodes": nodes, "edges": edges}

    def get_context_data(self, **kwargs):
        """准备ECharts所需的数据"""
        context = super().get_context_data(**kwargs)

        try:
            target_rack = self.object

            # 获取拓扑数据
            graph_data = self._get_graph_data(target_rack)

            # 将数据转换为JSON字符串
            context.update(
                {
                    "nodes_json": json.dumps(graph_data["nodes"], ensure_ascii=False),
                    "edges_json": json.dumps(graph_data["edges"], ensure_ascii=False),
                    "return_url": self.object.get_absolute_url(),
                }
            )

        except Exception as e:
            import traceback

            print("Error:", str(e))
            print("Traceback:", traceback.format_exc())
            context["error"] = str(e)

        return context
