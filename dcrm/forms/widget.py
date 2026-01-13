from django import forms


class DeviceModelSelect(forms.Select):
    """自定义的 Select widget"""

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        if value and hasattr(value, "instance"):
            option["attrs"].update(
                {
                    "data-model-height": value.instance.height,
                    "data-model-power-count": value.instance.power_port_count,
                    "data-model-pk": value.instance.type.pk,
                }
            )
        return option


class DeviceRackSelect(forms.Select):
    """自定义的 Select widget"""

    def create_option(
        self, name, value, label, selected, index, subindex=None, attrs=None
    ):
        option = super().create_option(
            name, value, label, selected, index, subindex, attrs
        )
        if value and hasattr(value, "instance"):
            option["attrs"].update(
                {
                    "data-rack-tenant": (
                        value.instance.tenant.name if value.instance.tenant else ""
                    ),
                    "data-rack-type": value.instance.rack_type,
                }
            )
        return option
