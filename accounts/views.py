from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.views.generic import TemplateView
from django.views import View

from .forms import EmailAuthenticationForm, SellerApplicationForm, UserRegistrationForm
from .models import SellerApplication, SellerApplicationStatus, UserRole


class RegisterView(View):
    form_class = UserRegistrationForm
    template_name = "registration/register.html"

    def get(self, request):
        form = self.form_class()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = self.form_class(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("core:home")
        return render(request, self.template_name, {"form": form})


class EmailLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["application"] = SellerApplication.objects.filter(user=self.request.user).first()
        return context


class SellerApplicationView(LoginRequiredMixin, View):
    template_name = "accounts/seller_application.html"
    form_class = SellerApplicationForm

    def get(self, request):
        if request.user.role == UserRole.SELLER:
            messages.info(request, "Your account is already a seller account.")
            return redirect("accounts:dashboard")

        application = SellerApplication.objects.filter(user=request.user).first()
        can_submit = (
            application is None or application.status == SellerApplicationStatus.REJECTED
        )
        form = self.form_class(instance=application) if can_submit else None
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "application": application,
                "can_submit": can_submit,
            },
        )

    def post(self, request):
        if request.user.role == UserRole.SELLER:
            messages.info(request, "Your account is already a seller account.")
            return redirect("accounts:dashboard")

        application = SellerApplication.objects.filter(user=request.user).first()
        can_submit = (
            application is None or application.status == SellerApplicationStatus.REJECTED
        )
        if not can_submit:
            messages.info(request, "Your seller application is already under review.")
            return redirect("accounts:seller_application")

        form = self.form_class(request.POST, instance=application)
        if form.is_valid():
            seller_application = form.save(commit=False)
            seller_application.user = request.user
            seller_application.status = SellerApplicationStatus.PENDING
            seller_application.admin_note = ""
            seller_application.reviewed_by = None
            seller_application.reviewed_at = None
            seller_application.save()
            messages.success(request, "Seller application submitted successfully.")
            return redirect("accounts:seller_application")

        return render(
            request,
            self.template_name,
            {
                "form": form,
                "application": application,
                "can_submit": True,
            },
        )
