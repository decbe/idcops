import csv
import logging
from io import StringIO

import dateparser

from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import get_text_list
from django.utils.translation import gettext_lazy as _

from dcrm.views.imports.csv import (
    CSVChoiceField,
    CSVModelChoiceField,
    CSVModelMultipleChoiceField,
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
        # 获取请求头中的Accept-Charset
        accept_charset = self.request.headers.get("User-Agent")
        self.csv_charset = "utf-8-sig" if "Windows NT" in accept_charset else "utf-8"
        self._build_fields()

    def _get_search_fields(self, field):
        """
        获取外键字段的查找字段列表
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
        for field in list(self.model._meta.fields) + list(
            self.model._meta.local_many_to_many
        ):
            # for field in self.model._meta.fields:
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

    def test_csv_header(self, reader):
        """
        判断 csv 文件第2行是不是模型字段名称
        """
        field_verbose_names = {
            field.verbose_name: field.name for field in self.model._meta.fields
        }
        csv_field_names = reader.fieldnames

        from collections import Counter

        line = Counter(csv_field_names) + Counter(field_verbose_names.keys())
        logger.warn("DEBUG: 字段匹配结果: %s", line)

    def clean(self):
        cleaned_data = super().clean()
        if "csv_data" in cleaned_data:
            csv_file = cleaned_data["csv_data"]
            logger.info("DEBUG: 表单清理 - 开始处理文件")

            # 读取CSV内容
            content = csv_file.read().decode(self.csv_charset)
            logger.info("DEBUG: 原始CSV内容:\n%s", content)

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

                    # 处理每个字段
                    for field_name, field in self.fields.items():
                        if field_name == "csv_data":
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
