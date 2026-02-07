from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import TemplateView

from accounts.models import UserRole

from .forms import DepositTicketForm, WithdrawalRequestForm
from .models import DepositPaymentMethod, DepositTicket, WalletLedgerEntry, WithdrawalRequest
from .services import WalletError, get_or_create_wallet, reserve_withdrawal


class WalletDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "wallet/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wallet = get_or_create_wallet(self.request.user)
        context["wallet"] = wallet
        context["entries"] = WalletLedgerEntry.objects.filter(wallet=wallet)[:20]
        context["deposit_tickets"] = DepositTicket.objects.filter(user=self.request.user)[:5]
        context["withdrawal_requests"] = WithdrawalRequest.objects.filter(user=self.request.user)[:5]
        return context


class DepositTicketCreateView(LoginRequiredMixin, View):
    template_name = "wallet/deposit_form.html"
    form_class = DepositTicketForm
    payment_details = [
        {
            "method": DepositPaymentMethod.EASYPAISA,
            "title": "Easypaisa",
            "account_name": "GamesBazaar Pvt Ltd",
            "account_id": "03XX-XXXXXXX",
        },
        {
            "method": DepositPaymentMethod.JAZZCASH,
            "title": "JazzCash",
            "account_name": "GamesBazaar Pvt Ltd",
            "account_id": "03XX-XXXXXXX",
        },
        {
            "method": DepositPaymentMethod.BANK_TRANSFER,
            "title": "Bank Transfer",
            "account_name": "GamesBazaar Pvt Ltd",
            "account_id": "PK00-BAZAAR-0000-0000",
        },
        {
            "method": DepositPaymentMethod.SADAPAY,
            "title": "SadaPay",
            "account_name": "GamesBazaar Pvt Ltd",
            "account_id": "03XX-XXXXXXX",
        },
        {
            "method": DepositPaymentMethod.NAYAPAY,
            "title": "NayaPay",
            "account_name": "GamesBazaar Pvt Ltd",
            "account_id": "03XX-XXXXXXX",
        },
    ]

    def get(self, request):
        return render(
            request,
            self.template_name,
            {"form": self.form_class(), "payment_details": self.payment_details},
        )

    def post(self, request):
        form = self.form_class(request.POST, request.FILES)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.user = request.user
            ticket.save()
            messages.success(request, "Deposit request submitted. We will review it shortly.")
            return redirect("wallet:dashboard")
        return render(
            request,
            self.template_name,
            {"form": form, "payment_details": self.payment_details},
        )


class WithdrawalRequestCreateView(LoginRequiredMixin, View):
    template_name = "wallet/withdrawal_form.html"
    form_class = WithdrawalRequestForm

    def get(self, request):
        if request.user.role != UserRole.SELLER:
            messages.info(request, "Only approved sellers can request withdrawals.")
            return redirect("wallet:dashboard")
        return render(request, self.template_name, {"form": self.form_class()})

    def post(self, request):
        if request.user.role != UserRole.SELLER:
            messages.info(request, "Only approved sellers can request withdrawals.")
            return redirect("wallet:dashboard")

        form = self.form_class(request.POST)
        if form.is_valid():
            try:
                reserve_withdrawal(
                    user=request.user,
                    amount=form.cleaned_data["amount"],
                    payout_method=form.cleaned_data["payout_method"],
                    account_title=form.cleaned_data["account_title"],
                    account_number=form.cleaned_data["account_number"],
                    bank_name=form.cleaned_data.get("bank_name", ""),
                )
            except WalletError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, "Withdrawal request submitted and funds reserved.")
                return redirect("wallet:dashboard")

        return render(request, self.template_name, {"form": form})
