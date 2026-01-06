import sys
from typing import Any, Literal

from django.contrib import messages
from django.forms import modelformset_factory
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_htmx.http import HttpResponseClientRedirect

from dcrm.forms.inventory import (
    ItemInstanceHistoryStockOutForm,
)
from dcrm.models import CodingRule, ItemInstance, ItemInstanceHistory, LogEntry
from dcrm.models.base import LogEntry
from dcrm.models.choices import (
    ActionColorChoices,
    ChangeActionChoices,
    ItemInstanceStatus,
)
from dcrm.utilities.serialization import serialize_object

from .actions import registry


class BatchInventoryAction:
    model = None
    form_class = None
    template_name = None
    detail_fields = []
    action_name = ""
    next_url_name = "item_instance_list"

    def __init__(self, request, instances) -> None:
        self.request = request
        self.user = request.user
        self.instances = instances.filter(
            data_center=self.user.data_center, status=self.get_status_filter()
        )
        self.action = self.get_action()

    def get_action(self) -> dict:
        action = registry.get_action(self.model, self.action_name)
        return action

    def get_status_filter(self) -> Literal[ItemInstanceStatus.IN_STOCK]:
        # 默认只处理在库物品
        from dcrm.models.choices import ItemInstanceStatus

        return ItemInstanceStatus.IN_STOCK

    def get_initial(self) -> list[dict[str, Any]]:
        # 可被子类重写
        return [
            {
                "item_instance": obj,
                "quantity": obj.quantity if obj.quantity == 1 else None,
                "reason": "",
            }
            for obj in self.instances
        ]

    def get_formset(self, initial=None, data=None) -> Any:
        FormSet = modelformset_factory(
            self.model,
            form=self.form_class,
            extra=self.instances.count(),
            can_delete=True,
        )
        return FormSet(
            data or None,
            initial=initial,
            form_kwargs={"request": self.request, "is_initial": not data},
            queryset=self.model.objects.none(),
        )

    def handle_action(self, form) -> Any:
        """子类实现具体业务逻辑"""
        raise NotImplementedError

    def get_context(self, formset) -> dict[str, Any]:

        return {
            "action": self.get_action(),
            "formset": formset,
            "detail_fields": self.detail_fields,
            "next_url": reverse(self.next_url_name),
        }

    def __call__(self, **kwargs) -> HttpResponseClientRedirect | Any | TemplateResponse:
        if not self.instances.exists():
            messages.error(self.request, "请选择要操作的库存物品")
            return HttpResponseClientRedirect(reverse(self.next_url_name))

        formset = self.get_formset(initial=self.get_initial())
        handle_verify = all(
            [
                self.request.POST.get("action") == self.action_name,
                self.request.POST.get("apply") == "true",
            ]
        )
        if handle_verify:
            formset = self.get_formset(data=self.request.POST)
            if formset.is_valid():
                logs = []
                for form in formset:
                    if not (
                        form.is_valid()
                        and form.cleaned_data
                        and not form.cleaned_data.get("DELETE", False)
                    ):
                        continue
                    log = self.handle_action(form)
                    if log:
                        logs.append(log)
                if logs:
                    LogEntry.objects.bulk_create(logs)
                formset.save()
                messages.success(self.request, f"批量{self.action.get('name')}成功")
                return reverse(self.next_url_name)
            else:
                messages.error(
                    self.request, f"批量{self.action.get('name')}失败，请检查表单"
                )
        return TemplateResponse(
            self.request, self.template_name, self.get_context(formset)
        )


