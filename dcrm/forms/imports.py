import csv
import logging
from io import StringIO

import dateparser
from charset_normalizer import detect
from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import get_text_list
from django.utils.translation import gettext_lazy as _

from dcrm.models.mixins import CustomFieldsMixin
from dcrm.views.imports.csv import (
    CSVChoiceField,
    CSVModelChoiceField,
    CSVModelMultipleChoiceField,
    CSVRackPDUField,
    convert_custom_field_value,
)

# from dcrm.utilities.base import get_content_type_by_labeled_name


logger = logging.getLogger(__name__)


class BaseImportForm(forms.Form):
    csv_data = forms.FileField(
        label=_("CSV 格式数据文件"),
        help_text=_("请上传 CSV 文件，文件格式参考下载的模板文件"),
    )

    def __init__(self, *args, **kwargs):
        self.model = kwargs.pop("model")
        self.request = kwargs.pop("request")
        self.exclude_fields = [
            "lft",
            "rght",
            "tree_id",
            "level",
            "id",
            "updated_at",
            "password",
            "_password",
        ]
        super().__init__(*args, **kwargs)

        logger.info("DEBUG: 初始化导入表单，模型: %s", self.model._meta.verbose_name)
        self.fields_map = {}
        self.related_fields = {}
        self.custom_fields_map = {}  # 存储自定义字段映射
        # 获取请求头中的Accept-Charset
        accept_charset = self.request.headers.get("User-Agent")
        self.csv_charset = "utf-8-sig" if "Windows NT" in accept_charset else "utf-8"
        self._build_fields()

    def _get_search_fields(self, field):
        """获取外键字段的查找字段列表
        """
        related_model = field.remote_field.model
        search_fields = []

        # 常用字段名称列表
        common_fields = ["name", "title", "label", "code", "number", "serial"]

        # 首先检查模型是否定义了search_fields
        if hasattr(related_model, "search_fields"):
            return related_model.search_fields

        # 检查常用字段
        for field_name in common_fields:
            if field_name in [f.name for f in related_model._meta.fields]:
                search_fields.append(field_name)

        # 如果没有找到任何匹配字段，使用主键
        if not search_fields:
            search_fields = ["pk"]

        return search_fields

    def _build_fields(self):
        """构建导入字段"""
        model_fields = list(filter(lambda x: x.editable, self.model._meta.fields))
        m2m_fields = list(self.model._meta.many_to_many)

        for field in model_fields + m2m_fields:
            if field.name in self.exclude_fields:
                continue

            # 特殊字段处理：created_at, data_center, created_by 不需要必填
            is_special_field = field.name in ["created_at", "data_center", "created_by"]
            field_required = (
                False
                if is_special_field
                else (field.blank is False and field.null is False)
            )

            if isinstance(field, (models.ForeignKey, models.ManyToManyField)):
                search_fields = self._get_search_fields(field)
                if field.name == "data_center":
                    help_text = _("数据中心名称，留空则使用当前用户的数据中心")
                elif field.name == "created_by":
                    help_text = _("创建者用户名，留空则使用当前用户")
                else:
                    help_text = _("输入 {model} 中的 {fields} 字段值").format(
                        fields=get_text_list(search_fields),
                        model=field.remote_field.model._meta.verbose_name,
                    )

                if isinstance(field, models.ForeignKey):
                    self.fields[field.name] = CSVModelChoiceField(
                        queryset=field.remote_field.model.objects.all(),
                        required=field_required,
                        search_fields=search_fields,
                        label=field.verbose_name,
                        help_text=help_text,
                    )
                else:
                    # 对于rack_pdus字段，使用专门的CSVRackPDUField，限制在rack下查找
                    if field.name == "rack_pdus":
                        self.fields[field.name] = CSVRackPDUField(
                            queryset=field.remote_field.model.objects.all(),
                            required=field_required,
                            search_fields=search_fields,
                            label=field.verbose_name,
                            help_text=_(
                                "输入PDU名称（多个值用逗号,分隔），将在当前行的机柜下查找"
                            ),
                        )
                    else:
                        self.fields[field.name] = CSVModelMultipleChoiceField(
                            queryset=field.remote_field.model.objects.all(),
                            required=field_required,
                            search_fields=search_fields,
                            label=field.verbose_name,
                            help_text=help_text,
                        )
                self.related_fields[field.name] = field

            elif isinstance(field, models.DateTimeField) and field.name == "created_at":
                self.fields[field.name] = forms.CharField(
                    required=False,
                    label=field.verbose_name,
                    help_text=_("创建时间，格式：YYYY-MM-DD HH:MM，留空则使用当前时间"),
                )

            elif isinstance(field, models.BooleanField):
                self.fields[field.name] = forms.BooleanField(
                    required=False, label=field.verbose_name
                )

            elif hasattr(field, "choices") and field.choices:
                self.fields[field.name] = CSVChoiceField(
                    choices=field.choices,
                    required=field_required,
                    label=field.verbose_name,
                )

            else:
                self.fields[field.name] = forms.CharField(
                    required=field_required, label=field.verbose_name
                )

            self.fields_map[field.name] = field

        # 构建自定义字段
        self._build_custom_fields()

    def _build_custom_fields(self):
        """构建自定义字段"""
        # 检查模型是否支持自定义字段
        if not issubclass(self.model, CustomFieldsMixin):
            return

        from dcrm.models.customfields import CustomField

        # 获取用户的数据中心
        data_center = getattr(self.request.user, "data_center", None)
        if not data_center:
            return

        # 获取该模型的自定义字段
        try:
            custom_fields = CustomField.objects.get_for_model(
                self.model, data_center, hidden=False
            )
        except Exception as e:
            logger.warning(f"获取自定义字段失败: {e}")
            return

        # 为每个自定义字段创建表单字段
        for cf in custom_fields:
            field_name = f"_cf_{cf.name}"
            # 使用 to_form_field 创建字段，但调整为导入场景
            form_field = cf.to_form_field(set_initial=False, enforce_required=False)
            # 调整字段属性
            form_field.required = cf.required
            form_field.label = cf.label or cf.name
            form_field.help_text = cf.description or ""
            # 存储自定义字段映射
            self.custom_fields_map[field_name] = cf
            self.fields[field_name] = form_field

    def test_csv_header(self, reader):
        """判断 csv 文件第2行是不是模型字段名称
        """
        field_verbose_names = {
            field.verbose_name: field.name for field in self.model._meta.fields
        }
        csv_field_names = reader.fieldnames

        from collections import Counter

        line = Counter(csv_field_names) + Counter(field_verbose_names.keys())
        logger.warning("DEBUG: 字段匹配结果: %s", line)

    def clean(self):
        cleaned_data = super().clean()
        if "csv_data" in cleaned_data:
            csv_file = cleaned_data["csv_data"]
            logger.info("DEBUG: 表单清理 - 开始处理文件")

            # 读取CSV二进制内容
            csv_file.seek(0)  # 确保从文件开头读取
            raw_bytes = csv_file.read()

            # 确保是字节类型
            if isinstance(raw_bytes, str):
                raw_bytes = raw_bytes.encode("utf-8")

            # 自动检测编码
            detected = detect(raw_bytes)
            detected_encoding = None
            confidence = 0

            if detected:
                detected_encoding = detected.get("encoding")
                confidence = detected.get("confidence", 0)

            logger.info(
                "DEBUG: 检测到编码: %s (置信度: %.2f%%)",
                detected_encoding or "未知",
                confidence * 100,
            )

            # 根据检测结果选择编码
            # 如果检测到的编码置信度较高，优先使用检测到的编码
            if detected_encoding and confidence >= 0.7:
                try:
                    content = raw_bytes.decode(detected_encoding)
                    logger.info(
                        "DEBUG: 使用检测到的编码 %s 成功解码", detected_encoding
                    )
                except (UnicodeDecodeError, LookupError) as e:
                    logger.warning(
                        "DEBUG: 使用检测到的编码 %s 失败: %s，尝试使用默认编码: %s",
                        detected_encoding,
                        str(e),
                        self.csv_charset,
                    )
                    try:
                        content = raw_bytes.decode(self.csv_charset)
                    except (UnicodeDecodeError, LookupError):
                        # 最后尝试使用 UTF-8
                        content = raw_bytes.decode("utf-8", errors="replace")
            else:
                # 置信度较低或未检测到编码，使用默认编码
                logger.info(
                    "DEBUG: 编码检测置信度较低或未检测到，使用默认编码: %s",
                    self.csv_charset,
                )
                try:
                    content = raw_bytes.decode(self.csv_charset)
                except (UnicodeDecodeError, LookupError):
                    # 如果默认编码失败，尝试使用检测到的编码或 UTF-8
                    fallback_encoding = detected_encoding or "utf-8"
                    logger.warning(
                        "DEBUG: 默认编码失败，尝试使用: %s", fallback_encoding
                    )
                    content = raw_bytes.decode(fallback_encoding, errors="replace")

            # 此时 content 已经是 UTF-8 编码的字符串（Python 3 中字符串默认是 UTF-8）
            logger.info("DEBUG: 原始CSV内容（前500字符）:\n%s", content[:500])

            csv_file = StringIO(content)
            reader = csv.DictReader(csv_file)

            # self.test_csv_header(reader)

            logger.info("DEBUG: CSV字段: %s", reader.fieldnames)
            logger.info("DEBUG: 表单字段: %s", list(self.fields.keys()))

            # 存储所有行的数据
            rows_data = []
            row_num = 0
            has_errors = False

            try:
                for row in reader:
                    row_num += 1
                    logger.info("DEBUG: 处理第 %s 行数据: %s", row_num, row)
                    row_data = {}
                    row_has_errors = False

                    # 处理自定义字段
                    custom_fields_data = {}
                    for csv_field_name in row.keys():
                        if csv_field_name.startswith("_cf_"):
                            field_name = csv_field_name
                            if field_name in self.custom_fields_map:
                                cf = self.custom_fields_map[field_name]
                                value = row.get(csv_field_name, "").strip()
                                if value:
                                    try:
                                        # 使用转换函数处理自定义字段值
                                        converted_value = convert_custom_field_value(
                                            cf, value, self.request
                                        )
                                        # 使用字段名（去掉 _cf_ 前缀）存储
                                        custom_fields_data[cf.name] = converted_value
                                    except ValidationError as e:
                                        logger.info(
                                            "DEBUG: 第 %s 行自定义字段 %s 验证失败: %s",
                                            row_num,
                                            field_name,
                                            str(e),
                                        )
                                        self.add_error(
                                            field_name, _(f"第 {row_num} 行：{str(e)}")
                                        )
                                        row_has_errors = True
                                        has_errors = True

                    # 存储自定义字段数据
                    if custom_fields_data:
                        row_data["_custom_fields"] = custom_fields_data

                    # 处理每个字段（先处理非rack_pdus字段，确保rack字段先处理）
                    rack_pdus_field = None
                    rack_pdus_value = None

                    for field_name, field in self.fields.items():
                        if field_name == "csv_data":
                            continue
                        # 跳过自定义字段（已在上面处理）
                        if field_name.startswith("_cf_"):
                            continue

                        # 跳过rack_pdus字段，稍后单独处理
                        if isinstance(field, CSVRackPDUField):
                            rack_pdus_field = field
                            rack_pdus_value = row.get(field_name, "").strip()
                            continue

                        # 从CSV中获取值
                        csv_field_name = field_name

                        value = row.get(csv_field_name, "").strip()
                        logger.info(
                            "DEBUG: 处理字段 %s -> CSV值: '%s' (必填: %s)",
                            field_name,
                            value,
                            field.required,
                        )

                        try:
                            # 处理外键字段
                            if isinstance(field, CSVModelChoiceField):
                                if field_name == "data_center" and row_data.get(
                                    "data_center", None
                                ):
                                    value = row_data["data_center"]
                                    data_center = field.to_python(value)
                                    if (
                                        data_center
                                        and data_center
                                        in self.request.user.data_centers.all()
                                    ):
                                        row_data[field_name] = data_center
                                    else:
                                        raise ValidationError(
                                            _(
                                                f"你没有导入该数据中心资源的权限 {field.label}: {value}"
                                            )
                                        )
                                elif value:
                                    obj = field.to_python(value)
                                    if obj:
                                        row_data[field_name] = obj
                                        logger.info(
                                            "DEBUG: 外键字段 %s 找到对象: %s",
                                            field_name,
                                            obj,
                                        )
                                    else:
                                        raise ValidationError(
                                            _(f"未找到匹配的 {field.label}: {value}")
                                        )
                                elif field_name == "created_by":
                                    row_data[field_name] = None

                            # 处理布尔字段
                            elif isinstance(field, forms.BooleanField):
                                row_data[field_name] = value.lower() in [
                                    "true",
                                    "yes",
                                    "1",
                                    "y",
                                    "是",
                                ]

                            # 处理日期时间字段
                            elif isinstance(
                                self.fields_map.get(field_name), models.DateTimeField
                            ):
                                if value:
                                    row_data[field_name] = dateparser.parse(value)

                            # 处理日期字段
                            elif isinstance(
                                self.fields_map.get(field_name), models.DateField
                            ):
                                if value:
                                    row_data[field_name] = dateparser.parse(
                                        value
                                    ).date()

                            # 处理选择字段
                            elif isinstance(field, CSVChoiceField):
                                if value:
                                    row_data[field_name] = field.to_python(value)
                            elif isinstance(field, CSVModelMultipleChoiceField):
                                if value:
                                    row_data[field_name] = field.to_python(value)

                            # 处理其他字段
                            else:
                                if value:
                                    row_data[field_name] = field.to_python(value)

                        except ValidationError as e:
                            logger.info(
                                "DEBUG: 第 %s 行字段 %s 验证失败: %s",
                                row_num,
                                field_name,
                                str(e),
                            )
                            self.add_error(field_name, _(f"第 {row_num} 行：{str(e)}"))
                            row_has_errors = True
                            has_errors = True

                    # 最后处理rack_pdus字段，此时rack字段应该已经处理完成
                    if rack_pdus_field and rack_pdus_value:
                        try:
                            # 获取当前行的rack值
                            rack = row_data.get("rack")
                            if not rack:
                                raise ValidationError(
                                    _(
                                        "rack_pdus字段需要先确定rack值，请确保CSV中包含rack字段，且rack字段在当前行已处理"
                                    )
                                )
                            # 调用to_python时传入rack参数
                            row_data["rack_pdus"] = rack_pdus_field.to_python(
                                rack_pdus_value, rack=rack
                            )
                            logger.info(
                                "DEBUG: rack_pdus字段处理完成，rack: %s, pdus: %s",
                                rack,
                                row_data["rack_pdus"],
                            )
                        except ValidationError as e:
                            logger.info(
                                "DEBUG: 第 %s 行字段 rack_pdus 验证失败: %s",
                                row_num,
                                str(e),
                            )
                            self.add_error("rack_pdus", _(f"第 {row_num} 行：{str(e)}"))
                            row_has_errors = True
                            has_errors = True

                    if not row_has_errors:
                        rows_data.append(row_data)
                        logger.info(
                            "DEBUG: 第 %s 行数据验证成功: %s", row_num, row_data
                        )

            except StopIteration:
                if row_num == 0:
                    raise forms.ValidationError(_("CSV文件为空"))

            # 重置文件指针
            csv_file.seek(0)
            cleaned_data["csv_data"] = csv_file
            cleaned_data["rows_data"] = rows_data
            cleaned_data["has_errors"] = has_errors

            logger.info("DEBUG: 最终的cleaned_data: %s", cleaned_data)
            # print(f"DEBUG: 最终的cleaned_data: {cleaned_data}")
        return cleaned_data
