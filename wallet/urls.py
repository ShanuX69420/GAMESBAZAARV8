from django.urls import path

from .views import DepositTicketCreateView, WalletDashboardView, WithdrawalRequestCreateView

app_name = "wallet"

urlpatterns = [
    path("wallet/", WalletDashboardView.as_view(), name="dashboard"),
    path("wallet/deposits/new/", DepositTicketCreateView.as_view(), name="deposit_create"),
    path("wallet/withdrawals/new/", WithdrawalRequestCreateView.as_view(), name="withdrawal_create"),
]