@registry.register(
    name=_("出库"),
    models=(ItemInstance, ItemInstanceHistory),
    permissions=("add", "change"),
    description=_("出库选中的库存物品"),
    color=ActionColorChoices.DEFAULT,
    icon="fa fa-sign-out",
    order=100,
    is_htmx=True,
)
def batch_stock_out(
    request, instances, **kwargs
) -> HttpResponseClientRedirect | Any | TemplateResponse:
    _action_name = sys._getframe().f_code.co_name

    class BatchStockOut(BatchInventoryAction):
        model = ItemInstanceHistory
        form_class = ItemInstanceHistoryStockOutForm
        template_name = "inventory/batch_stock_out.html"
        detail_fields = [
            "code",
            "tenant",
            "item",
            "identifier",
            "warehouse",
            "quantity",
        ]
        action_name = _action_name

        def handle_action(self, form) -> LogEntry:
            item = form.cleaned_data["item_instance"]
            quantity = form.cleaned_data["quantity"]
            if item.quantity == 1:
                status = ItemInstanceStatus.USED
                quantity = 1
            else:
                status = item.status
                quantity = item.quantity - quantity
            prechange_data = serialize_object(item)
            item.status = status
            item.quantity = quantity
            item.save()
            extra_data = {
                "ipaddr": self.request.ipaddr,
                "user_agent": self.request.META.get("HTTP_USER_AGENT"),
            }
            return LogEntry(
                created_by=self.request.user,
                created_at=item.updated_at,
                data_center=item.data_center,
                action=ChangeActionChoices.UPDATE,
                action_type=self.action_name,
                object_repr=item,
                message=f"出库: ({str(item)})",
                timestamp=str(int(timezone.now().timestamp() * 1000)),
                prechange_data=prechange_data,
                postchange_data=serialize_object(item),
                extra_data=extra_data,
            )

    return BatchStockOut(request, instances)()


@registry.register(
    name=_("借出"),
    models=(ItemInstance, ItemInstanceHistory),
    permissions=("add", "change"),
    description=_("借出选中的库存物品"),
    color=ActionColorChoices.DEFAULT,
    icon="fa fa-sign-in",
    order=100,
    is_htmx=True,
)
def batch_borrow(
    request, instances, **kwargs
) -> HttpResponseClientRedirect | Any | TemplateResponse:
    """物品借出
    """
    _action_name = sys._getframe().f_code.co_name
    extra_data = {
        "ipaddr": request.ipaddr,
        "user_agent": request.META.get("HTTP_USER_AGENT"),
    }

    class BatchStockOut(BatchInventoryAction):
        model = ItemInstanceHistory
        form_class = ItemInstanceHistoryStockOutForm
        template_name = "inventory/batch_stock_out.html"
        detail_fields = [
            "code",
            "tenant",
            "item",
            "identifier",
            "warehouse",
            "quantity",
        ]
        action_name = _action_name

        def handle_action(self, form) -> LogEntry:
            item = form.cleaned_data["item_instance"]
            _quantity = form.cleaned_data["quantity"]
            if item.quantity == 1:
                status = ItemInstanceStatus.BORROWING
                quantity = 1
            else:
                status = item.status
                quantity = item.quantity - _quantity
            prechange_data = serialize_object(item)
            item.status = status
            item.quantity = quantity
            item.save()
            # TODO:根据iteminstance创建新实例，数量指向借出的数量，parent指向操作的物品实例
            rules = CodingRule.objects.get_for_model(
                ItemInstance, self.request.user.data_center
            )
            rule = rules.filter(to_field="code").first()
            codes = rule.get_available_codes(limit=1)

            new_item = ItemInstance(
                code=codes[0],
                parent=item,
                status=ItemInstanceStatus.BORROWING,
                quantity=_quantity,
                history_count=0,
                created_by=self.request.user,
                data_center=self.request.user.data_center,
            )
            new_item.save()

            return LogEntry(
                created_by=self.request.user,
                created_at=item.updated_at,
                data_center=item.data_center,
                action=ChangeActionChoices.UPDATE,
                action_type=self.action_name,
                object_repr=item,
                message=f"借出: ({str(item)} [{_quantity}])",
                timestamp=str(int(timezone.now().timestamp() * 1000)),
                prechange_data=prechange_data,
                postchange_data=serialize_object(item),
                extra_data=extra_data,
            )

    return BatchStockOut(request, instances)()
