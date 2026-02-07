from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView

from listings.models import Listing, ListingStatus
from wallet.services import WalletError, get_or_create_wallet

from .forms import DeliveryNoteForm, DisputeForm, OrderCheckoutForm
from .models import Order
from .services import (
    OrderError,
    confirm_order_delivery,
    create_order_from_listing,
    mark_order_delivered,
    open_dispute,
)


class OrderListView(LoginRequiredMixin, ListView):
    model = Order
    template_name = "orders/order_list.html"
    context_object_name = "orders"
    paginate_by = 20

    def get_queryset(self):
        return (
            Order.objects.select_related("buyer", "seller", "listing")
            .filter(Q(buyer=self.request.user) | Q(seller=self.request.user))
            .order_by("-created_at")
        )


class OrderDetailView(LoginRequiredMixin, DetailView):
    model = Order
    template_name = "orders/order_detail.html"
    context_object_name = "order"

    def get_queryset(self):
        return Order.objects.select_related("buyer", "seller", "listing").filter(
            Q(buyer=self.request.user) | Q(seller=self.request.user)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["delivery_form"] = DeliveryNoteForm()
        context["dispute_form"] = DisputeForm()
        return context


class OrderCreateView(LoginRequiredMixin, View):
    def post(self, request, listing_id):
        quantity = request.POST.get("quantity", "1")
        return redirect(f'{reverse("orders:checkout", kwargs={"listing_id": listing_id})}?quantity={quantity}')


class OrderCheckoutView(LoginRequiredMixin, View):
    template_name = "orders/order_checkout.html"

    def _build_preview(self, buyer, listing_id, quantity):
        listing = get_object_or_404(Listing.objects.select_related("seller"), pk=listing_id)
        if listing.status != ListingStatus.ACTIVE:
            raise OrderError("This listing is not available for purchase.")
        if listing.seller_id == buyer.id:
            raise OrderError("You cannot buy your own listing.")
        if quantity < 1:
            raise OrderError("Quantity must be at least 1.")
        if quantity > listing.stock:
            raise OrderError("Requested quantity is higher than listing stock.")

        total_amount = listing.price_pkr * quantity
        wallet = get_or_create_wallet(buyer)
        remaining_balance = wallet.available_balance - total_amount
        return {
            "listing": listing,
            "quantity": quantity,
            "unit_price": listing.price_pkr,
            "total_amount": total_amount,
            "wallet_balance": wallet.available_balance,
            "remaining_balance": remaining_balance,
            "has_sufficient_balance": remaining_balance >= Decimal("0.00"),
        }

    def get(self, request, listing_id):
        raw_quantity = request.GET.get("quantity", "1")
        try:
            quantity = int(raw_quantity)
        except (TypeError, ValueError):
            messages.error(request, "Please provide a valid quantity.")
            return redirect("listings:detail", pk=listing_id)

        try:
            preview = self._build_preview(request.user, listing_id, quantity)
        except OrderError as exc:
            messages.error(request, str(exc))
            return redirect("listings:detail", pk=listing_id)

        form = OrderCheckoutForm(initial={"quantity": quantity})
        return render(
            request,
            self.template_name,
            {
                "listing": preview["listing"],
                "preview": preview,
                "form": form,
            },
        )

    def post(self, request, listing_id):
        form = OrderCheckoutForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Please provide a valid quantity.")
            return redirect("listings:detail", pk=listing_id)

        quantity = form.cleaned_data["quantity"]
        try:
            preview = self._build_preview(request.user, listing_id, quantity)
            if not preview["has_sufficient_balance"]:
                raise WalletError("Insufficient wallet balance for this order.")

            order = create_order_from_listing(
                buyer=request.user,
                listing_id=listing_id,
                quantity=quantity,
            )
        except (OrderError, WalletError) as exc:
            messages.error(request, str(exc))
            return redirect("orders:checkout", listing_id=listing_id)

        messages.success(request, f"Order #{order.pk} placed successfully.")
        return redirect("orders:detail", pk=order.pk)


class MarkOrderDeliveredView(LoginRequiredMixin, View):
    def post(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)
        form = DeliveryNoteForm(request.POST)
        note = ""
        if form.is_valid():
            note = form.cleaned_data.get("delivery_note", "")

        try:
            mark_order_delivered(order=order, actor=request.user, note=note)
        except OrderError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Order #{order.pk} marked as delivered.")

        return redirect("orders:detail", pk=order.pk)


class ConfirmOrderDeliveryView(LoginRequiredMixin, View):
    def post(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)
        try:
            confirm_order_delivery(order=order, actor=request.user)
        except (OrderError, WalletError) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Order #{order.pk} has been confirmed and completed.")
        return redirect("orders:detail", pk=order.pk)


class OpenDisputeView(LoginRequiredMixin, View):
    def post(self, request, order_id):
        order = get_object_or_404(Order, pk=order_id)
        form = DisputeForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Please provide a valid dispute reason.")
            return redirect("orders:detail", pk=order.pk)

        try:
            open_dispute(
                order=order,
                actor=request.user,
                reason=form.cleaned_data["reason"],
                details=form.cleaned_data["details"],
            )
        except OrderError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Dispute opened for order #{order.pk}.")
        return redirect("orders:detail", pk=order.pk)
