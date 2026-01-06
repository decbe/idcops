import hashlib
import logging
import os
import re
import uuid
from ipaddress import IPv4Interface, IPv6Interface, ip_interface
from typing import Any

from django.db import models
from django.db.models import Q
from django.utils import timezone
from magic import Magic

logger = logging.getLogger(__name__)


def upload_to(instance: Any, filename: str) -> str:
    if ext := filename.split(".")[-1]:
        filename = f"{uuid.uuid4()}.{ext}"
    today = timezone.datetime.now().strftime(r"%Y/%m/%d")
    return os.path.join("uploads", today, filename)


def get_file_mime(filepath, buffer=False):
    # 检测文件类型
    m = Magic(mime=True)
    if buffer:
        filetype = m.from_buffer(filepath)
    else:
        filetype = m.from_file(filepath)
    return filetype if filetype else "unknown"


def md5sum_file(filepath, buffer=False):
    m = hashlib.md5()
    if buffer:
        m.update(filepath)
    else:
        with open(filepath, "rb") as fp:
            while True:
                data = fp.read(4096)
                if not data:
                    break
                m.update(data)
    return m.hexdigest()


def tag_limit_filter(app_label: str, model: str) -> models.Q:
    """获取标签选择器选项
    """
    q = Q(object_types__app_label=app_label, object_types__model=model)
    return q


def get_network_info(ip_interface_str: str) -> dict:
    """获取接口地址的网络信息

    Args:
        ip_interface_str: 接口地址字符串，如 '192.168.1.1/24' 或 '2001:db8::1/64'

    Returns:
        包含网络信息的字典

    """
    iface = ip_interface(ip_interface_str)
    network = iface.network

    info = {
        "interface": str(iface),  # 接口地址
        "ip": str(iface.ip),  # IP地址
        "network": str(network.network_address),  # 网络地址
        "netmask": str(network.netmask),  # 子网掩码
        "prefixlen": network.prefixlen,  # 前缀长度
        "num_addresses": network.num_addresses,  # 可用地址数
        "is_private": iface.ip.is_private,  # 是否私有地址
    }

    # IPv4 和 IPv6 的处理略有不同
    if isinstance(iface, IPv4Interface):
        info.update(
            {
                "broadcast": str(network.broadcast_address),  # 广播地址(仅IPv4)
                "first_host": str(network.network_address + 1),  # 第一个可用主机地址
                "last_host": str(network.broadcast_address - 1),  # 最后一个可用主机地址
            }
        )
    elif isinstance(iface, IPv6Interface):
        info.update(
            {
                "broadcast": None,  # IPv6没有广播地址概念
                "first_host": str(network.network_address + 1),
                "last_host": str(network.network_address + network.num_addresses - 1),
            }
        )

    return info


def sort_items(items, sort_field="name", reverse=True, key_func=None):
    """根据指定字段对列表中的字典进行排序

    :param items: 待排序的列表（字典组成的列表）
    :param sort_field: 排序字段名（默认按'name'排序）
    :param reverse: 是否降序排列（默认升序）
    :param key_func: 自定义键函数（可选）
    :return: 排序后的新列表

    Usage:
    # 调用示例
    sorted_by_name_length = sort_items(data, reverse=True)  # 按'name'长度降序
    sorted_by_id = sort_items(data, sort_field='id')          # 按'id'升序
    sorted_by_custom_key = sort_items(data, key_func=lambda x: x['id'])  # 自定义键函数
    """
    # 处理字段不存在的情况
    if sort_field is not None and key_func is None:
        try:
            key_func = lambda x: len(x[sort_field])  # noqa: E731
        except KeyError:
            raise ValueError(f"字段 '{sort_field}' 不存在于数据中")
    elif key_func is None:
        key_func = lambda x: len(x.get(sort_field, ""))  # noqa: E731

    # 执行排序（稳定排序）
    return sorted(items, key=key_func, reverse=reverse)


def recursive_sort(items, sort_field="name", reverse=True):
    sorted_items = sort_items(items, sort_field, reverse)

    for item in sorted_items:
        if isinstance(item.get("children"), list):
            item["children"] = recursive_sort(item["children"], sort_field, reverse)
    return sorted_items


def auto_group_racks(racks, key):
    """自动识别机柜编号的命名模式并分组
    能处理多种不同格式的机柜编号

    参数:
        racks: 机柜编号列表

    返回:
        dict: 以识别出的分组为键，对应机柜列表为值的字典
    """
    # 尝试不同的模式匹配
    patterns = [
        r"(.*)-([A-Z])(\d+)",  # 如 3F01-A01
        r"(.*)-(\d+)",  # 如 Room1-01
        r"(.*)(\d+)$",  # 如 Rack01
    ]

    # 尝试每种模式，选择匹配率最高的
    best_pattern = None
    best_match_count = 0

    for pattern in patterns:
        match_count = sum(1 for rack in racks if re.match(pattern, rack[key]))
        if match_count > best_match_count:
            best_pattern = pattern
            best_match_count = match_count

    if not best_pattern or best_match_count < len(racks) * 0.5:  # 至少50%匹配
        # 如果没有找到合适的模式，按原样返回
        return {"default": racks}

    # 根据最佳模式分组
    groups = {}

    if best_pattern == r"(.*)-([A-Z])(\d+)":
        # 按前缀和字母分组
        for rack in racks:
            match = re.match(best_pattern, rack[key])
            if not match:
                continue

            prefix, letter, number = match.groups()
            group_key = f"{prefix}-{letter}"

            if group_key not in groups:
                groups[group_key] = []

            groups[group_key].append(rack)

    elif best_pattern in [r"(.*)-(\d+)", r"(.*)(\d+)$"]:
        # 按前缀分组
        for rack in racks:
            match = re.match(best_pattern, rack[key])
            if not match:
                continue

            prefix = match.group(1)

            if prefix not in groups:
                groups[prefix] = []

            groups[prefix].append(rack)

    # 对各组内机柜排序
    # TODO: 如果需要，可以在这里添加组内排序逻辑

    return groups
