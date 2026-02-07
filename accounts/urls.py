from django.contrib.auth.views import LogoutView
from django.urls import path

from .views import DashboardView, EmailLoginView, RegisterView, SellerApplicationView

app_name = "accounts"

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", EmailLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("seller/apply/", SellerApplicationView.as_view(), name="seller_application"),
]
