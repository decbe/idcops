from dataclasses import dataclass, field
from typing import Callable, Dict, List

from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


@dataclass
class MenuItem:
    """菜单项数据类"""

    name: str  # 菜单名称
    icon: str = "fa-circle-o"  # 图标类名
    url: str = "#"  # URL
    url_name: str = ""  # URL name
    badge_text: str = ""  # 静态徽章文本
    badge_class: str = ""  # 徽章样式类
    children: List = None  # 子菜单
    permission: str = None  # 权限标识
    icon_color: str = ""  # 图标颜色
    badge_callback: Callable = None  # 徽章数量回调函数
    target: str = ""  # 链接打开方式: _blank, _self 等
    active_patterns: List[str] = field(default_factory=list)  # 新增：激活模式列表
    url_params: Dict[str, str] = field(default_factory=dict)  # 新增：URL参数

    def __post_init__(self):
        self.children = self.children or []
        self.active = False
        # 如果有 url_name，解析成 url
        if self.url_name and self.url == "#":
            try:
                if self.url_params:
                    self.url = (
                        reverse(self.url_name)
                        + "?"
                        + "&".join([f"{k}={v}" for k, v in self.url_params.items()])
                    )
                else:
                    self.url = reverse(self.url_name)
            except NoReverseMatch:
                self.url = "#"

    @property
    def dynamic_badge_text(self):
        """获取徽章文本，优先使用回调函数"""
        if self.badge_callback:
            try:
                count = self.badge_callback()
                return str(count) if count > 0 else ""
            except BaseException:
                return self.badge_text
        return self.badge_text

    def copy(self):
        """深度复制菜单项"""
        new_item = MenuItem(
            name=self.name,
            icon=self.icon,
            url=self.url,
            url_name=self.url_name,
            badge_text=self.badge_text,
            badge_class=self.badge_class,
            permission=self.permission,
            icon_color=self.icon_color,
            badge_callback=self.badge_callback,  # 复制回调函数
            target=self.target,
            active_patterns=self.active_patterns,
            url_params=self.url_params,
        )
        new_item.children = [child.copy() for child in self.children]
        new_item.active = self.active
        return new_item


