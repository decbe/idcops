from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db.models import Q
from django.db.models.base import Model
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from django.utils.translation import gettext_lazy as _


class CustomFieldFormField(forms.Field):
    """自定义字段的表单字段"""

    def __init__(self, custom_field, *args, **kwargs):
        self.custom_field = custom_field

        # 设置基础属性
        kwargs.update(
            {
                "label": custom_field.label or custom_field.name,
                "required": custom_field.required,
                "help_text": custom_field.help_text,
                "initial": custom_field.default_value,
            }
        )

        # 根据字段类型设置具体的表单字段
        field_class, field_kwargs = self._get_field_class_and_kwargs()
        kwargs.update(field_kwargs)

        # 调用对应字段类型的构造函数
        self.field = field_class(**kwargs)
        super().__init__(**kwargs)

    def _get_field_class_and_kwargs(self):
        """根据自定义字段类型返回对应的表单字段类和参数"""
        field_type = self.custom_field.type
        kwargs = {}

        type_map = {
            "string": (
                forms.CharField,
                {
                    "max_length": 255,
                    "widget": forms.TextInput(attrs={"class": "vTextField"}),
                },
            ),
            "text": (
                forms.CharField,
                {"widget": forms.Textarea(attrs={"class": "vLargeTextField"})},
            ),
            "integer": (
                forms.IntegerField,
                {"widget": forms.NumberInput(attrs={"class": "vIntegerField"})},
            ),
            "decimal": (
                forms.DecimalField,
                {
                    "max_digits": 10,
                    "decimal_places": 2,
                    "widget": forms.NumberInput(attrs={"class": "vDecimalField"}),
                },
            ),
            "boolean": (
                forms.BooleanField,
                {"widget": forms.CheckboxInput(attrs={"class": "vCheckboxField"})},
            ),
            "date": (
                forms.DateField,
                {
                    "widget": forms.DateInput(
                        attrs={"class": "vDateField", "type": "date"}
                    )
                },
            ),
            "datetime": (
                forms.DateTimeField,
                {
                    "widget": forms.DateTimeInput(
                        attrs={"class": "vDateTimeField", "type": "datetime-local"}
                    )
                },
            ),
            "url": (
                forms.URLField,
                {"widget": forms.URLInput(attrs={"class": "vURLField"})},
            ),
            "email": (
                forms.EmailField,
                {"widget": forms.EmailInput(attrs={"class": "vEmailField"})},
            ),
            "choice": (forms.ChoiceField, self._get_choice_kwargs()),
            "multi_choice": (
                forms.MultipleChoiceField,
                self._get_choice_kwargs(multiple=True),
            ),
        }

        field_class, base_kwargs = type_map.get(field_type, (forms.CharField, {}))
        kwargs.update(base_kwargs)

        # 添加验证器
        if self.custom_field.validation_regex:
            kwargs["validators"] = [
                RegexValidator(
                    regex=self.custom_field.validation_regex,
                    message=self.custom_field.validation_error_message
                    or _("Value does not match the required format"),
                )
            ]

        return field_class, kwargs

    def _get_choice_kwargs(self, multiple=False):
        """获取选择字段的参数"""
        choices = []
        if not multiple and not self.custom_field.required:
            choices.append(("", "---------"))

        if self.custom_field.choices:
            choices.extend(
                [(c.strip(), c.strip()) for c in self.custom_field.choices.split(",")]
            )

        widget_class = forms.SelectMultiple if multiple else forms.Select
        return {
            "choices": choices,
            "widget": widget_class(attrs={"class": "vSelectField"}),
        }

    def clean(self, value):
        """清理和验证字段值"""
        return self.field.clean(value)


