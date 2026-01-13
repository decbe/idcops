from collections import defaultdict
from typing import Any

from django.core.management.base import BaseCommand

from dcrm.register import registry
from dcrm.signals.counters import update_counts


class Command(BaseCommand):
    help = "强制重新计算所有已缓存的计数字段"

    @staticmethod
    def collect_models() -> defaultdict[Any, dict]:
        """查询注册表，查找所有具有一个或多个计数字段的模型。返回每个模型的计数字段到相关查询名称的映射。
        """
        models = defaultdict(dict)

        for model, field_mappings in registry["counter_fields"].items():
            for field_name, counter_name in field_mappings.items():
                fk_field = model._meta.get_field(field_name)  # Interface.device
                parent_model = fk_field.related_model  # Device
                related_query_name = fk_field.related_query_name()  # 'interfaces'
                models[parent_model][counter_name] = related_query_name

        return models

    def handle(self, *model_names, **options) -> None:
        for model, mappings in self.collect_models().items():
            for field_name, related_query in mappings.items():
                update_counts(model, field_name, related_query)
