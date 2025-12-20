from django import forms
from django.utils.translation import gettext_lazy as _

from dcrm.models import Comment


class CommentForm(forms.ModelForm):
    """评论表单"""

    class Meta:
        model = Comment
        fields = ["content"]
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": _("在此添加评论..."),
                    "required": True,
                }
            )
        }
        labels = {"content": _("评论内容")}