class DynamicModelChoiceField(forms.ModelChoiceField):
    """
    动态模型选择字段，支持API查询和动态过滤
    """

    def __init__(self, queryset, *args, **kwargs):
        self.query_params = kwargs.pop("query_params", {})
        self.null_option = kwargs.pop("null_option", True)

        # 新增：动态依赖字段配置
        self.dependencies = kwargs.pop("dependencies", [])
        self.dynamic_params = kwargs.pop("dynamic_params", {})

        # API相关配置
        self.api_url = kwargs.pop("api_url", None)
        self.display_field = kwargs.pop("display_field", "name")
        self.value_field = kwargs.pop("value_field", "id")

        # 初始化父类
        super().__init__(queryset, *args, **kwargs)

        # 设置widget属性
        self.widget = APISelectWidget(
            api_url=self.get_api_url(),
            display_field=self.display_field,
            value_field=self.value_field,
            dependencies=self.dependencies,
            attrs=self.widget.attrs,
        )

    def get_api_url(self):
        """获取API URL"""
        if self.api_url:
            try:
                return reverse(self.api_url)
            except NoReverseMatch as e:
                raise e
        model = self.queryset.model
        return f"/api/v1/{model._meta.app_label}/{model._meta.model_name}/"

    def get_filters(self, form):
        """
        获取过滤条件
        """
        filters = Q()

        # 处理基本查询参数
        for param, field_name in self.query_params.items():
            field_value = self.get_field_value(form, field_name)
            if field_value:
                filters &= Q(**{param: field_value})

        # 处理动态参数
        for param, config in self.dynamic_params.items():
            if callable(config):
                try:
                    value = config(form)
                    if value is not None:
                        filters &= Q(**{param: value})
                except Exception:
                    continue
            elif isinstance(config, dict):
                field_name = config.get("field")
                transform = config.get("transform")
                if field_name:
                    value = self.get_field_value(form, field_name)
                    if value is not None and transform:
                        try:
                            value = transform(value)
                        except Exception:
                            continue
                    if value is not None:
                        filters &= Q(**{param: value})

        return filters

    def get_field_value(self, form, field_name):
        """
        获取字段值，处理各种数据来源和类型转换
        """
        value = None

        # 处理表单前缀
        prefixed_name = field_name
        if hasattr(form, "prefix") and form.prefix:
            prefixed_name = f"{form.prefix}-{field_name}"

        # 处理数组字段名称（多选字段）
        array_name = f"{prefixed_name}[]"  # 处理request.POST/GET中的数组格式

        # 按优先级获取值
        if hasattr(form, "cleaned_data") and field_name in form.cleaned_data:
            value = form.cleaned_data.get(field_name)
        elif form.is_bound:
            # 检查常规字段名
            if field_name in form.data or prefixed_name in form.data:
                key = prefixed_name if prefixed_name in form.data else field_name
                value = form.data.get(key)
            # 检查多值字段（多选）
            elif array_name in form.data:
                value = form.data.getlist(array_name)
            # 检查是否存在多值数据，即使名称不是数组格式
            elif prefixed_name in form.data and hasattr(form.data, "getlist"):
                multi_values = form.data.getlist(prefixed_name)
                if len(multi_values) > 1:
                    value = multi_values
                else:
                    value = form.data.get(prefixed_name)
        elif hasattr(form, "initial") and field_name in list(form.initial):
            value = form.initial.get(field_name)

        # 新增: 检查请求对象中是否包含相关依赖项的值
        # 这用于处理Choices.js发送的AJAX请求
        if (
            value is None
            and hasattr(form, "request")
            and getattr(form, "request", None) is not None
        ):
            request = form.request
            # 检查URL参数中的字段值
            if request.GET and field_name in request.GET:
                value = request.GET.get(field_name)
            # 处理多值字段
            elif f"{field_name}[]" in request.GET:
                value = request.GET.getlist(f"{field_name}[]")
            # 检查POST请求中的JSON数据
            elif (
                hasattr(request, "POST") and request.content_type == "application/json"
            ):
                try:
                    import json

                    post_data = json.loads(request.body)
                    if field_name in post_data:
                        value = post_data.get(field_name)
                except (ValueError, json.JSONDecodeError):
                    pass

        # 处理空字符串
        if value == "":
            value = None

        # 处理外键字段和对象转换
        if value is not None and hasattr(form, "fields") and field_name in form.fields:
            field = form.fields[field_name]

            # 处理单选模型字段
            if isinstance(field, forms.ModelChoiceField) and not isinstance(
                field, forms.ModelMultipleChoiceField
            ):
                try:
                    value = field.to_python(value)
                except ValidationError:
                    return None

            # 处理多选模型字段
            elif isinstance(field, forms.ModelMultipleChoiceField):
                if isinstance(value, list):
                    try:
                        # 转换多个ID为对象列表
                        value = [field.to_python(v) for v in value if v]
                        # 过滤掉None值
                        value = [v for v in value if v is not None]
                    except ValidationError:
                        return None
                elif value:  # 单个值但在多选字段
                    try:
                        obj = field.to_python(value)
                        value = [obj] if obj is not None else []
                    except ValidationError:
                        return None

        return value

    def get_bound_field(self, form, field_name):
        """
        获取绑定字段时动态更新查询集
        """
        bound_field = super().get_bound_field(form, field_name)
        filters = self.get_filters(form)

        # 更新查询集
        if filters:
            self.queryset = self.queryset.filter(filters)
        else:
            # 如果有依赖字段但没有选择值，返回空查询集
            if self.dependencies:
                self.queryset = self.queryset.none()
            self.queryset = self.queryset.none()
        return bound_field

    def label_from_instance(self, obj):
        """
        自定义对象显示标签
        """
        if hasattr(obj, "get_display_name"):
            return obj.get_display_name()
        if hasattr(obj, self.display_field):
            return getattr(obj, self.display_field)
        return str(obj)


