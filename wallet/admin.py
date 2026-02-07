from django.contrib import admin
from django.contrib import messages as django_messages
from django.http import HttpResponseRedirect
from django.utils.html import format_html

from .models import DepositTicket, WalletAccount, WalletLedgerEntry, WithdrawalRequest
from .services import (
    WalletError,
    approve_deposit,
    approve_withdrawal,
    pay_withdrawal,
    reject_deposit,
    reject_withdrawal,
)


@admin.register(WalletAccount)
class WalletAccountAdmin(admin.ModelAdmin):
    list_display = ("user", "available_balance", "held_balance", "updated_at")
    search_fields = ("user__email",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(WalletLedgerEntry)
class WalletLedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "wallet",
        "entry_type",
        "direction",
        "amount",
        "available_balance_after",
        "held_balance_after",
        "created_at",
    )
    list_filter = ("entry_type", "direction", "created_at")
    search_fields = ("wallet__user__email", "reference_type", "reference_id")
    readonly_fields = [field.name for field in WalletLedgerEntry._meta.fields]


@admin.register(DepositTicket)
class DepositTicketAdmin(admin.ModelAdmin):
    change_form_template = "admin/wallet/depositticket/change_form.html"
    list_display = (
        "id",
        "user",
        "amount",
        "payment_method",
        "transaction_id",
        "status",
        "created_at",
        "reviewed_at",
    )
    list_filter = ("status", "payment_method", "created_at")
    search_fields = ("user__email", "payment_reference", "transaction_id")
    actions = ("approve_selected", "reject_selected")
    readonly_fields = (
        "receipt_preview",
        "status",
        "reviewed_by",
        "reviewed_at",
        "credited_at",
        "created_at",
        "updated_at",
    )
    fields = (
        "user",
        "amount",
        "payment_method",
        "payment_reference",
        "transaction_id",
        "receipt_file",
        "receipt_preview",
        "admin_note",
        "status",
        "reviewed_by",
        "reviewed_at",
        "credited_at",
        "created_at",
        "updated_at",
    )

    def receipt_preview(self, obj):
        if not obj or not obj.receipt_file:
            return "No receipt uploaded."
        return format_html(
            '<a href="{}" target="_blank">Open full receipt</a><br><img src="{}" alt="Receipt preview" style="margin-top:8px; max-width: 520px; max-height: 420px; border:1px solid #ddd; border-radius: 6px;">',
            obj.receipt_file.url,
            obj.receipt_file.url,
        )

    receipt_preview.short_description = "Receipt Preview"

    @admin.action(description="Approve selected deposit tickets")
    def approve_selected(self, request, queryset):
        approved_count = 0
        failed_count = 0
        for ticket in queryset:
            try:
                approve_deposit(
                    ticket=ticket,
                    reviewer=request.user,
                    note=ticket.admin_note or "Deposit approved by admin.",
                )
                approved_count += 1
            except WalletError:
                failed_count += 1

        if approved_count:
            self.message_user(request, f"Approved {approved_count} deposit ticket(s).", django_messages.SUCCESS)
        if failed_count:
            self.message_user(
                request,
                f"Skipped {failed_count} ticket(s) that were not pending.",
                django_messages.WARNING,
            )

    @admin.action(description="Reject selected deposit tickets")
    def reject_selected(self, request, queryset):
        rejected_count = 0
        failed_count = 0
        for ticket in queryset:
            try:
                reject_deposit(
                    ticket=ticket,
                    reviewer=request.user,
                    note=ticket.admin_note or "Deposit rejected by admin.",
                )
                rejected_count += 1
            except WalletError:
                failed_count += 1

        if rejected_count:
            self.message_user(request, f"Rejected {rejected_count} deposit ticket(s).", django_messages.SUCCESS)
        if failed_count:
            self.message_user(
                request,
                f"Skipped {failed_count} ticket(s) that were not pending.",
                django_messages.WARNING,
            )

    def response_change(self, request, obj):
        if "_approve_ticket" in request.POST:
            try:
                approve_deposit(
                    ticket=obj,
                    reviewer=request.user,
                    note=obj.admin_note or "Deposit approved by admin.",
                )
                self.message_user(request, "Deposit ticket approved.", django_messages.SUCCESS)
            except WalletError as exc:
                self.message_user(request, str(exc), django_messages.ERROR)
            return HttpResponseRedirect(request.path)

        if "_reject_ticket" in request.POST:
            try:
                reject_deposit(
                    ticket=obj,
                    reviewer=request.user,
                    note=obj.admin_note or "Deposit rejected by admin.",
                )
                self.message_user(request, "Deposit ticket rejected.", django_messages.SUCCESS)
            except WalletError as exc:
                self.message_user(request, str(exc), django_messages.ERROR)
            return HttpResponseRedirect(request.path)

        return super().response_change(request, obj)


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    change_form_template = "admin/wallet/withdrawalrequest/change_form.html"
    list_display = (
        "id",
        "user",
        "amount",
        "payout_method",
        "account_title",
        "account_number",
        "status",
        "created_at",
        "reviewed_at",
    )
    list_filter = ("status", "payout_method", "created_at")
    search_fields = ("user__email", "payout_reference", "account_title", "account_number", "bank_name")
    actions = ("approve_selected", "pay_selected", "reject_selected")
    readonly_fields = (
        "status",
        "reviewed_by",
        "reviewed_at",
        "reserved_at",
        "paid_at",
        "created_at",
        "updated_at",
    )

    @admin.action(description="Approve selected withdrawal requests")
    def approve_selected(self, request, queryset):
        approved_count = 0
        failed_count = 0
        for request_obj in queryset:
            try:
                approve_withdrawal(
                    request_obj=request_obj,
                    reviewer=request.user,
                    note=request_obj.admin_note or "Withdrawal approved by admin.",
                )
                approved_count += 1
            except WalletError:
                failed_count += 1

        if approved_count:
            self.message_user(request, f"Approved {approved_count} withdrawal request(s).", django_messages.SUCCESS)
        if failed_count:
            self.message_user(
                request,
                f"Skipped {failed_count} withdrawal request(s) that were not pending.",
                django_messages.WARNING,
            )

    @admin.action(description="Mark selected withdrawals as paid")
    def pay_selected(self, request, queryset):
        paid_count = 0
        failed_count = 0
        for request_obj in queryset:
            try:
                pay_withdrawal(
                    request_obj=request_obj,
                    reviewer=request.user,
                    note=request_obj.admin_note or "Withdrawal payout completed.",
                    payout_reference=request_obj.payout_reference,
                )
                paid_count += 1
            except WalletError:
                failed_count += 1

        if paid_count:
            self.message_user(request, f"Marked {paid_count} withdrawal request(s) as paid.", django_messages.SUCCESS)
        if failed_count:
            self.message_user(
                request,
                f"Skipped {failed_count} withdrawal request(s) that were already paid/rejected.",
                django_messages.WARNING,
            )

    def response_change(self, request, obj):
        if "_approve_request" in request.POST:
            try:
                approve_withdrawal(
                    request_obj=obj,
                    reviewer=request.user,
                    note=obj.admin_note or "Withdrawal approved by admin.",
                )
                self.message_user(request, "Withdrawal request approved.", django_messages.SUCCESS)
            except WalletError as exc:
                self.message_user(request, str(exc), django_messages.ERROR)
            return HttpResponseRedirect(request.path)

        if "_pay_request" in request.POST:
            try:
                pay_withdrawal(
                    request_obj=obj,
                    reviewer=request.user,
                    note=obj.admin_note or "Withdrawal payout completed.",
                    payout_reference=obj.payout_reference,
                )
                self.message_user(request, "Withdrawal request marked as paid.", django_messages.SUCCESS)
            except WalletError as exc:
                self.message_user(request, str(exc), django_messages.ERROR)
            return HttpResponseRedirect(request.path)

        if "_reject_request" in request.POST:
            try:
                reject_withdrawal(
                    request_obj=obj,
                    reviewer=request.user,
                    note=obj.admin_note or "Withdrawal rejected by admin.",
                )
                self.message_user(request, "Withdrawal request rejected.", django_messages.SUCCESS)
            except WalletError as exc:
                self.message_user(request, str(exc), django_messages.ERROR)
            return HttpResponseRedirect(request.path)

        return super().response_change(request, obj)

    @admin.action(description="Reject selected withdrawal requests")
    def reject_selected(self, request, queryset):
        rejected_count = 0
        failed_count = 0
        for request_obj in queryset:
            try:
                reject_withdrawal(
                    request_obj=request_obj,
                    reviewer=request.user,
                    note=request_obj.admin_note or "Withdrawal rejected by admin.",
                )
                rejected_count += 1
            except WalletError:
                failed_count += 1

        if rejected_count:
            self.message_user(request, f"Rejected {rejected_count} withdrawal request(s).", django_messages.SUCCESS)
        if failed_count:
            self.message_user(
                request,
                f"Skipped {failed_count} withdrawal request(s) that were already paid/rejected.",
                django_messages.WARNING,
            )
