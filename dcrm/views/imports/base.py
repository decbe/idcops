from django.contrib import messages
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic.edit import FormView

from dcrm.forms.imports import BaseImportForm


class BaseImportView(FormView):
    template_name = "generic/bulk_import.html"
    form_class = BaseImportForm
    success_url = None
    model = None
    _registry = {}  # 用于存储模型和导入视图的映射

    @classmethod
    def register(cls, model_class, import_view):
        """注册模型的导入视图"""
        cls._registry[model_class] = import_view

    @classmethod
    def get_import_view(cls, model_class):
        """获取模型的导入视图"""
        return cls._registry.get(model_class)

    def get_form_kwargs(self):
        """传递额外的参数到表单"""
        kwargs = super().get_form_kwargs()
        kwargs["model"] = self.model
        kwargs["request"] = self.request  # 添加 request 参数
        return kwargs

    def get_success_url(self):
        if self.success_url:
            return self.success_url
        return reverse_lazy(f"dcrm:{self.model._meta.model_name}_list")

    def form_valid(self, form):
        if form.cleaned_data.get("has_errors", False):
            return self.form_invalid(form)

        rows_data = form.cleaned_data["rows_data"]
        created_count = 0

        try:
            for row_data in rows_data:
                instance = self.model()

                for field_name, value in row_data.items():
                    # 使用 fields_map 获取字段类型信息
                    field = form.fields_map[field_name]

                    # 特殊处理关联字段
                    if field_name in form.related_fields:
                        # 处理外键关系
                        setattr(instance, field_name, value)
                    else:
                        # 处理普通字段
                        setattr(instance, field_name, value)

                # 设置数据中心和创建者
                if hasattr(instance, "data_center") and not instance.data_center:
                    instance.data_center = self.request.user.data_center
                if hasattr(instance, "created_by") and not instance.created_by:
                    instance.created_by = self.request.user

                instance.save()
                created_count += 1

            messages.success(
                self.request, _("成功导入 {} 条记录").format(created_count)
            )
            return super().form_valid(form)

        except Exception as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("导入{}").format(self.model._meta.verbose_name)
        return context
