from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import (
    DepositTicket,
    DepositTicketStatus,
    WalletAccount,
    WalletLedgerDirection,
    WalletLedgerEntry,
    WalletLedgerType,
    WithdrawalPaymentMethod,
    WithdrawalRequest,
    WithdrawalRequestStatus,
)


class WalletError(ValueError):
    pass


def get_or_create_wallet(user):
    wallet, _ = WalletAccount.objects.get_or_create(user=user)
    return wallet


def append_wallet_entry(
    wallet,
    *,
    entry_type,
    direction,
    amount,
    available_delta=Decimal("0"),
    held_delta=Decimal("0"),
    note="",
    reference_type="",
    reference_id="",
    created_by=None,
):
    wallet.available_balance = wallet.available_balance + available_delta
    wallet.held_balance = wallet.held_balance + held_delta

    if wallet.available_balance < 0 or wallet.held_balance < 0:
        raise WalletError("Wallet balance cannot become negative.")

    wallet.save(update_fields=["available_balance", "held_balance", "updated_at"])
    return WalletLedgerEntry.objects.create(
        wallet=wallet,
        entry_type=entry_type,
        direction=direction,
        amount=amount,
        available_delta=available_delta,
        held_delta=held_delta,
        available_balance_after=wallet.available_balance,
        held_balance_after=wallet.held_balance,
        note=note,
        reference_type=reference_type,
        reference_id=reference_id,
        created_by=created_by,
    )


def _append_ledger_entry(*args, **kwargs):
    return append_wallet_entry(*args, **kwargs)


def approve_deposit(*, ticket, reviewer, note=""):
    with transaction.atomic():
        ticket = DepositTicket.objects.select_for_update().select_related("user").get(pk=ticket.pk)
        if ticket.status != DepositTicketStatus.PENDING:
            raise WalletError("Only pending deposits can be approved.")

        wallet = get_or_create_wallet(ticket.user)
        wallet = WalletAccount.objects.select_for_update().get(pk=wallet.pk)

        append_wallet_entry(
            wallet,
            entry_type=WalletLedgerType.DEPOSIT_CREDIT,
            direction=WalletLedgerDirection.CREDIT,
            amount=ticket.amount,
            available_delta=ticket.amount,
            note=note or "Deposit approved and credited.",
            reference_type="deposit_ticket",
            reference_id=str(ticket.pk),
            created_by=reviewer,
        )

        ticket.status = DepositTicketStatus.APPROVED
        ticket.admin_note = note
        ticket.reviewed_by = reviewer
        ticket.reviewed_at = timezone.now()
        ticket.credited_at = timezone.now()
        ticket.save(
            update_fields=[
                "status",
                "admin_note",
                "reviewed_by",
                "reviewed_at",
                "credited_at",
                "updated_at",
            ]
        )

        return ticket


