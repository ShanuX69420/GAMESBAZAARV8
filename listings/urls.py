from django.urls import path

from .views import (
    ListingCreateView,
    ListingDeleteView,
    ListingDetailView,
    ListingListView,
    ListingRestockView,
    ListingStatusUpdateView,
    ListingUpdateView,
    SellerListingListView,
)

app_name = "listings"

urlpatterns = [
    path("listings/", ListingListView.as_view(), name="list"),
    path("listings/<int:pk>/", ListingDetailView.as_view(), name="detail"),
    path("sell/listings/<int:pk>/edit/", ListingUpdateView.as_view(), name="edit"),
    path("sell/listings/<int:listing_id>/restock/", ListingRestockView.as_view(), name="restock"),
    path("sell/listings/<int:listing_id>/delete/", ListingDeleteView.as_view(), name="delete"),
    path(
        "sell/listings/<int:listing_id>/pause/",
        ListingStatusUpdateView.as_view(),
        {"action": "pause"},
        name="pause",
    ),
    path(
        "sell/listings/<int:listing_id>/activate/",
        ListingStatusUpdateView.as_view(),
        {"action": "activate"},
        name="activate",
    ),
    path("sell/listings/new/", ListingCreateView.as_view(), name="create"),
    path("sell/listings/mine/", SellerListingListView.as_view(), name="mine"),
]
