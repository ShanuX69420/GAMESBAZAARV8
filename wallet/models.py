from django.conf import settings
from django.db import models
from django.utils import timezone


class WalletLedgerDirection(models.TextChoices):
    CREDIT = "credit", "Credit"
    DEBIT = "debit", "Debit"
    TRANSFER = "transfer", "Transfer"


class WalletLedgerType(models.TextChoices):
    DEPOSIT_CREDIT = "deposit_credit", "Deposit Credit"
    WITHDRAWAL_HOLD = "withdrawal_hold", "Withdrawal Hold"
    WITHDRAWAL_RELEASE = "withdrawal_release", "Withdrawal Release"
    WITHDRAWAL_PAID = "withdrawal_paid", "Withdrawal Paid"
    ORDER_PAYMENT = "order_payment", "Order Payment"
    ORDER_SALE_HOLD = "order_sale_hold", "Order Sale Hold"
    ORDER_SALE_RELEASE = "order_sale_release", "Order Sale Release"
    ORDER_FEE_CAPTURE = "order_fee_capture", "Order Fee Capture"
    ORDER_REFUND = "order_refund", "Order Refund"
    ADJUSTMENT = "adjustment", "Adjustment"


class DepositTicketStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class DepositPaymentMethod(models.TextChoices):
    EASYPAISA = "easypaisa", "Easypaisa"
    JAZZCASH = "jazzcash", "JazzCash"
    BANK_TRANSFER = "bank_transfer", "Bank Transfer"
    SADAPAY = "sadapay", "SadaPay"
    NAYAPAY = "nayapay", "NayaPay"


class WithdrawalRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    PAID = "paid", "Paid"


class WithdrawalPaymentMethod(models.TextChoices):
    EASYPAISA = "easypaisa", "Easypaisa"
    JAZZCASH = "jazzcash", "JazzCash"
    BANK_TRANSFER = "bank_transfer", "Bank Transfer"
    SADAPAY = "sadapay", "SadaPay"
    NAYAPAY = "nayapay", "NayaPay"


class WalletAccount(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallet_account",
    )
    available_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    held_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self):
        return f"{self.user.email} wallet"


class WalletLedgerEntry(models.Model):
    wallet = models.ForeignKey(
        WalletAccount,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    entry_type = models.CharField(max_length=30, choices=WalletLedgerType.choices)
    direction = models.CharField(max_length=20, choices=WalletLedgerDirection.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    available_delta = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    held_delta = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    available_balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    held_balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    note = models.TextField(blank=True)
    reference_type = models.CharField(max_length=50, blank=True)
    reference_id = models.CharField(max_length=50, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="wallet_entries_created",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["entry_type", "created_at"]),
            models.Index(fields=["wallet", "created_at"]),
        ]

    def __str__(self):
        return f"{self.entry_type} ({self.amount})"


class DepositTicket(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="deposit_tickets",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_method = models.CharField(max_length=30, choices=DepositPaymentMethod.choices)
    payment_reference = models.CharField(max_length=80)
    transaction_id = models.CharField(max_length=100, blank=True)
    receipt_file = models.FileField(upload_to="deposit_receipts/", blank=True)
    status = models.CharField(
        max_length=20,
        choices=DepositTicketStatus.choices,
        default=DepositTicketStatus.PENDING,
    )
    admin_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_deposit_tickets",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    credited_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Deposit #{self.pk} - {self.user.email}"


class WithdrawalRequest(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="withdrawal_requests",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payout_method = models.CharField(max_length=30, choices=WithdrawalPaymentMethod.choices)
    account_title = models.CharField(max_length=120, default="")
    account_number = models.CharField(max_length=120, default="")
    bank_name = models.CharField(max_length=120, blank=True)
    payout_details = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=WithdrawalRequestStatus.choices,
        default=WithdrawalRequestStatus.PENDING,
    )
    admin_note = models.TextField(blank=True)
    payout_reference = models.CharField(max_length=100, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_withdrawal_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reserved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Withdrawal #{self.pk} - {self.user.email}"