class MenuRegistry:
    """菜单注册器"""

    def __init__(self):
        self._registry = {}  # 存储菜单项的字典
        self._sections = {}  # 存储菜单分区的字典
        self._base_menus = {}  # 存储预生成的基础菜单结构
        self._superuser_menus = None  # 超级用户的基础菜单

    def register(self, section: str, item: MenuItem):
        """注册菜单项"""
        if section not in self._registry:
            self._registry[section] = []
        self._registry[section].append(item)
        # 注册新菜单项时清除基础菜单缓存
        self._base_menus = {}
        self._superuser_menus = None

    def register_section(self, section: str, name: str):
        """注册菜单分区"""
        self._sections[section] = name
        # 注册新分区时清除基础菜单缓存
        self._base_menus = {}
        self._superuser_menus = None

    def get_sections(self) -> Dict[str, str]:
        """获取所有菜单分区"""
        return self._sections

    def _has_permission(self, user, item: MenuItem) -> bool:
        """检查用户是否有权限访问菜单项"""
        if not item.permission:
            return True
        return user.has_perm(item.permission)

    def _update_badge_counts(self, item: MenuItem):
        """更新单个菜单项的徽章数量"""
        if item.badge_callback:
            item.badge_text = item.dynamic_badge_text
        if item.children:
            for child in item.children:
                self._update_badge_counts(child)

    def _set_active_menu(self, item: MenuItem, current_url_name: str) -> bool:
        """递归设置菜单项的活动状态，返回是否找到匹配项"""
        # 检查当前项
        if item.url_name == current_url_name or any(
            pattern == current_url_name for pattern in item.active_patterns
        ):
            item.active = True
            return True

        # 检查子项
        if item.children:
            for child in item.children:
                if self._set_active_menu(child, current_url_name):
                    item.active = True  # 子项激活时，父项也激活
                    return True
        return False

    def _get_base_menus_for_user(self, user):
        """获取用户的基础菜单结构（应用级缓存）"""
        if user.is_superuser:
            # 超级用户菜单只需生成一次
            if self._superuser_menus is None:
                self._superuser_menus = {
                    section: [item.copy() for item in items]
                    for section, items in self._registry.items()
                }
            return {
                section: [item.copy() for item in items]
                for section, items in self._superuser_menus.items()
            }

        # 普通用户按权限组缓存
        # 使用用户权限的哈希作为缓存键
        perm_key = frozenset(user.get_all_permissions())

        if perm_key not in self._base_menus:
            # 为该权限组生成基础菜单
            filtered_menus = {}
            for section, items in self._registry.items():
                filtered_items = []
                for item in items:
                    if self._has_permission(user, item):
                        filtered_items.append(item.copy())
                if filtered_items:
                    filtered_menus[section] = filtered_items

            # 存储到应用级缓存
            self._base_menus[perm_key] = filtered_menus

        # 返回菜单的深拷贝，以便可以安全修改
        return {
            section: [item.copy() for item in items]
            for section, items in self._base_menus[perm_key].items()
        }

    def _reset_active_state(self, item: MenuItem):
        """递归重置菜单项的active状态"""
        item.active = False
        if item.children:
            for child in item.children:
                self._reset_active_state(child)

    def get_menus(
        self, user=None, current_url_name: str = None
    ) -> Dict[str, List[MenuItem]]:
        """获取菜单列表（使用应用级缓存）"""
        if user is None or not user.is_authenticated:
            return {}

        # 从应用级缓存获取基础菜单结构
        menus = self._get_base_menus_for_user(user)

        # 更新动态徽章数量
        for items in menus.values():
            for item in items:
                self._update_badge_counts(item)

        # 设置当前活动菜单
        if current_url_name:
            for items in menus.values():
                for item in items:
                    # 重置所有菜单项的active状态
                    self._reset_active_state(item)
                    # 设置当前URL对应的菜单项为active
                    if self._set_active_menu(item, current_url_name):
                        break  # 找到匹配项后就停止搜索

        return menus

    def clear_cache(self):
        """清除应用级缓存"""
        self._base_menus = {}
        self._superuser_menus = None


# 创建全局菜单注册器实例
menu_registry = MenuRegistry()


# 示例徽章回调函数
def get_testing_devices():
    """获取测试已到期的主机数量"""
    return 0
    from .models import DeviceHost

    hosts = DeviceHost.objects.filter(
        test_end_time__isnull=False, test_end_time__lt=timezone.now().date()
    )
    return hosts.count()