def reject_deposit(*, ticket, reviewer, note=""):
    with transaction.atomic():
        ticket = DepositTicket.objects.select_for_update().get(pk=ticket.pk)
        if ticket.status != DepositTicketStatus.PENDING:
            raise WalletError("Only pending deposits can be rejected.")

        ticket.status = DepositTicketStatus.REJECTED
        ticket.admin_note = note
        ticket.reviewed_by = reviewer
        ticket.reviewed_at = timezone.now()
        ticket.save(
            update_fields=[
                "status",
                "admin_note",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )

        return ticket


def reserve_withdrawal(
    *,
    user,
    amount,
    payout_method,
    payout_details="",
    account_title="",
    account_number="",
    bank_name="",
):
    if amount <= 0:
        raise WalletError("Withdrawal amount must be greater than zero.")

    valid_methods = {value for value, _ in WithdrawalPaymentMethod.choices}
    if payout_method not in valid_methods:
        raise WalletError("Invalid payout method selected.")

    account_title = (account_title or "").strip()
    account_number = (account_number or "").strip()
    bank_name = (bank_name or "").strip()
    payout_details = (payout_details or "").strip()

    if payout_details:
        if not account_title:
            account_title = "Manual payout details"
        if not account_number:
            account_number = "See payout details"

    if not account_title:
        raise WalletError("Account title is required.")
    if not account_number:
        raise WalletError("Account number / wallet number / IBAN is required.")
    if payout_method == "bank_transfer" and not bank_name:
        raise WalletError("Bank name is required for bank transfer withdrawals.")

    if not payout_details:
        payout_details = f"{account_title} | {account_number}"
        if bank_name:
            payout_details = f"{payout_details} | {bank_name}"

    with transaction.atomic():
        wallet = get_or_create_wallet(user)
        wallet = WalletAccount.objects.select_for_update().get(pk=wallet.pk)

        if wallet.available_balance < amount:
            raise WalletError("Insufficient available balance.")

        request_obj = WithdrawalRequest.objects.create(
            user=user,
            amount=amount,
            payout_method=payout_method,
            account_title=account_title,
            account_number=account_number,
            bank_name=bank_name,
            payout_details=payout_details,
            status=WithdrawalRequestStatus.PENDING,
            reserved_at=timezone.now(),
        )

        append_wallet_entry(
            wallet,
            entry_type=WalletLedgerType.WITHDRAWAL_HOLD,
            direction=WalletLedgerDirection.TRANSFER,
            amount=amount,
            available_delta=-amount,
            held_delta=amount,
            note="Funds reserved for withdrawal request.",
            reference_type="withdrawal_request",
            reference_id=str(request_obj.pk),
            created_by=user,
        )

        return request_obj


def approve_withdrawal(*, request_obj, reviewer, note=""):
    with transaction.atomic():
        request_obj = WithdrawalRequest.objects.select_for_update().get(pk=request_obj.pk)
        if request_obj.status != WithdrawalRequestStatus.PENDING:
            raise WalletError("Only pending withdrawals can be approved.")

        request_obj.status = WithdrawalRequestStatus.APPROVED
        request_obj.admin_note = note
        request_obj.reviewed_by = reviewer
        request_obj.reviewed_at = timezone.now()
        request_obj.save(
            update_fields=[
                "status",
                "admin_note",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )
        return request_obj


def reject_withdrawal(*, request_obj, reviewer, note=""):
    with transaction.atomic():
        request_obj = WithdrawalRequest.objects.select_for_update().select_related("user").get(pk=request_obj.pk)
        if request_obj.status not in {WithdrawalRequestStatus.PENDING, WithdrawalRequestStatus.APPROVED}:
            raise WalletError("Only pending or approved withdrawals can be rejected.")

        wallet = get_or_create_wallet(request_obj.user)
        wallet = WalletAccount.objects.select_for_update().get(pk=wallet.pk)
        if wallet.held_balance < request_obj.amount:
            raise WalletError("Held balance is insufficient to reject this withdrawal.")

        append_wallet_entry(
            wallet,
            entry_type=WalletLedgerType.WITHDRAWAL_RELEASE,
            direction=WalletLedgerDirection.TRANSFER,
            amount=request_obj.amount,
            available_delta=request_obj.amount,
            held_delta=-request_obj.amount,
            note=note or "Withdrawal request rejected and funds returned.",
            reference_type="withdrawal_request",
            reference_id=str(request_obj.pk),
            created_by=reviewer,
        )

        request_obj.status = WithdrawalRequestStatus.REJECTED
        request_obj.admin_note = note
        request_obj.reviewed_by = reviewer
        request_obj.reviewed_at = timezone.now()
        request_obj.save(
            update_fields=[
                "status",
                "admin_note",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            ]
        )
        return request_obj


def pay_withdrawal(*, request_obj, reviewer, note="", payout_reference=""):
    with transaction.atomic():
        request_obj = WithdrawalRequest.objects.select_for_update().select_related("user").get(pk=request_obj.pk)
        if request_obj.status in {WithdrawalRequestStatus.REJECTED, WithdrawalRequestStatus.PAID}:
            raise WalletError("Only pending or approved withdrawals can be marked paid.")

        wallet = get_or_create_wallet(request_obj.user)
        wallet = WalletAccount.objects.select_for_update().get(pk=wallet.pk)
        if wallet.held_balance < request_obj.amount:
            raise WalletError("Held balance is insufficient to mark this withdrawal as paid.")

        append_wallet_entry(
            wallet,
            entry_type=WalletLedgerType.WITHDRAWAL_PAID,
            direction=WalletLedgerDirection.DEBIT,
            amount=request_obj.amount,
            held_delta=-request_obj.amount,
            note=note or "Withdrawal marked as paid by finance admin.",
            reference_type="withdrawal_request",
            reference_id=str(request_obj.pk),
            created_by=reviewer,
        )

        request_obj.status = WithdrawalRequestStatus.PAID
        request_obj.admin_note = note
        request_obj.payout_reference = payout_reference
        request_obj.reviewed_by = reviewer
        request_obj.reviewed_at = timezone.now()
        request_obj.paid_at = timezone.now()
        request_obj.save(
            update_fields=[
                "status",
                "admin_note",
                "payout_reference",
                "reviewed_by",
                "reviewed_at",
                "paid_at",
                "updated_at",
            ]
        )
        return request_obj
