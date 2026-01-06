from django import template

register = template.Library()


@register.filter
def sub(value, arg):
    """减法过滤器"""
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return value


@register.filter
def mul(value, arg):
    """乘法过滤器"""
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return value


@register.filter
def range_filter(value):
    """生成指定长度的序列，从1开始"""
    try:
        return range(1, int(value) + 1)
    except (ValueError, TypeError):
        return range(1)


@register.filter
def get_device_at_position(devices, position):
    """获取指定位置的设备"""
    for device in devices:
        if device["position"] == position:
            return device
    return None


@register.filter
def is_position_in_device_span(devices, position):
    """检查位置是否在任何设备的跨度内"""
    for device in devices:
        if device["position"] < position < device["position"] + device["height"]:
            return True
    return False


@register.filter
def get_item(dictionary, key):
    """获取字典中的值"""
    return dictionary.get(key)


@register.filter
def zfill(value, length=2):
    """格式化数字，在左侧补0

    用法：
    {{ value|zfill:2 }}  # 补齐2位，如：01, 02, 03
    """
    return str(value).zfill(length)


@register.filter
def rack_elevation(rack, active_device=None):
    """渲染机柜立面图
    采用 adminlte 2.4 的风格
    使用 table, tr, td 渲染机柜立面图

    Args:
        rack: 机柜对象
        active_device: 当前激活的设备，将会添加bg-success样式

    Returns:
        str: 包含机柜立面图的HTML表格

    """
    html = []
    # 添加表格头部
    html.append('<div class="table-responsive">')
    html.append('<table class="table table-bordered table-condensed">')
    html.append("<tbody>")

    # 跳过的行数（用于设备跨行显示）
    skip_rows = 0

    # 遍历机柜U位和设备
    for u, device, is_start in rack.unit_devices:
        # 如果需要跳过当前行（因为上一个设备占用了多个U位）
        if skip_rows > 0:
            skip_rows -= 1
            continue

        # 开始新的行
        html.append("<tr>")
        # U位编号单元格
        html.append(
            f'<td class="text-center" style="width:4em;background-color:#f9f9f9">U{u}</td>'
        )

        if device and is_start:
            # 设备起始位置，需要合并单元格
            device_height = device.model.height
            skip_rows = device_height - 1

            # 设置设备单元格的样式
            css_class = []
            if device == active_device:
                css_class.append("bg-success")  # 当前激活的设备使用绿色背景

            # 设备信息单元格
            html.append(
                f'<td rowspan="{device_height}" class="{" ".join(css_class)}">'
                f'<div class="text-center">{device.name}</div>'
                f'<small class="text-muted">{device.model}</small>'
                f"</td>"
            )
        elif not device:
            # 空闲U位
            html.append('<td class="text-center text-muted">空闲</td>')

        html.append("</tr>")

    # 添加表格尾部
    html.append("</tbody>")
    html.append("</table>")
    html.append("</div>")

    return "\n".join(html)


# 改用 inclusion_tag 的标签直接渲染 html模板
@register.inclusion_tag("rack/rack_elevation_table.html", takes_context=True)
def render_rack_elevation(context, rack, active_device=None, edit_device=False):
    """渲染机柜立面图，采用三列布局显示

    布局说明：
    - 左侧U位编号列：固定宽度，显示从上到下的U位编号
    - 中间设备列：显示设备信息，支持根据设备高度合并单元格
    - 右侧U位编号列：固定宽度，显示从上到下的U位编号

    参数说明：
        rack: 机柜对象
        active_device: 当前激活的设备，会被添加bg-success样式

    使用方式：
    {% load rack_tags %}
    {% render_rack_elevation rack active_device %}
    """
    # 将生成器转换为列表，以便模板可以多次遍历

    data = {
        "rack_units": list(rack.unit_devices),
        "rack": rack,
        "space_usage": rack.get_space_usage(),
        "active_device": active_device,
        "edit_device": edit_device,
        "request": context["request"],  # 传递 request 对象到模板
    }
    if active_device and edit_device:
        extra = {
            "can_drop_units": rack.get_available_units(
                active_device.height, exclude_id=active_device.id
            ),
            "active_device": active_device,
        }
    else:
        extra = {"can_drop_units": rack.get_available_units()}
    data.update(extra)
    return data


@register.inclusion_tag("device/ports_table.html", takes_context=True)
def render_device_ports(context, device): ...
