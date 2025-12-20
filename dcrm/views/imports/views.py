import csv
import io
import logging
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth import get_permission_codename
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.fields import NOT_PROVIDED
from django.forms import ValidationError
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.text import get_text_list
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from dcrm.constants import FIELD_TYPE_MAP
from dcrm.forms.imports import BaseImportForm
from dcrm.utilities.base import camel_to_snake
from dcrm.views.mixins.base import BaseRequestMixin

logger = logging.getLogger(__name__)


class BulkImportView(PermissionRequiredMixin, BaseRequestMixin, FormView):
    template_name = "generic/bulk_import.html"
    form_class = BaseImportForm
    exclude_fields = [
        "id",
        "updated_at",
        "password",
        "data_center",
        "datacenter_group",
        "lft",
        "rght",
        "tree_id",
        "level",
        "custom_field_data",
        "updated_by",
    ]
    model = None
    return_url = None

    def get_permission_required(self):
        code_name = get_permission_codename("add", self.opts)
        self.permission_required = f"{self.opts.app_label}.{code_name}"
        return super().get_permission_required()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["model"] = self.model
        kwargs["request"] = self.request
        logger.info("DEBUG: 视图 - 表单初始化参数:", kwargs)
        return kwargs

    def get_field_type_display(self, field):
        """获取字段类型的显示名称"""
        field_type_mapping = FIELD_TYPE_MAP

        field_type = field.get_internal_type()
        if isinstance(field, (models.ForeignKey, models.OneToOneField)):
            field_type = "ForeignKey"
        elif isinstance(field, models.ManyToManyField):
            field_type = "ManyToManyField"

        return field_type_mapping.get(field_type, field_type)

    def get_field_default(self, field):
        """获取字段的默认值，包含特殊情况处理"""
        default = getattr(field, "default", NOT_PROVIDED)
        # 特殊字段的默认值处理
        if field.name == "created_at":
            return timezone.now()
        elif field.name == "data_center":
            return self.request.user.data_center
        elif field.name == "created_by":
            return self.request.user

        if isinstance(field, models.BooleanField):
            return str(field.default).lower()

        if default is NOT_PROVIDED:
            return ""

        # 处理可调用的默认值
        if callable(default):
            try:
                return default()
            except Exception:
                logger.error(f"处理默认值失败: {field} {field.name}")
                return ""

        return default

    def get_field_guide(self):
        """生成字段指南信息"""
        fields = []
        # 获取所有字段，包括多对多字段
        all_fields = list(self.model._meta.fields) + list(self.model._meta.many_to_many)

        # 获取导入表单中定义的帮助文本
        form = self.form_class(model=self.model, request=self.request)
        form_help_texts = {}
        for field_name, field in form.fields.items():
            if field.help_text:
                form_help_texts[field_name] = field.help_text

        for field in all_fields:
            if field.name in self.exclude_fields:
                continue

            if not field.editable:
                continue
            # 跳过ImageField, FileField
            if isinstance(field, (models.ImageField, models.FileField)):
                continue
            field_info = {
                "name": field.name,
                "label": field.verbose_name,
                "default": self.get_field_default(field),  # 使用新的方法获取默认值
                "type": self.get_field_type_display(field),
                "required": not field.blank and not field.null,
                "help_text": field.help_text,  # 初始化 help_text
                "is_text": field.get_internal_type() in ["TextField", "JSONField"],
                "is_m2m": isinstance(field, models.ManyToManyField),
            }

            # 如果导入表单中没有定义帮助文本，则使用其他规则
            if isinstance(field, (models.ForeignKey, models.ManyToManyField)):
                related_model = field.remote_field.model
                search_fields = getattr(
                    related_model,
                    "search_fields",
                    [
                        "name",
                    ],
                )
                example_values = []
                for search_field in search_fields:
                    # 获取一个示例对象
                    query = models.Q()
                    if hasattr(related_model, "data_center"):
                        query = models.Q(data_center=self.request.user.data_center)
                    example_obj = related_model.objects.filter(query).first()
                    if example_obj:
                        example_values.append(
                            f"{getattr(example_obj, search_field, '')}"
                        )
                    else:
                        example_values.append(f"[{search_field}]")

                field_info["help_text"] = _(
                    "输入 {model} 的 {fields} 字段值{m2m_hint}，例如：{examples}"
                ).format(
                    model=related_model._meta.verbose_name,
                    fields=get_text_list(search_fields),
                    m2m_hint=(
                        "（多个值用分号;分隔）"
                        if isinstance(field, models.ManyToManyField)
                        else ""
                    ),
                    examples=get_text_list(example_values),
                )

                field_info.update(
                    {
                        "related_model": related_model._meta.verbose_name,
                        "search_fields": search_fields,
                    }
                )

            # 处理选择字段
            elif hasattr(field, "choices") and field.choices:
                field_info["choices"] = [
                    {
                        "value": choice[0],
                        "label": str(choice[1]),
                    }
                    for choice in field.choices
                ]
                field_info["type"] = _("选项")
                field_info["help_text"] = str(field.help_text)

            # 处理其他字段的帮助文本
            else:
                # 使用字段的 help_text，如果没有则使用 verbose_name
                base_help = str(field.help_text or field.verbose_name)

                # 根据字段类型添加额外说明
                type_hints = {
                    "IntegerField": "请输入整数",
                    "FloatField": "请输入数字",
                    "DecimalField": "请输入数字",
                    "DateTimeField": "请输入日期时间，格式：YYYY-MM-DD HH:MM:SS",
                    "DateField": "请输入日期，格式：YYYY-MM-DD",
                    "TimeField": "请输入时间，格式：HH:MM:SS",
                    "BooleanField": "请输入 true 或 false",
                    "TextField": "可输入多行文本",
                    "JSONField": "请输入有效的 JSON 格式数据",
                }

                field_type = field.get_internal_type()
                type_hint = type_hints.get(field_type, "")

                if type_hint:
                    field_info["help_text"] = f"{base_help}（{type_hint}）"
                else:
                    field_info["help_text"] = base_help

            # 最后覆盖使用导入表单中定义的帮助文本
            if field.name in form_help_texts:
                field_info["help_text"] = form_help_texts[field.name]
            if field.name in ["created_at", "data_center", "created_by"]:
                field_info["required"] = False

            fields.append(field_info)
        # 排序字段
        fields.sort(
            key=lambda x: (
                not x["required"],  # 必填字段优先
                x["is_text"],  # 文本字段放最后
                x["is_m2m"],  # 多对多字段放在文本字段之前
                x["name"],  # 同类型字段按名称排序
            )
        )
        # 转换为字典格式返回
        return {field["name"]: {k: v for k, v in field.items()} for field in fields}

    def get_csv_example(self):
        """生成CSV示例"""
        fields = []
        values = []

        for field_name, field_info in self.get_field_guide().items():
            fields.append(field_name)

            # 生成示例值
            if field_info.get("related_model"):
                # 获取一个实际的示例对象
                related_model = self.model._meta.get_field(
                    field_name
                ).remote_field.model
                example_obj = related_model.objects.first()
                if example_obj and field_info["search_fields"]:
                    example_value = getattr(
                        example_obj, field_info["search_fields"][0], ""
                    )
                    values.append(str(example_value))
                else:
                    if field_info["required"]:
                        values.append(f"{field_info['related_model']}-001")
                    else:
                        values.append(f"[{field_info['related_model']}-可选]")
            elif field_info.get("choices"):
                first_choice = field_info["choices"][0]
                if field_info["required"]:
                    values.append(f"{first_choice['value']}")
                else:
                    values.append(f"[{first_choice['value']}]")
            elif field_name == "name":
                values.append("Device-001")
            elif field_name == "serial_number":
                values.append("SN12345678")
            elif field_info["type"] == _("布尔值"):
                values.append("true" if field_info["required"] else "[true]")
            elif field_info["type"] == _("日期"):
                values.append(
                    "2024-01-01" if field_info["required"] else "[2024-01-01]"
                )
            elif field_info["type"] == _("时间"):
                values.append("12:00:00" if field_info["required"] else "[12:00:00]")
            elif field_info["type"] == _("日期时间"):
                values.append(
                    "2024-01-01 12:00:00"
                    if field_info["required"]
                    else "[2024-01-01 12:00:00]"
                )
            elif field_info["type"] in [
                _("整数"),
                _("小整数"),
                _("大整数"),
                _("正整数"),
            ]:
                if field_name == "height":
                    values.append("2")  # 设备高度通常为2U
                elif field_name == "position":
                    values.append("42")  # 机柜位置示例
                else:
                    values.append("1" if field_info["required"] else "[1]")
            elif field_info["type"] in [_("浮点数"), _("小数")]:
                values.append("1.0" if field_info["required"] else "[1.0]")
            else:
                if field_info["required"]:
                    values.append(f"{field_info['label']}-示例")
                else:
                    values.append(f"[{field_info['label']}-可选]")

        return f"{','.join(fields)}\n{','.join(values)}"

    def get_csv_template(self):
        """生成包含字段说明的CSV模板"""
        field_names = []
        field_labels = []
        example_values = []

        for field_name, field_info in self.get_field_guide().items():
            field_names.append(field_name)
            field_labels.append(str(field_info["label"]))

            # 获取示例值
            if field_info.get("default") not in [None, ""]:
                # 使用默认值作为示例
                example_values.append(str(field_info["default"]))
            elif field_info.get("related_model"):
                # 处理关联字段
                related_model = self.model._meta.get_field(
                    field_name
                ).remote_field.model
                example_obj = related_model.objects.first()
                if example_obj and field_info["search_fields"]:
                    example_value = getattr(
                        example_obj, field_info["search_fields"][0], ""
                    )
                    example_values.append(str(example_value))
                else:
                    if field_info["required"]:
                        example_values.append(f"{field_info['related_model']}-001")
                    else:
                        example_values.append("")
            elif field_info.get("choices"):
                # 处理选择字段
                first_choice = field_info["choices"][0]
                if field_info["required"]:
                    example_values.append(f"{first_choice['value']}")
                else:
                    example_values.append("")
            else:
                # 根据字段类型生成示例值
                example_map = {
                    _("整数"): "1",
                    _("小整数"): "1",
                    _("大整数"): "1",
                    _("正整数"): "1",
                    _("浮点数"): "1.0",
                    _("小数"): "1.0",
                    _("布尔值"): "true",
                    _("日期"): "2024-01-01",
                    _("时间"): "12:00:00",
                    _("日期时间"): "2024-01-01 12:00:00",
                }

                example_value = example_map.get(field_info["type"], "")
                if not example_value and field_info["required"]:
                    example_value = f"{field_info['label']}-示例"
                example_values.append(example_value)

        # 返回字典格式，不包含 field_helps
        return {
            "field_names": field_names,
            "field_labels": field_labels,
            "example_values": example_values,
        }

    def get_csv_charset(self):
        """获取CSV字符集"""
        accept_charset = self.request.headers.get("User-Agent")
        return "utf-8-sig" if "Windows NT" in accept_charset else "utf-8"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        model_name = camel_to_snake(self.model._meta.object_name)
        list_url = reverse_lazy(f"{model_name}_list")
        context.update(
            {
                "model_name": self.model._meta.verbose_name,
                "field_guide": self.get_field_guide(),
                "csv_example": self.get_csv_example(),
                "return_url": list_url,
            }
        )
        return context

    def convert_field_value(self, field, value):
        """使用 Django 字段的 to_python 方法进行类型转换"""
        if value is None or value == "":
            return None

        try:
            # 对于外键字段，value 已经是对象，直接返回
            if isinstance(field, (models.ForeignKey, models.OneToOneField)):
                return value

            # 使用字段的 to_python 方法进行转换
            return field.to_python(value)

        except (ValidationError, ValueError) as e:
            raise ValidationError(
                f"字段 {field.verbose_name} 的值 '{value}' 转换失败: {str(e)}"
            )

    def form_valid(self, form):
        success_count = 0
        error_count = 0
        error_messages = []

        rows_data = form.cleaned_data.get("rows_data", [])

        m2m_fields = {
            field.name: field
            for field in self.model._meta.get_fields()
            if isinstance(field, models.ManyToManyField)
        }

        # 获取所有模型字段的映射
        model_fields = {
            field.name: field
            for field in self.model._meta.get_fields()
            if not isinstance(field, models.ManyToManyField)
        }

        for row_num, row_data in enumerate(rows_data, start=1):
            try:
                m2m_data = {}
                instance_data = {}

                # 2. 数据中心处理保持不变
                instance_data["data_center"] = row_data.get("data_center")
                if not instance_data["data_center"]:
                    instance_data["data_center"] = self.request.user.data_center

                # 3. 创建者处理保持不变
                instance_data["created_by"] = row_data.get("created_by")
                if not instance_data["created_by"]:
                    instance_data["created_by"] = self.request.user

                # 处理其他字段，包括类型转换
                for field_name, value in row_data.items():
                    if field_name in ["created_at", "data_center", "created_by"]:
                        continue

                    if value is None:
                        continue

                    # 如果是多对多字段，存储到 m2m_data
                    if field_name in m2m_fields:
                        m2m_data[field_name] = value
                    else:
                        # 获取字段对象并进行类型转换
                        field = model_fields.get(field_name)
                        if field:
                            try:
                                converted_value = self.convert_field_value(field, value)
                                instance_data[field_name] = converted_value
                            except ValidationError as e:
                                raise ValidationError(f"第 {row_num} 行: {str(e)}")

                logger.info(f"DEBUG: 第 {row_num} 行准备创建数据: {instance_data}")
                logger.info(f"DEBUG: 第 {row_num} 行多对多数据: {m2m_data}")

                # 创建对象
                obj, created = self.model.objects.get_or_create(**instance_data)
                # 处理多对多关系
                for field_name, related_objects in m2m_data.items():
                    if not related_objects:
                        continue

                    m2m_field = getattr(obj, field_name)
                    # 如果是QuerySet或列表，直接添加
                    if isinstance(related_objects, (models.QuerySet, list)):
                        # print(related_objects)
                        m2m_field.add(*related_objects)
                    # 如果是单个对象，添加这个对象
                    else:
                        m2m_field.add(related_objects)
                # obj.save_m2m()
                success_count += 1
                logger.info(f"DEBUG: 第 {row_num} 行创建成功: {obj}")

            except Exception as e:
                error_count += 1
                error_msg = f"第 {row_num} 行: {str(e)}"
                error_messages.append(error_msg)
                logger.info(f"DEBUG: {error_msg}")
                continue

        # 显示成功消息
        if success_count:
            messages.success(
                self.request,
                f"成功导入 {success_count} 条{self.model._meta.verbose_name}记录",
            )

        # 显示错误消息
        if error_messages:
            for msg in error_messages:
                messages.error(self.request, msg)
            messages.error(
                self.request,
                f"导入失败 {error_count} 条{self.model._meta.verbose_name}记录",
            )

        # 如果有成功导入的记录，就返回成功页面
        if success_count > 0:
            return super().form_valid(form)

        # 如果全部失败，返回表单页面
        return super().form_invalid(form)

    def get_success_url(self):
        model_name = camel_to_snake(self.model._meta.object_name)
        success_url = self.return_url or reverse_lazy(f"{model_name}_list")
        return success_url

    def get(self, request, *args, **kwargs):
        if "download_template" in request.GET:
            return self.download_csv_template(request, *args, **kwargs)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        logger.info("DEBUG: 处理POST请求")
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        # 即使表单验证失败，如果有有效数据，也要处理
        if "rows_data" in form.cleaned_data:
            return self.form_valid(form)
        return super().form_invalid(form)

    def download_csv_template(self, request, *args, **kwargs):
        """处理CSV模板下载"""
        # 创建一个内存中的文件对象
        output = io.StringIO()

        # 获取CSV数据
        template_data = self.get_csv_template()

        # 创建CSV写入器
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        # 写入四行数据
        writer.writerow(template_data["field_names"])
        writer.writerow(template_data["field_labels"])
        writer.writerow(template_data["example_values"])

        # 准备响应
        filename = quote("{}导入模板.csv".format(self.model._meta.verbose_name))
        content_type = f"application/octet-stream; charset={self.get_csv_charset()}"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        }
        response = HttpResponse(
            output.getvalue().encode(self.get_csv_charset()),
            content_type=content_type,
            headers=headers,
        )

        return response