class DynamicModelMultipleChoiceField(
    DynamicModelChoiceField, forms.ModelMultipleChoiceField
):
    """
    动态多选模型字段
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.widget = APISelectMultipleWidget(attrs=self.widget.attrs)


class APISelectWidget(forms.Select):
    """
    支持API查询的Select部件，使用Choices.js实现
    display_field: 用于显示的字段名, 可以多个字段联合使用，使用逗号分割，例如：name,type
    """

    template_name = "dcrm/widgets/api_select.html"

    def __init__(
        self,
        api_url=None,
        display_field="_repr",
        value_field="id",
        dependencies=None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        # 基础类和数据属性
        classes = ["form-control", "choices-select", "object-select"]
        if dependencies:
            classes.append("dynamic-select")

        self.attrs.update(
            {
                "class": " ".join(classes),
                "data-api-url": api_url,
                "data-display-field": display_field,
                "data-value-field": value_field,
            }
        )

        if dependencies:
            self.attrs["data-dependencies"] = ",".join(dependencies)
            # 添加自定义数据属性，用于前端JS处理
            self.attrs["data-dynamic-filter"] = "true"

    def get_context(self, name, value, attrs):
        """重写获取上下文方法，添加额外的JS处理逻辑"""
        context = super().get_context(name, value, attrs)

        # 检查是否有依赖项
        if "data-dependencies" in self.attrs:
            # 这里可以添加任何需要传递给模板的额外属性
            context["widget"]["attrs"]["data-field-name"] = name

        return context


class APISelectMultipleWidget(APISelectWidget, forms.SelectMultiple): ...


class DeviceModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        # 构建显示信息
        return f"{obj} ({obj.height}U | {obj.power_port_count}电源)"


class DeviceRackChoiceField(forms.ModelChoiceField):
    """
    机柜选择字段，支持动态加载和过滤
    """

    def label_from_instance(self, obj):
        """自定义机柜显示格式"""
        if obj.tenant:
            return f"{obj.name} ({obj.tenant.name})"
        return f"{obj.name} ({obj.get_rack_type_display()})"


class DeviceIPAddressChoiceField(forms.ModelMultipleChoiceField):

    def label_from_instance(self, obj: Model) -> str:
        return f"{obj.address} ({obj.ip_type_display})"
