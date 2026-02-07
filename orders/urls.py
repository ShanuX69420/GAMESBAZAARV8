from django.urls import path

from .views import (
    ConfirmOrderDeliveryView,
    MarkOrderDeliveredView,
    OpenDisputeView,
    OrderCheckoutView,
    OrderCreateView,
    OrderDetailView,
    OrderListView,
)

app_name = "orders"

urlpatterns = [
    path("orders/", OrderListView.as_view(), name="list"),
    path("orders/<int:pk>/", OrderDetailView.as_view(), name="detail"),
    path("orders/create/<int:listing_id>/", OrderCreateView.as_view(), name="create"),
    path("orders/checkout/<int:listing_id>/", OrderCheckoutView.as_view(), name="checkout"),
    path("orders/<int:order_id>/mark-delivered/", MarkOrderDeliveredView.as_view(), name="mark_delivered"),
    path("orders/<int:order_id>/confirm/", ConfirmOrderDeliveryView.as_view(), name="confirm"),
    path("orders/<int:order_id>/dispute/", OpenDisputeView.as_view(), name="open_dispute"),
]
