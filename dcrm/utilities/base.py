import logging
import re
from itertools import chain

import exrex
from django.contrib.admin.utils import label_for_field
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models.constants import LOOKUP_SEP
from django.utils.text import camel_case_to_spaces, slugify
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


def camel_to_snake(name, seq="_"):
    """将驼峰命名转换为蛇形命名
    ModelHost -> model_host
    objectHost -> object_host
    eg:
    opts.object_name == 'ModelHost'
    """
    return slugify(camel_case_to_spaces(name)).replace("-", seq)


def expand_regex_pattern(pattern: str, limit: int = 1000) -> list[str]:
    """展开正则表达式模式

    Args:
        pattern: 正则表达式模式字符串
        limit: 生成结果的最大数量,默认1000个

    Returns:
        List[str]: 展开后的字符串列表

    Raises:
        ValueError: 当正则表达式无效或结果数量超过限制时

    """
    logger.debug("开始展开正则表达式模式: %s, 限制数量: %d", pattern, limit)

    if not pattern or not isinstance(pattern, str):
        error_msg = _("正则表达式模式必须是非空字符串")
        logger.error(error_msg)
        raise ValueError(error_msg)

    try:
        # 验证正则表达式的有效性
        re.compile(pattern)
        logger.debug("正则表达式语法验证通过")

        # 计算可能的组合数量
        count = exrex.count(pattern)
        logger.info("正则表达式可能生成 %d 个结果", count)

        if count > limit:
            error_msg = _("正则表达式可能产生过多结果: %(count)d > %(limit)d") % {
                "count": count,
                "limit": limit,
            }
            logger.error(error_msg)
            raise ValueError(error_msg)

        # 生成结果
        results = list(exrex.generate(pattern))

        # 验证结果
        if not results:
            error_msg = _("正则表达式未能生成任何结果")
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info("成功生成 %d 个结果", len(results))
        return results

    except re.error as e:
        error_msg = _("无效的正则表达式: %(error)s") % {"error": str(e)}
        logger.error(error_msg)
        raise ValueError(error_msg)
    except Exception as e:
        error_msg = _("展开正则表达式时发生错误: %(error)s") % {"error": str(e)}
        logger.error(error_msg, exc_info=True)  # 包含完整的异常堆栈
        raise ValueError(error_msg)


def get_object_opts(obj):
    """获取模型 Meta Options
    支持 model, model queryset, model instance or model Meta.
    """
    if isinstance(obj, (models.Model, models.base.ModelBase)):
        opts = obj._meta
    elif isinstance(obj, models.query.QuerySet):
        opts = obj.model._meta
    else:
        opts = obj
    return opts


def lookup_field_verbose(obj, custom_fields, field_name, custom_fields_maps=None):
    """获取字段的 verbose_name。支持外键路径（如 'model__name'）和方法的 short_description。

    Args:
        obj: Django Model instance
        field_name: 字段名，支持外键路径，如 'model__name'

    Returns:
        str: 字段的 verbose_name

    Raises:
        ValueError: 如果 obj 不是 Django Model 实例
        FieldDoesNotExist: 如果字段不存在

    """
    opts = get_object_opts(obj)

    try:
        # 一对多字段
        _field = opts.get_field(field_name)
        if _field.one_to_many:
            return _field.related_model._meta.verbose_name

        # 常规字段
        return label_for_field(field_name, opts.model)

    except FieldDoesNotExist:
        # 外键字段 model__type
        if LOOKUP_SEP in field_name:
            parts = field_name.split(LOOKUP_SEP)
            model = opts.model
            for i, part in enumerate(parts[:-1]):
                field = model._meta.get_field(part)
                if not field.is_relation:
                    break
                model = field.remote_field.model
            field = model._meta.get_field(parts[-1])
            return field.verbose_name
        # 方法的 short_description
        attr = getattr(obj, field_name, None)
        if attr and hasattr(attr, "short_description"):
            return attr.short_description
        else:
            # 使用 maps 避免重复查询
            if custom_fields_maps:
                custom_field = custom_fields_maps.get(field_name, None)
                if custom_field:
                    return custom_field.label
            if custom_fields:
                # 处理自定义字段 需要一次查询
                custom_field = custom_fields.filter(name=field_name).first()
                if custom_field:
                    return custom_field.label
            raise ValueError(f"字段 '{field_name}' 不存在")
    except Exception as e:
        raise ValueError(f"处理字段 '{field_name}' 时发生错误: {str(e)}")


def get_content_type_by_labeled_name(labeled_name: str) -> ContentType:
    """通过 app_labeled_name 反向查询 ContentType

    Args:
        labeled_name: 格式为 "app_label | verbose_name" 的字符串

    Returns:
        ContentType 实例

    Raises:
        ContentType.DoesNotExist: 如果找不到匹配的 ContentType

    """
    from django.apps import apps

    if "|" in labeled_name:
        app_label, verbose_name = labeled_name.split("|")
    else:
        verbose_name = labeled_name
    app_models = apps.get_models()
    result = []
    for model in app_models:
        opts = model._meta
        if opts.verbose_name == verbose_name.strip():
            result.append(model)
    if len(result) >= 1:
        return ContentType.objects.get_for_model(result[0])
    else:
        raise ContentType.DoesNotExist(
            f"Invalid format for labeled_name: {labeled_name}"
        )


def merge_multiple_keywords(*keyword_tuples):
    """使用 chain 合并多个关键词元组"""
    # 先展平元组列表,再展平每个元组
    keywords = set(chain.from_iterable(chain.from_iterable(keyword_tuples)))
    # 移除空字符串和 None
    keywords.discard("")
    keywords.discard(None)
    return keywords
