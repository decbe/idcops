from django.urls import path

from dcrm.views import (
    api,
    auth,
    codingrule,
    customfield,
    datacenter,
    device,
    document,
    inventory,
    logentry,
    network,
    patchcord,
    qrcode,
    rack,
    reports,
    room,
    system,
    tags,
    tenant,
    topology,
    views,
)
from dcrm.views.autocomplete import get_autocomplete_urls
from dcrm.views.imports.registrations import get_import_urls

urlpatterns = [
    # 首页
    path("", views.IndexView.as_view(), name="index"),
    # 系统管理相关
    ## Welcome
    path("system/welcome/", views.WelcomeView.as_view(), name="welcome"),
    ## 数据中心
    path(
        "system/datacenters/",
        datacenter.DataCenterListView.as_view(),
        name="data_center_list",
    ),
    path(
        "system/datacenters/add/",
        datacenter.DataCenterCreateView.as_view(),
        name="data_center_create",
    ),
    path(
        "system/datacenters/<int:pk>/edit/",
        datacenter.DataCenterUpdateView.as_view(),
        name="data_center_update",
    ),
    path(
        "system/datacenters/<int:pk>/detail/",
        datacenter.DataCenterDetailView.as_view(),
        name="data_center_detail",
    ),
    path(
        "system/datacenters/<int:pk>/delete/",
        datacenter.DataCenterDeleteView.as_view(),
        name="data_center_delete",
    ),
    ## 用户管理
    path("system/users/", system.UserListView.as_view(), name="user_list"),
    path("system/users/add/", system.UserCreateView.as_view(), name="user_create"),
    path("system/users/<int:pk>/", system.UserDetailView.as_view(), name="user_detail"),
    path(
        "system/users/<int:pk>/edit/",
        system.UserUpdateView.as_view(),
        name="user_update",
    ),
    path(
        "system/users/<int:pk>/delete/",
        system.UserDeleteView.as_view(),
        name="user_delete",
    ),
    path(
        "system/users/profile/",
        system.UserProfileView.as_view(),
        name="user_profile",
    ),
    path(
        "system/users/configure/<str:model_name>/<str:view_name>/",
        system.UserCustomFieldConfigView.as_view(),
        name="user_field_config",
    ),
    ## 用户组
    path("system/groups/", system.GroupListView.as_view(), name="group_list"),
    path("system/groups/add/", system.GroupCreateView.as_view(), name="group_create"),
    path(
        "system/groups/<int:pk>/", system.GroupDetailView.as_view(), name="group_detail"
    ),
    path(
        "system/groups/<int:pk>/edit/",
        system.GroupUpdateView.as_view(),
        name="group_update",
    ),
    path(
        "system/groups/<int:pk>/delete/",
        system.GroupDeleteView.as_view(),
        name="group_delete",
    ),
    ## 操作日志
    path("system/logs/", logentry.LogEntryListView.as_view(), name="log_entry_list"),
    path(
        "system/logs/<int:pk>/",
        logentry.LogEntryDetailView.as_view(),
        name="log_entry_detail",
    ),
    ## 标签管理
    path("tags/", tags.TagListView.as_view(), name="tag_list"),
    path("tags/add/", tags.TagCreateView.as_view(), name="tag_create"),
    path("tags/<int:pk>/", tags.TagDetailView.as_view(), name="tag_detail"),
    path("tags/<int:pk>/edit/", tags.TagUpdateView.as_view(), name="tag_update"),
    path("tags/<int:pk>/delete/", tags.TagDeleteView.as_view(), name="tag_delete"),
    ## 自定义字段
    path(
        "custom-fields/",
        customfield.CustomFieldListView.as_view(),
        name="custom_field_list",
    ),
    path(
        "custom-fields/add/",
        customfield.CustomFieldCreateView.as_view(),
        name="custom_field_create",
    ),
    path(
        "custom-fields/<int:pk>/",
        customfield.CustomFieldDetailView.as_view(),
        name="custom_field_detail",
    ),
    path(
        "custom-fields/<int:pk>/edit/",
        customfield.CustomFieldUpdateView.as_view(),
        name="custom_field_update",
    ),
    path(
        "custom-fields/<int:pk>/delete/",
        customfield.CustomFieldDeleteView.as_view(),
        name="custom_field_delete",
    ),
    ## 编码规则
    path(
        "coding-rules/",
        codingrule.CodingRuleListView.as_view(),
        name="coding_rule_list",
    ),
    path(
        "coding-rules/add/",
        codingrule.CodingRuleCreateView.as_view(),
        name="coding_rule_create",
    ),
    path(
        "coding-rules/<int:pk>/",
        codingrule.CodingRuleDetailView.as_view(),
        name="coding_rule_detail",
    ),
    path(
        "coding-rules/<int:pk>/edit/",
        codingrule.CodingRuleUpdateView.as_view(),
        name="coding_rule_update",
    ),
    path(
        "coding-rules/<int:pk>/delete/",
        codingrule.CodingRuleDeleteView.as_view(),
        name="coding_rule_delete",
    ),
    # 租户相关
    ## 租户管理
    path("tenants/", tenant.TenantListView.as_view(), name="tenant_list"),
    path("tenants/add/", tenant.TenantCreateView.as_view(), name="tenant_create"),
    path("tenants/<int:pk>/", tenant.TenantDetailView.as_view(), name="tenant_detail"),
    path(
        "tenants/<int:pk>/edit/",
        tenant.TenantUpdateView.as_view(),
        name="tenant_update",
    ),
    path(
        "tenants/<int:pk>/delete/",
        tenant.TenantDeleteView.as_view(),
        name="tenant_delete",
    ),
    ## 联系人
    path("contacts/", tenant.ContactListView.as_view(), name="contact_list"),
    path("contacts/add/", tenant.ContactCreateView.as_view(), name="contact_create"),
    path(
        "contacts/<int:pk>/", tenant.ContactDetailView.as_view(), name="contact_detail"
    ),
    path(
        "contacts/<int:pk>/edit/",
        tenant.ContactUpdateView.as_view(),
        name="contact_update",
    ),
    path(
        "contacts/<int:pk>/delete/",
        tenant.ContactDeleteView.as_view(),
        name="contact_delete",
    ),
    ## 联系人角色
    path(
        "contact-roles/",
        tenant.ContactRoleListView.as_view(),
        name="contact_role_list",
    ),
    path(
        "contact-roles/add/",
        tenant.ContactRoleCreateView.as_view(),
        name="contact_role_create",
    ),
    path(
        "contact-roles/<int:pk>/",
        tenant.ContactRoleDetailView.as_view(),
        name="contact_role_detail",
    ),
    path(
        "contact-roles/<int:pk>/edit/",
        tenant.ContactRoleUpdateView.as_view(),
        name="contact_role_update",
    ),
    path(
        "contact-roles/<int:pk>/delete/",
        tenant.ContactRoleDeleteView.as_view(),
        name="contact_role_delete",
    ),
    ## 制造商
    path(
        "manufacturers/",
        tenant.ManufacturerListView.as_view(),
        name="manufacturer_list",
    ),
    path(
        "manufacturers/add/",
        tenant.ManufacturerCreateView.as_view(),
        name="manufacturer_create",
    ),
    path(
        "manufacturers/<int:pk>/",
        tenant.ManufacturerDetailView.as_view(),
        name="manufacturer_detail",
    ),
    path(
        "manufacturers/<int:pk>/edit/",
        tenant.ManufacturerUpdateView.as_view(),
        name="manufacturer_update",
    ),
    path(
        "manufacturers/<int:pk>/delete/",
        tenant.ManufacturerDeleteView.as_view(),
        name="manufacturer_delete",
    ),
    # 数据中心基础设施
    ## 机房管理
    path("rooms/", room.RoomListView.as_view(), name="room_list"),
    path("rooms/add/", room.RoomCreateView.as_view(), name="room_create"),
    path("rooms/<int:pk>/", room.RoomDetailView.as_view(), name="room_detail"),
    path("rooms/<int:pk>/edit/", room.RoomUpdateView.as_view(), name="room_update"),
    path("rooms/<int:pk>/delete/", room.RoomDeleteView.as_view(), name="room_delete"),
    ### 机房房间平面图
    path("rooms/maps/", room.RoomRackMapsView.as_view(), name="room_rack_maps"),
    # 机柜管理
    path("racks/", rack.RackListView.as_view(), name="rack_list"),
    path("racks/add/", rack.RackCreateView.as_view(), name="rack_create"),
    path("racks/<int:pk>/", rack.RackDetailView.as_view(), name="rack_detail"),
    path("racks/<int:pk>/edit/", rack.RackUpdateView.as_view(), name="rack_update"),
    path("racks/<int:pk>/delete/", rack.RackDeleteView.as_view(), name="rack_delete"),
    path(
        "racks/<int:pk>/topology/",
        topology.RackTopologyView.as_view(),
        name="rack_topology",
    ),
    ## 机柜状态
    path("racks/status/", rack.RackStatusListView.as_view(), name="rack_status_list"),
    path(
        "racks/status/add/",
        rack.RackStatusCreateView.as_view(),
        name="rack_status_create",
    ),
    path(
        "racks/status/<int:pk>/",
        rack.RackStatusDetailView.as_view(),
        name="rack_status_detail",
    ),
    path(
        "racks/status/<int:pk>/edit/",
        rack.RackStatusUpdateView.as_view(),
        name="rack_status_update",
    ),
    path(
        "racks/status/<int:pk>/delete/",
        rack.RackStatusDeleteView.as_view(),
        name="rack_status_delete",
    ),
    ## 机柜PDU
    path("racks/pdus/", rack.RackPDUListView.as_view(), name="rack_pdu_list"),
    path("racks/pdus/add/", rack.RackPDUCreateView.as_view(), name="rack_pdu_create"),
    path(
        "racks/pdus/<int:pk>/", rack.RackPDUDetailView.as_view(), name="rack_pdu_detail"
    ),
    path(
        "racks/pdus/<int:pk>/edit/",
        rack.RackPDUUpdateView.as_view(),
        name="rack_pdu_update",
    ),
    path(
        "racks/pdus/<int:pk>/delete/",
        rack.RackPDUDeleteView.as_view(),
        name="rack_pdu_delete",
    ),
    # 设备管理相关
    ## 设备
    path("devices/", device.DeviceListView.as_view(), name="device_list"),
    path("devices/add/", device.DeviceCreateView.as_view(), name="device_create"),
    path("devices/<int:pk>/", device.DeviceDetailView.as_view(), name="device_detail"),
    path(
        "devices/<int:pk>/edit/",
        device.DeviceUpdateView.as_view(),
        name="device_update",
    ),
    path(
        "devices/<int:pk>/delete/",
        device.DeviceDeleteView.as_view(),
        name="device_delete",
    ),
    path(
        "devices/<int:pk>/topology/",
        topology.DeviceTopologyView.as_view(),
        name="device_topology",
    ),
    ## 在线设备
    path(
        "devices/online/",
        device.OnlineDeviceListView.as_view(),
        name="online_device_list",
    ),
    path(
        "devices/online/add/",
        device.OnlineDeviceCreateView.as_view(),
        name="online_device_create",
    ),
    path(
        "devices/online/<int:pk>/",
        device.OnlineDeviceDetailView.as_view(),
        name="online_device_detail",
    ),
    path(
        "devices/online/<int:pk>/edit/",
        device.OnlineDeviceUpdateView.as_view(),
        name="online_device_update",
    ),
    path(
        "devices/online/<int:pk>/delete/",
        device.OnlineDeviceDeleteView.as_view(),
        name="online_device_delete",
    ),
    path(
        "devices/online/bulk-create/",
        device.OnlineDeviceBulkCreateView.as_view(),
        name="online_device_bulk_create",
    ),
    ## 设备类型
    path(
        "devices/types/",
        device.DeviceTypeListView.as_view(),
        name="device_type_list",
    ),
    path(
        "devices/types/add/",
        device.DeviceTypeCreateView.as_view(),
        name="device_type_create",
    ),
    path(
        "devices/types/<int:pk>/",
        device.DeviceTypeDetailView.as_view(),
        name="device_type_detail",
    ),
    path(
        "devices/types/<int:pk>/edit/",
        device.DeviceTypeUpdateView.as_view(),
        name="device_type_update",
    ),
    path(
        "devices/types/<int:pk>/delete/",
        device.DeviceTypeDeleteView.as_view(),
        name="device_type_delete",
    ),
    ## 设备型号
    path(
        "devices/models/",
        device.DeviceModelListView.as_view(),
        name="device_model_list",
    ),
    path(
        "devices/models/add/",
        device.DeviceModelCreateView.as_view(),
        name="device_model_create",
    ),
    path(
        "devices/models/<int:pk>/",
        device.DeviceModelDetailView.as_view(),
        name="device_model_detail",
    ),
    path(
        "devices/models/<int:pk>/edit/",
        device.DeviceModelUpdateView.as_view(),
        name="device_model_update",
    ),
    path(
        "devices/models/<int:pk>/delete/",
        device.DeviceModelDeleteView.as_view(),
        name="device_model_delete",
    ),
    ## 设备端口
    path(
        "devices/ports/", device.DevicePortListView.as_view(), name="device_port_list"
    ),
    path(
        "devices/ports/add/",
        device.DevicePortCreateView.as_view(),
        name="device_port_create",
    ),
    path(
        "devices/ports/<int:pk>/",
        device.DevicePortDetailView.as_view(),
        name="device_port_detail",
    ),
    path(
        "devices/ports/<int:pk>/edit/",
        device.DevicePortUpdateView.as_view(),
        name="device_port_update",
    ),
    path(
        "devices/ports/<int:pk>/delete/",
        device.DevicePortDeleteView.as_view(),
        name="device_port_delete",
    ),
    ## 设备主机
    path(
        "devices/hosts/", device.DeviceHostListView.as_view(), name="device_host_list"
    ),
    path(
        "devices/hosts/add/",
        device.DeviceHostCreateView.as_view(),
        name="device_host_create",
    ),
    path(
        "devices/hosts/<int:pk>/",
        device.DeviceHostDetailView.as_view(),
        name="device_host_detail",
    ),
    path(
        "devices/hosts/<int:pk>/edit/",
        device.DeviceHostUpdateView.as_view(),
        name="device_host_update",
    ),
    path(
        "devices/hosts/<int:pk>/delete/",
        device.DeviceHostDeleteView.as_view(),
        name="device_host_delete",
    ),
    # 网络管理相关
    ## 子网管理
    path("networks/subnet/", network.SubnetListView.as_view(), name="subnet_list"),
    path(
        "networks/subnet/add/", network.SubnetCreateView.as_view(), name="subnet_create"
    ),
    path(
        "networks/subnet/<int:pk>/",
        network.SubnetDetailView.as_view(),
        name="subnet_detail",
    ),
    path(
        "networks/subnet/<int:pk>/sse/",
        network.ServerSentEventView.as_view(),
        name="subnet_sse",
    ),
    path(
        "networks/subnet/<int:pk>/edit/",
        network.SubnetUpdateView.as_view(),
        name="subnet_update",
    ),
    path(
        "networks/subnet/<int:pk>/delete/",
        network.SubnetDeleteView.as_view(),
        name="subnet_delete",
    ),
    # path('networks/subnet/bulk-import/', network.SubnetBulkImportView.as_view(), name='subnet_bulk_import'),
    ## IP管理
    path(
        "networks/ipaddress/",
        network.IPAddressListView.as_view(),
        name="ip_address_list",
    ),
    path(
        "networks/ipaddress/add/",
        network.IPAddressCreateView.as_view(),
        name="ip_address_create",
    ),
    path(
        "networks/ipaddress/<int:pk>/",
        network.IPAddressDetailView.as_view(),
        name="ip_address_detail",
    ),
    path(
        "networks/ipaddress/<int:pk>/edit/",
        network.IPAddressUpdateView.as_view(),
        name="ip_address_update",
    ),
    path(
        "networks/ipaddress/<int:pk>/delete/",
        network.IPAddressDeleteView.as_view(),
        name="ip_address_delete",
    ),
    ## VLAN管理
    path("networks/vlans/", network.VLANListView.as_view(), name="vlan_list"),
    path("networks/vlans/add/", network.VLANCreateView.as_view(), name="vlan_create"),
    path(
        "networks/vlans/<int:pk>/", network.VLANDetailView.as_view(), name="vlan_detail"
    ),
    path(
        "networks/vlans/<int:pk>/edit/",
        network.VLANUpdateView.as_view(),
        name="vlan_update",
    ),
    path(
        "networks/vlans/<int:pk>/delete/",
        network.VLANDeleteView.as_view(),
        name="vlan_delete",
    ),
    ## 代理管理
    path("networks/proxies/", network.ProxyListView.as_view(), name="proxy_list"),
    path(
        "networks/proxies/add/", network.ProxyCreateView.as_view(), name="proxy_create"
    ),
    path(
        "networks/proxies/<int:pk>/",
        network.ProxyDetailView.as_view(),
        name="proxy_detail",
    ),
    path(
        "networks/proxies/<int:pk>/edit/",
        network.ProxyUpdateView.as_view(),
        name="proxy_update",
    ),
    path(
        "networks/proxies/<int:pk>/delete/",
        network.ProxyDeleteView.as_view(),
        name="proxy_delete",
    ),
    ## 网络产品
    path(
        "networks/products/",
        network.NetworkProductListView.as_view(),
        name="network_product_list",
    ),
    path(
        "networks/products/add/",
        network.NetworkProductCreateView.as_view(),
        name="network_product_create",
    ),
    path(
        "networks/products/<int:pk>/",
        network.NetworkProductDetailView.as_view(),
        name="network_product_detail",
    ),
    path(
        "networks/products/<int:pk>/edit/",
        network.NetworkProductUpdateView.as_view(),
        name="network_product_update",
    ),
    path(
        "networks/products/<int:pk>/delete/",
        network.NetworkProductDeleteView.as_view(),
        name="network_product_delete",
    ),
    # 跳线管理相关
    ## 跳线
    path("patch-cords/", patchcord.PatchCordListView.as_view(), name="patch_cord_list"),
    path(
        "patch-cords/add/",
        patchcord.PatchCordCreateView.as_view(),
        name="patch_cord_create",
    ),
    path(
        "patch-cords/<int:pk>/",
        patchcord.PatchCordDetailView.as_view(),
        name="patch_cord_detail",
    ),
    path(
        "patch-cords/<int:pk>/edit/",
        patchcord.PatchCordUpdateView.as_view(),
        name="patch_cord_update",
    ),
    path(
        "patch-cords/<int:pk>/delete/",
        patchcord.PatchCordDeleteView.as_view(),
        name="patch_cord_delete",
    ),
    ## 跳线节点
    path(
        "patch-cords/nodes/",
        patchcord.PatchCordNodeListView.as_view(),
        name="patch_cord_node_list",
    ),
    path(
        "patch-cords/nodes/add/",
        patchcord.PatchCordNodeCreateView.as_view(),
        name="patch_cord_node_create",
    ),
    path(
        "patch-cords/nodes/<int:pk>/",
        patchcord.PatchCordNodeDetailView.as_view(),
        name="patch_cord_node_detail",
    ),
    path(
        "patch-cords/nodes/<int:pk>/edit/",
        patchcord.PatchCordNodeUpdateView.as_view(),
        name="patch_cord_node_update",
    ),
    path(
        "patch-cords/nodes/<int:pk>/delete/",
        patchcord.PatchCordNodeDeleteView.as_view(),
        name="patch_cord_node_delete",
    ),
    # 库存管理相关
    ## 仓库
    path(
        "inventory/warehouses/",
        inventory.WarehouseListView.as_view(),
        name="warehouse_list",
    ),
    path(
        "inventory/warehouses/add/",
        inventory.WarehouseCreateView.as_view(),
        name="warehouse_create",
    ),
    path(
        "inventory/warehouses/<int:pk>/",
        inventory.WarehouseDetailView.as_view(),
        name="warehouse_detail",
    ),
    path(
        "inventory/warehouses/<int:pk>/edit/",
        inventory.WarehouseUpdateView.as_view(),
        name="warehouse_update",
    ),
    path(
        "inventory/warehouses/<int:pk>/delete/",
        inventory.WarehouseDeleteView.as_view(),
        name="warehouse_delete",
    ),
    ## 物品类别
    path(
        "inventory/item-categories/",
        inventory.ItemCategoryListView.as_view(),
        name="item_category_list",
    ),
    path(
        "inventory/item-categories/add/",
        inventory.ItemCategoryCreateView.as_view(),
        name="item_category_create",
    ),
    path(
        "inventory/item-categories/<int:pk>/",
        inventory.ItemCategoryDetailView.as_view(),
        name="item_category_detail",
    ),
    path(
        "inventory/item-categories/<int:pk>/edit/",
        inventory.ItemCategoryUpdateView.as_view(),
        name="item_category_update",
    ),
    path(
        "inventory/item-categories/<int:pk>/delete/",
        inventory.ItemCategoryDeleteView.as_view(),
        name="item_category_delete",
    ),
    ## 物品实例
    path(
        "inventory/items/instances/",
        inventory.ItemInstanceListView.as_view(),
        name="item_instance_list",
    ),
    path(
        "inventory/items/instances/add/",
        inventory.ItemInstanceCreateView.as_view(),
        name="item_instance_create",
    ),
    path(
        "inventory/items/instances/<int:pk>/",
        inventory.ItemInstanceDetailView.as_view(),
        name="item_instance_detail",
    ),
    path(
        "inventory/items/instances/<int:pk>/edit/",
        inventory.ItemInstanceUpdateView.as_view(),
        name="item_instance_update",
    ),
    path(
        "inventory/items/instances/<int:pk>/delete/",
        inventory.ItemInstanceDeleteView.as_view(),
        name="item_instance_delete",
    ),
    path(
        "inventory/items/instances/add/bulk/",
        inventory.BulkItemInstanceCreateView.as_view(),
        # name="item_instance_bulk_create",
        name="item_instance_create",
    ),
    ## 物品实例历史
    path(
        "inventory/items/instances/history/",
        inventory.ItemInstanceHistoryListView.as_view(),
        name="item_instance_history_list",
    ),
    path(
        "inventory/items/instances/history/add/",
        inventory.ItemInstanceHistoryCreateView.as_view(),
        name="item_instance_history_create",
    ),
    path(
        "inventory/items/instances/history/<int:pk>/",
        inventory.ItemInstanceHistoryDetailView.as_view(),
        name="item_instance_history_detail",
    ),
    path(
        "inventory/items/instances/history/<int:pk>/edit/",
        inventory.ItemInstanceHistoryUpdateView.as_view(),
        name="item_instance_history_update",
    ),
    path(
        "inventory/items/instances/history/<int:pk>/delete/",
        inventory.ItemInstanceHistoryDeleteView.as_view(),
        name="item_instance_history_delete",
    ),
    ## 物品
    path(
        "inventory/items/",
        inventory.InventoryItemListView.as_view(),
        name="inventory_item_list",
    ),
    path(
        "inventory/items/add/",
        inventory.InventoryItemCreateView.as_view(),
        name="inventory_item_create",
    ),
    path(
        "inventory/items/<int:pk>/",
        inventory.InventoryItemDetailView.as_view(),
        name="inventory_item_detail",
    ),
    path(
        "inventory/items/<int:pk>/edit/",
        inventory.InventoryItemUpdateView.as_view(),
        name="inventory_item_update",
    ),
    path(
        "inventory/items/<int:pk>/delete/",
        inventory.InventoryItemDeleteView.as_view(),
        name="inventory_item_delete",
    ),
    # 配置管理
    path("configuration/", system.ConfigurationView.as_view(), name="configuration"),
    # 认证相关
    path(
        "accounts/create-first-superuser/",
        views.CreateFirstSuperUserView.as_view(),
        name="create_first_superuser",
    ),
    path("accounts/login/", auth.CustomLoginView.as_view(), name="login"),
    path("accounts/logout/", auth.CustomLogoutView.as_view(), name="logout"),
    path(
        "accounts/password/change/",
        auth.CustomPasswordChangeView.as_view(),
        name="password_change",
    ),
    path(
        "accounts/password/reset/",
        auth.CustomPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "accounts/password/reset/<uidb64>/<token>/",
        auth.CustomPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path("documents/", document.DocumentListView.as_view(), name="document_list"),
    path(
        "documents/add/",
        document.DocumentCreateView.as_view(),
        name="document_create",
    ),
    path(
        "documents/convert-upload/",
        document.DocumentConvertUploadView.as_view(),
        name="document_convert_upload",
    ),
    path(
        "documents/<int:pk>/",
        document.DocumentDetailView.as_view(),
        name="document_detail",
    ),
    path(
        "documents/<int:pk>/edit/",
        document.DocumentUpdateView.as_view(),
        name="document_update",
    ),
    path(
        "documents/<int:pk>/delete/",
        document.DocumentDeleteView.as_view(),
        name="document_delete",
    ),
    path(
        "documents/categories/",
        document.CategoryListView.as_view(),
        name="category_list",
    ),
    path(
        "documents/categories/add/",
        document.CategoryCreateView.as_view(),
        name="category_create",
    ),
    path(
        "documents/categories/<int:pk>/",
        document.CategoryDetailView.as_view(),
        name="category_detail",
    ),
    path(
        "documents/categories/<int:pk>/edit/",
        document.CategoryUpdateView.as_view(),
        name="category_update",
    ),
    path(
        "documents/categories/<int:pk>/delete/",
        document.CategoryDeleteView.as_view(),
        name="category_delete",
    ),
    # API相关
    path("api/", api.ninja_api.urls),
    # 文件上传
    path("attachement-upload/", views.UploadAttachment.as_view(), name="upload"),
    # 报表功能
    path("reports/devices/", reports.DeviceReportView.as_view(), name="device_report"),
    path(
        "reports/devices/data/",
        reports.DeviceReportDataView.as_view(),
        name="device_report_data",
    ),
    path("reports/racks/", reports.RackReportView.as_view(), name="rack_report"),
    path(
        "reports/racks/data/",
        reports.RackReportDataView.as_view(),
        name="rack_report_data",
    ),
    path("reports/tenants/", reports.TenantReportView.as_view(), name="tenant_report"),
    path(
        "reports/tenants/data/",
        reports.TenantReportDataView.as_view(),
        name="tenant_report_data",
    ),
    # 导入功能
    *get_import_urls(),
    # Autocomplete 功能
    *get_autocomplete_urls(),
    # 二维码功能
    path(
        "scan/<str:token>/",
        qrcode.QRPublicDetailView.as_view(),
        name="qr_public_detail",
    ),
    path("qr/image/<str:token>/", qrcode.QRImageView.as_view(), name="qr_image"),
    path(
        "qr/download/<str:token>/",
        qrcode.QRImageDownloadView.as_view(),
        name="qr_download",
    ),
]
