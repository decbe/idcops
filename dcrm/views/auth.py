from django.contrib import messages
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetView,
)
from django.urls import reverse_lazy
from django.utils.translation import gettext as _


class CustomLoginView(LoginView):
    """自定义登录视图"""

    template_name = "auth/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        next_url = self.request.GET.get("next") or self.request.POST.get("next")
        if next_url:
            return next_url
        return reverse_lazy("index")

    def form_valid(self, form):
        messages.success(self.request, _("登录成功"))
        return super().form_valid(form)


class CustomLogoutView(LogoutView):
    """自定义注销视图"""

    http_method_names = ["get", "post", "options"]

    template_name = "auth/login.html"
    next_page = "login"

    def dispatch(self, request, *args, **kwargs):
        messages.info(request, _("已安全退出"))
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class CustomPasswordChangeView(PasswordChangeView):
    """自定义密码修改视图"""

    template_name = "auth/password_change.html"
    success_url = reverse_lazy("index")

    def form_valid(self, form):
        messages.success(self.request, _("密码修改成功"))
        return super().form_valid(form)


class CustomPasswordResetView(PasswordResetView):
    """自定义密码重置视图"""

    template_name = "auth/password_reset.html"
    email_template_name = "auth/password_reset_email.html"
    success_url = reverse_lazy("login")

    def form_valid(self, form):
        messages.info(self.request, _("密码重置邮件已发送"))
        return super().form_valid(form)


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    """自定义密码重置确认视图"""

    template_name = "auth/password_reset_confirm.html"
    success_url = reverse_lazy("login")

    def form_valid(self, form):
        messages.success(self.request, _("密码重置成功，请使用新密码登录"))
        return super().form_valid(form)