# 注册默认菜单
def register_default_menus():
    # 注册分区
    menu_registry.register_section("main", _("主菜单"))
    menu_registry.register_section("system", _("系统设置"))
    menu_registry.register_section("help", _("帮助文档"))

    # 主导航
    menu_registry.register(
        "main",
        MenuItem(
            name=_("仪表盘"),
            icon="fa-dashboard",
            url_name="index",
        ),
    )

    # 设备管理
    devices = MenuItem(
        name=_("设备管理"),
        icon="fa-server",
        children=[
            MenuItem(
                name=_("在线设备"),
                url_name="online_device_list",
                permission="dcrm.view_onlinedevice",
                active_patterns=[
                    "online_device_detail",
                    "online_device_create",
                    "online_device_update",
                    "online_device_delete",
                    "online_device_import",
                ],
            ),
            MenuItem(
                name=_("所有设备"),
                url_name="device_list",
                permission="dcrm.view_device",
                active_patterns=[
                    "device_detail",
                    "device_create",
                    "device_update",
                    "device_delete",
                    "device_import",
                    "device_topology",
                ],
            ),
            MenuItem(
                name=_("设备端口"),
                url_name="device_port_list",
                permission="dcrm.view_deviceport",
                active_patterns=[
                    "device_port_detail",
                    "device_port_create",
                    "device_port_update",
                    "device_port_delete",
                    "device_port_import",
                    "device_port_topology",
                ],
            ),
            MenuItem(
                name=_("设备型号"),
                url_name="device_model_list",
                permission="dcrm.view_devicemodel",
                active_patterns=[
                    "device_model_detail",
                    "device_model_create",
                    "device_model_update",
                    "device_model_delete",
                    "device_model_import",
                ],
            ),
            MenuItem(
                name=_("设备类型"),
                url_name="device_type_list",
                permission="dcrm.view_devicetype",
                active_patterns=[
                    "device_type_detail",
                    "device_type_create",
                    "device_type_update",
                    "device_type_delete",
                    "device_type_import",
                ],
            ),
            MenuItem(
                name=_("设备主机"),
                url_name="device_host_list",
                badge_callback=get_testing_devices,
                badge_class="bg-yellow",
                permission="dcrm.view_devicehost",
                active_patterns=[
                    "device_host_detail",
                    "device_host_create",
                    "device_host_update",
                    "device_host_delete",
                    "device_host_import",
                ],
            ),
        ],
    )
    menu_registry.register("main", devices)

    # 机柜管理
    racks = MenuItem(
        name=_("机柜管理"),
        icon="fa-building",
        children=[
            MenuItem(
                name=_("机柜信息"),
                url_name="rack_list",
                permission="dcrm.view_rack",
                active_patterns=[
                    "rack_detail",
                    "rack_create",
                    "rack_update",
                    "rack_delete",
                    "rack_import",
                    "rack_topology",
                ],
            ),
            MenuItem(
                name=_("房间管理"),
                url_name="room_list",
                permission="dcrm.view_room",
                active_patterns=[
                    "room_detail",
                    "room_create",
                    "room_update",
                    "room_delete",
                    "room_import",
                    "room_rack_maps",
                ],
            ),
            MenuItem(
                name=_("机柜状态"),
                url_name="rack_status_list",
                permission="dcrm.view_rack_status",
                active_patterns=[
                    "rack_status_detail",
                    "rack_status_create",
                    "rack_status_update",
                    "rack_status_delete",
                    "rack_status_import",
                ],
            ),
            MenuItem(
                name=_("机柜PDU"),
                url_name="rack_pdu_list",
                permission="dcrm.view_rack_pdu",
                active_patterns=[
                    "rack_pdu_detail",
                    "rack_pdu_create",
                    "rack_pdu_update",
                    "rack_pdu_delete",
                    "rack_pdu_import",
                ],
            ),
        ],
    )
    menu_registry.register("main", racks)

    # 跳线管理
    cables = MenuItem(
        name=_("跳线管理"),
        icon="fa-random",
        children=[
            MenuItem(
                name=_("跳线信息"),
                url_name="patch_cord_list",
                permission="dcrm.view_patch_cord",
                active_patterns=[
                    "patch_cord_detail",
                    "patch_cord_create",
                    "patch_cord_update",
                    "patch_cord_delete",
                    "patch_cord_import",
                ],
            ),
            MenuItem(
                name=_("跳线节点"),
                url_name="patch_cord_node_list",
                permission="dcrm.view_patch_cord_node",
                active_patterns=[
                    "patch_cord_node_detail",
                    "patch_cord_node_create",
                    "patch_cord_node_update",
                    "patch_cord_node_delete",
                    "patch_cord_node_import",
                ],
            ),
        ],
    )
    menu_registry.register("main", cables)

    # 文档管理
    documents = MenuItem(
        name=_("文档管理"),
        icon="fa-file",
        children=[
            MenuItem(
                name=_("文档列表"),
                url_name="document_list",
                permission="dcrm.view_document",
                active_patterns=[
                    "document_detail",
                    "document_create",
                    "document_update",
                    "document_delete",
                    "document_import",
                ],
            ),
            MenuItem(
                name=_("文档分类"),
                url_name="category_list",
                permission="dcrm.view_category",
                active_patterns=[
                    "category_detail",
                    "category_create",
                    "category_update",
                    "category_delete",
                    "category_import",
                ],
            ),
        ],
    )
    menu_registry.register("main", documents)
    # 租户管理
    tenants = MenuItem(
        name=_("租户&联系人"),
        icon="fa-group",
        children=[
            MenuItem(
                name=_("租户管理"),
                url_name="tenant_list",
                permission="dcrm.view_tenant",
                active_patterns=[
                    "tenant_detail",
                    "tenant_create",
                    "tenant_update",
                    "tenant_delete",
                    "tenant_import",
                ],
            ),
            # 厂商管理
            MenuItem(
                name=_("厂商信息"),
                url_name="manufacturer_list",
                permission="dcrm.view_manufacturer",
                active_patterns=[
                    "manufacturer_detail",
                    "manufacturer_create",
                    "manufacturer_update",
                    "manufacturer_delete",
                    "manufacturer_import",
                ],
            ),
            # 联系人管理
            MenuItem(
                name=_("联系人信息"),
                url_name="contact_list",
                permission="dcrm.view_contact",
                active_patterns=[
                    "contact_detail",
                    "contact_create",
                    "contact_update",
                    "contact_delete",
                    "contact_import",
                ],
            ),
            # 联系人角色
            MenuItem(
                name=_("联系人角色"),
                url_name="contact_role_list",
                permission="dcrm.view_contact_role",
                active_patterns=[
                    "contact_role_detail",
                    "contact_role_create",
                    "contact_role_update",
                    "contact_role_delete",
                    "contact_role_import",
                ],
            ),
        ],
    )
    menu_registry.register("main", tenants)

    # 物品管理
    items = MenuItem(
        name=_("物品管理"),
        icon="fa-th",
        children=[
            MenuItem(
                name=_("库存物品"),
                url_name="item_instance_list",
                permission="dcrm.view_iteminstance",
                active_patterns=[
                    "item_instance_detail",
                    "item_instance_create",
                    "item_instance_update",
                    "item_instance_delete",
                    "item_instance_import",
                    "item_instance_bulk_create",
                ],
            ),
            MenuItem(
                name=_("物品"),
                url_name="inventory_item_list",
                permission="dcrm.view_inventoryitem",
                active_patterns=[
                    "inventory_item_detail",
                    "inventory_item_create",
                    "inventory_item_update",
                    "inventory_item_delete",
                    "inventory_item_import",
                ],
            ),
            MenuItem(
                name=_("物品类别"),
                url_name="item_category_list",
                permission="dcrm.view_itemcategory",
                active_patterns=[
                    "item_category_detail",
                    "item_category_create",
                    "item_category_update",
                    "item_category_delete",
                    "item_category_import",
                ],
            ),
            MenuItem(
                name=_("仓库管理"),
                url_name="warehouse_list",
                permission="dcrm.view_warehouse",
                active_patterns=[
                    "warehouse_detail",
                    "warehouse_create",
                    "warehouse_update",
                    "warehouse_delete",
                    "warehouse_import",
                ],
            ),
        ],
    )
    menu_registry.register("main", items)

    # 网络管理
    networks = MenuItem(
        name=_("IP地址管理"),
        icon="fa-sitemap",
        children=[
            MenuItem(
                name=_("子网管理"),
                url_name="subnet_list",
                permission="dcrm.view_subnet",
                active_patterns=[
                    "subnet_detail",
                    "subnet_create",
                    "subnet_update",
                    "subnet_delete",
                    "subnet_import",
                ],
            ),
            MenuItem(
                name=_("IP地址"),
                url_name="ip_address_list",
                permission="dcrm.view_ip",
                active_patterns=[
                    "ip_address_detail",
                    "ip_address_create",
                    "ip_address_update",
                    "ip_address_delete",
                    "ip_address_import",
                ],
            ),
            MenuItem(
                name=_("VLAN管理"),
                url_name="vlan_list",
                permission="dcrm.view_vlan",
                active_patterns=[
                    "vlan_detail",
                    "vlan_create",
                    "vlan_update",
                    "vlan_delete",
                    "vlan_import",
                ],
            ),
            MenuItem(
                name=_("网络产品"),
                url_name="network_product_list",
                permission="dcrm.view_network_product",
                active_patterns=[
                    "network_product_detail",
                    "network_product_create",
                    "network_product_update",
                    "network_product_delete",
                    "network_product_import",
                ],
            ),
        ],
    )
    menu_registry.register("main", networks)

    custom = MenuItem(
        name=_("自定义"),
        icon="fa-wrench",
        children=[
            MenuItem(
                name=_("标签管理"),
                url_name="tag_list",
                permission="dcrm.view_tag",
                active_patterns=[
                    "tag_detail",
                    "tag_create",
                    "tag_update",
                    "tag_delete",
                    "tag_import",
                ],
            ),
            MenuItem(
                name=_("自定义字段"),
                url_name="custom_field_list",
                permission="dcrm.view_customfield",
                active_patterns=[
                    "custom_field_detail",
                    "custom_field_create",
                    "custom_field_update",
                    "custom_field_delete",
                ],
            ),
            MenuItem(
                name=_("编号规则"),
                url_name="coding_rule_list",
                permission="dcrm.view_coding_rule",
                active_patterns=[
                    "coding_rule_detail",
                    "coding_rule_create",
                    "coding_rule_update",
                    "coding_rule_delete",
                    "coding_rule_import",
                ],
            ),
        ],
    )
    menu_registry.register("main", custom)

    # 报表管理
    reports = MenuItem(
        name=_("报表管理"),
        icon="fa-bar-chart",
        children=[
            MenuItem(
                name=_("设备报表"),
                url_name="device_report",
                permission="dcrm.view_device",
                active_patterns=[
                    "device_report",
                ],
            ),
            MenuItem(
                name=_("机柜报表"),
                url_name="rack_report",
                permission="dcrm.view_rack",
                active_patterns=[
                    "rack_report",
                ],
            ),
            MenuItem(
                name=_("租户报表"),
                url_name="tenant_report",
                permission="dcrm.view_tenant",
                active_patterns=[
                    "tenant_report",
                ],
            ),
        ],
    )
    menu_registry.register("system", reports)

    # 系统管理
    system = MenuItem(
        name=_("系统设置"),
        icon="fa-cogs",
        children=[
            # 用户管理
            MenuItem(
                name=_("用户管理"),
                url_name="user_list",
                permission="dcrm.view_user",
                active_patterns=[
                    "user_detail",
                    "user_create",
                    "user_update",
                    "user_delete",
                    "user_import",
                    "user_profile",
                ],
            ),
            # 用户组
            MenuItem(
                name=_("用户组"),
                url_name="group_list",
                permission="dcrm.view_group",
                active_patterns=[
                    "group_detail",
                    "group_create",
                    "group_update",
                    "group_delete",
                    "group_import",
                ],
            ),
            # 操作日志
            MenuItem(
                name=_("操作日志"),
                url_name="log_entry_list",
                permission="dcrm.view_logentry",
                active_patterns=[
                    "log_entry_detail",
                    "log_entry_delete",
                    "log_entry_import",
                ],
            ),
            # 配置管理菜单项
            MenuItem(
                name=_("配置管理"),
                url_name="configuration",
                permission="dcrm.view_datacenter",
                active_patterns=[
                    "configuration",
                ],
            ),
        ],
    )
    menu_registry.register("system", system)

    # 帮助文档
    menu_registry.register(
        "help", MenuItem(name=_("使用文档"), icon="fa-book", url="#")
    )


# 注册默认菜单
register_default_menus()
