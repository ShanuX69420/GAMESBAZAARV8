from decimal import Decimal

from django import forms

from .models import DepositTicket, WithdrawalPaymentMethod, WithdrawalRequest


class DepositTicketForm(forms.ModelForm):
    receipt_file = forms.FileField(required=True)

    class Meta:
        model = DepositTicket
        fields = ("amount", "payment_method", "payment_reference", "transaction_id", "receipt_file")
        labels = {
            "payment_reference": "Sender number/account",
            "transaction_id": "TRX ID (optional)",
        }

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= Decimal("0"):
            raise forms.ValidationError("Amount must be greater than zero.")
        return amount


class WithdrawalRequestForm(forms.ModelForm):
    class Meta:
        model = WithdrawalRequest
        fields = ("amount", "payout_method", "account_title", "account_number", "bank_name")
        labels = {
            "account_title": "Account title",
            "account_number": "Account number / wallet number / IBAN",
            "bank_name": "Bank name (for bank transfer)",
        }

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= Decimal("0"):
            raise forms.ValidationError("Amount must be greater than zero.")
        return amount

    def clean(self):
        cleaned_data = super().clean()
        payout_method = cleaned_data.get("payout_method")
        bank_name = (cleaned_data.get("bank_name") or "").strip()

        if payout_method == WithdrawalPaymentMethod.BANK_TRANSFER and not bank_name:
            self.add_error("bank_name", "Bank name is required for bank transfer withdrawals.")
        if payout_method != WithdrawalPaymentMethod.BANK_TRANSFER:
            cleaned_data["bank_name"] = ""

        return cleaned_data
