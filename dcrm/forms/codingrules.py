from django import forms
from django.contrib.contenttypes.models import ContentType
from django.db import models

from dcrm.models import CodingRule

from .base import BaseModelFormMixin


class CodingRuleBaseForm(BaseModelFormMixin):
    class Meta:
        model = CodingRule
        fields = [
            "content_type",
            "to_field",
            "name",
            "prefix",
            "start_at",
            "suffix",
            "height",
            "width",
            "description",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        initial = kwargs.get("initial", {})
        if self.instance.pk is None:
            content_type = initial.get("content_type", None)
            self.fields["content_type"].widget.attrs.update(
                {
                    "hx-get": "/coding-rules/add/",
                    "hx-trigger": "change",
                    "hx-target": "#edit-form",
                    "hx-swap": "innerHTML",
                    "hx-include": '[name="content_type"]',
                    "hx-push-url": "true",
                }
            )
        else:
            content_type = initial.get("content_type", self.instance.content_type.id)

        if content_type:
            model = ContentType.objects.get(pk=content_type).model_class()
            to_field_choices = []
            for field in model._meta.get_fields():
                can_be_build = all(
                    [
                        isinstance(field, (models.CharField, models.SlugField)),
                        not getattr(field, "choices", None),
                        not getattr(field, "flatchoices", None),
                    ]
                )
                if can_be_build:
                    to_field_choices.append((field.name, field.verbose_name))
            self.fields["to_field"] = forms.ChoiceField(
                choices=to_field_choices,
                widget=forms.Select(
                    attrs={
                        "class": "form-control select",
                        "style": "width: 100%",
                    }
                ),
                required=self.fields["to_field"].required,
                label=self.fields["to_field"].label,
                help_text=self.fields["to_field"].help_text,
            )
