from django.contrib import admin
from django.contrib import messages as django_messages
from django.http import HttpResponseRedirect

from .models import Dispute, Order
from .services import (
    OrderError,
    WalletError,
    refund_order,
    release_order_by_admin,
    resolve_dispute_buyer_refund,
    resolve_dispute_seller_win,
)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "buyer",
        "seller",
        "listing",
        "total_amount",
        "status",
        "auto_release_at",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("buyer__email", "seller__email", "listing__title")
    actions = ("release_selected_orders", "refund_selected_orders")

    @admin.action(description="Release selected orders to seller")
    def release_selected_orders(self, request, queryset):
        success = 0
        failed = 0
        for order in queryset:
            try:
                release_order_by_admin(
                    order=order,
                    reviewer=request.user,
                    note="Released by admin.",
                )
                success += 1
            except (OrderError, WalletError):
                failed += 1

        if success:
            self.message_user(request, f"Released {success} order(s).", django_messages.SUCCESS)
        if failed:
            self.message_user(
                request,
                f"Skipped {failed} order(s) that were not releasable.",
                django_messages.WARNING,
            )

    @admin.action(description="Refund selected orders to buyer")
    def refund_selected_orders(self, request, queryset):
        success = 0
        failed = 0
        for order in queryset:
            try:
                refund_order(
                    order=order,
                    actor=request.user,
                    resolution_note="Refunded by admin.",
                )
                success += 1
            except (OrderError, WalletError):
                failed += 1

        if success:
            self.message_user(request, f"Refunded {success} order(s).", django_messages.SUCCESS)
        if failed:
            self.message_user(
                request,
                f"Skipped {failed} order(s) that were not refundable.",
                django_messages.WARNING,
            )


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
    change_form_template = "admin/orders/dispute/change_form.html"
    list_display = ("id", "order", "opened_by", "reason", "status", "created_at", "resolved_at")
    list_filter = ("status", "created_at")
    search_fields = ("order__id", "opened_by__email", "reason")
    actions = ("resolve_seller_win", "resolve_buyer_refund")

    @admin.action(description="Resolve dispute with seller win")
    def resolve_seller_win(self, request, queryset):
        success = 0
        failed = 0
        for dispute in queryset:
            try:
                resolve_dispute_seller_win(
                    dispute=dispute,
                    reviewer=request.user,
                    note="Resolved in seller favor by admin.",
                )
                success += 1
            except (OrderError, WalletError):
                failed += 1

        if success:
            self.message_user(request, f"Resolved {success} dispute(s) for seller.", django_messages.SUCCESS)
        if failed:
            self.message_user(
                request,
                f"Skipped {failed} dispute(s) that were already resolved or invalid.",
                django_messages.WARNING,
            )

    def response_change(self, request, obj):
        if "_resolve_seller_win" in request.POST:
            try:
                resolve_dispute_seller_win(
                    dispute=obj,
                    reviewer=request.user,
                    note=obj.resolution_note or "Resolved in seller favor by admin.",
                )
                self.message_user(request, "Dispute resolved in seller favor.", django_messages.SUCCESS)
            except (OrderError, WalletError) as exc:
                self.message_user(request, str(exc), django_messages.ERROR)
            return HttpResponseRedirect(request.path)

        if "_resolve_buyer_refund" in request.POST:
            try:
                resolve_dispute_buyer_refund(
                    dispute=obj,
                    reviewer=request.user,
                    note=obj.resolution_note or "Resolved with buyer refund by admin.",
                )
                self.message_user(request, "Dispute resolved with buyer refund.", django_messages.SUCCESS)
            except (OrderError, WalletError) as exc:
                self.message_user(request, str(exc), django_messages.ERROR)
            return HttpResponseRedirect(request.path)

        return super().response_change(request, obj)

    @admin.action(description="Resolve dispute with buyer refund")
    def resolve_buyer_refund(self, request, queryset):
        success = 0
        failed = 0
        for dispute in queryset:
            try:
                resolve_dispute_buyer_refund(
                    dispute=dispute,
                    reviewer=request.user,
                    note="Resolved with buyer refund by admin.",
                )
                success += 1
            except (OrderError, WalletError):
                failed += 1

        if success:
            self.message_user(request, f"Resolved {success} dispute(s) with refunds.", django_messages.SUCCESS)
        if failed:
            self.message_user(
                request,
                f"Skipped {failed} dispute(s) that were already resolved or invalid.",
                django_messages.WARNING,
            )
