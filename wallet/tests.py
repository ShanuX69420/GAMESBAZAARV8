from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.models import UserRole

from .admin import DepositTicketAdmin, WithdrawalRequestAdmin
from .models import (
    DepositTicket,
    DepositTicketStatus,
    WalletAccount,
    WalletLedgerEntry,
    WalletLedgerType,
    WithdrawalRequest,
    WithdrawalRequestStatus,
)
from .services import get_or_create_wallet, reserve_withdrawal

User = get_user_model()


class WalletFlowTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(
            email="buyer-wallet@example.com",
            password="StrongPass123!",
            role=UserRole.BUYER,
        )
        self.seller = User.objects.create_user(
            email="seller-wallet@example.com",
            password="StrongPass123!",
            role=UserRole.SELLER,
        )
        self.admin_user = User.objects.create_superuser(
            email="wallet-admin@example.com",
            password="StrongPass123!",
        )

    def _build_admin_action_request(self, path, data=None):
        request = RequestFactory().post(path, data=data or {})
        request.user = self.admin_user
        session_middleware = SessionMiddleware(lambda req: None)
        session_middleware.process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def test_wallet_created_automatically_for_new_user(self):
        self.assertTrue(WalletAccount.objects.filter(user=self.buyer).exists())
        self.assertTrue(WalletAccount.objects.filter(user=self.seller).exists())

    def test_deposit_approval_action_credits_wallet(self):
        ticket = DepositTicket.objects.create(
            user=self.buyer,
            amount=Decimal("1500.00"),
            payment_method="bank_transfer",
            payment_reference="TRX123",
        )
        request = self._build_admin_action_request("/admin/wallet/depositticket/")

        admin_model = DepositTicketAdmin(DepositTicket, AdminSite())
        admin_model.approve_selected(request, DepositTicket.objects.filter(pk=ticket.pk))

        ticket.refresh_from_db()
        wallet = WalletAccount.objects.get(user=self.buyer)
        self.assertEqual(ticket.status, DepositTicketStatus.APPROVED)
        self.assertEqual(wallet.available_balance, Decimal("1500.00"))
        self.assertEqual(wallet.held_balance, Decimal("0.00"))
        self.assertTrue(
            WalletLedgerEntry.objects.filter(
                wallet=wallet,
                entry_type=WalletLedgerType.DEPOSIT_CREDIT,
                reference_type="deposit_ticket",
                reference_id=str(ticket.pk),
            ).exists()
        )

    def test_seller_can_create_withdrawal_request_and_funds_are_reserved(self):
        wallet = get_or_create_wallet(self.seller)
        wallet.available_balance = Decimal("2500.00")
        wallet.save(update_fields=["available_balance", "updated_at"])
        self.client.force_login(self.seller)

        response = self.client.post(
            reverse("wallet:withdrawal_create"),
            {
                "amount": "800.00",
                "payout_method": "bank_transfer",
                "account_title": "Ali Raza",
                "account_number": "PK00TEST123",
                "bank_name": "Meezan Bank",
            },
        )

        self.assertRedirects(response, reverse("wallet:dashboard"))
        wallet.refresh_from_db()
        request_obj = WithdrawalRequest.objects.get(user=self.seller)
        self.assertEqual(request_obj.status, WithdrawalRequestStatus.PENDING)
        self.assertEqual(wallet.available_balance, Decimal("1700.00"))
        self.assertEqual(wallet.held_balance, Decimal("800.00"))
        self.assertTrue(
            WalletLedgerEntry.objects.filter(
                wallet=wallet,
                entry_type=WalletLedgerType.WITHDRAWAL_HOLD,
                reference_type="withdrawal_request",
                reference_id=str(request_obj.pk),
            ).exists()
        )

    def test_buyer_cannot_access_withdrawal_request_page(self):
        self.client.force_login(self.buyer)

        response = self.client.get(reverse("wallet:withdrawal_create"))

        self.assertRedirects(response, reverse("wallet:dashboard"))

    def test_reject_withdrawal_action_returns_funds(self):
        wallet = get_or_create_wallet(self.seller)
        wallet.available_balance = Decimal("900.00")
        wallet.save(update_fields=["available_balance", "updated_at"])
        request_obj = reserve_withdrawal(
            user=self.seller,
            amount=Decimal("400.00"),
            payout_method="bank_transfer",
            account_title="Ali Raza",
            account_number="PK00TEST999",
            bank_name="UBL",
        )
        request = self._build_admin_action_request("/admin/wallet/withdrawalrequest/")

        admin_model = WithdrawalRequestAdmin(WithdrawalRequest, AdminSite())
        admin_model.reject_selected(request, WithdrawalRequest.objects.filter(pk=request_obj.pk))

        request_obj.refresh_from_db()
        wallet.refresh_from_db()
        self.assertEqual(request_obj.status, WithdrawalRequestStatus.REJECTED)
        self.assertEqual(wallet.available_balance, Decimal("900.00"))
        self.assertEqual(wallet.held_balance, Decimal("0.00"))
        self.assertTrue(
            WalletLedgerEntry.objects.filter(
                wallet=wallet,
                entry_type=WalletLedgerType.WITHDRAWAL_RELEASE,
                reference_id=str(request_obj.pk),
            ).exists()
        )

    def test_pay_withdrawal_action_debits_held_balance(self):
        wallet = get_or_create_wallet(self.seller)
        wallet.available_balance = Decimal("1100.00")
        wallet.save(update_fields=["available_balance", "updated_at"])
        request_obj = reserve_withdrawal(
            user=self.seller,
            amount=Decimal("500.00"),
            payout_method="jazzcash",
            account_title="Ali Raza",
            account_number="03001234567",
        )
        request = self._build_admin_action_request("/admin/wallet/withdrawalrequest/")

        admin_model = WithdrawalRequestAdmin(WithdrawalRequest, AdminSite())
        admin_model.pay_selected(request, WithdrawalRequest.objects.filter(pk=request_obj.pk))

        request_obj.refresh_from_db()
        wallet.refresh_from_db()
        self.assertEqual(request_obj.status, WithdrawalRequestStatus.PAID)
        self.assertEqual(wallet.available_balance, Decimal("600.00"))
        self.assertEqual(wallet.held_balance, Decimal("0.00"))
        self.assertTrue(
            WalletLedgerEntry.objects.filter(
                wallet=wallet,
                entry_type=WalletLedgerType.WITHDRAWAL_PAID,
                reference_id=str(request_obj.pk),
            ).exists()
        )

    def test_deposit_ticket_can_be_approved_from_change_page_button(self):
        ticket = DepositTicket.objects.create(
            user=self.buyer,
            amount=Decimal("700.00"),
            payment_method="jazzcash",
            payment_reference="03001231234",
        )
        request = self._build_admin_action_request(
            f"/admin/wallet/depositticket/{ticket.pk}/change/",
            data={"_approve_ticket": "1"},
        )
        admin_model = DepositTicketAdmin(DepositTicket, AdminSite())

        admin_model.response_change(request, ticket)

        ticket.refresh_from_db()
        wallet = WalletAccount.objects.get(user=self.buyer)
        self.assertEqual(ticket.status, DepositTicketStatus.APPROVED)
        self.assertEqual(wallet.available_balance, Decimal("700.00"))

    def test_withdrawal_request_can_be_paid_from_change_page_button(self):
        wallet = get_or_create_wallet(self.seller)
        wallet.available_balance = Decimal("900.00")
        wallet.save(update_fields=["available_balance", "updated_at"])
        request_obj = reserve_withdrawal(
            user=self.seller,
            amount=Decimal("300.00"),
            payout_method="bank_transfer",
            account_title="Ali Raza",
            account_number="PK00TEST777",
            bank_name="HBL",
        )
        request = self._build_admin_action_request(
            f"/admin/wallet/withdrawalrequest/{request_obj.pk}/change/",
            data={"_pay_request": "1"},
        )
        admin_model = WithdrawalRequestAdmin(WithdrawalRequest, AdminSite())

        admin_model.response_change(request, request_obj)

        request_obj.refresh_from_db()
        wallet.refresh_from_db()
        self.assertEqual(request_obj.status, WithdrawalRequestStatus.PAID)
        self.assertEqual(wallet.held_balance, Decimal("0.00"))

    def test_wallet_dashboard_loads_for_authenticated_user(self):
        self.client.force_login(self.buyer)

        response = self.client.get(reverse("wallet:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Wallet Dashboard")
        self.assertNotContains(response, "Withdrawal Requests")

    def test_deposit_ticket_creation_requires_receipt_upload(self):
        self.client.force_login(self.buyer)

        no_receipt_response = self.client.post(
            reverse("wallet:deposit_create"),
            {
                "amount": "1200.00",
                "payment_method": "easypaisa",
                "payment_reference": "03450001122",
                "transaction_id": "TRX-001",
            },
        )
        self.assertEqual(no_receipt_response.status_code, 200)
        self.assertContains(no_receipt_response, "This field is required")

        receipt = SimpleUploadedFile("receipt.jpg", b"fake-image-bytes", content_type="image/jpeg")
        with_receipt_response = self.client.post(
            reverse("wallet:deposit_create"),
            {
                "amount": "1200.00",
                "payment_method": "easypaisa",
                "payment_reference": "03450001122",
                "transaction_id": "TRX-001",
                "receipt_file": receipt,
            },
        )
        self.assertRedirects(with_receipt_response, reverse("wallet:dashboard"))
        self.assertTrue(DepositTicket.objects.filter(user=self.buyer).exists())

    def test_bank_transfer_withdrawal_requires_bank_name(self):
        wallet = get_or_create_wallet(self.seller)
        wallet.available_balance = Decimal("1000.00")
        wallet.save(update_fields=["available_balance", "updated_at"])
        self.client.force_login(self.seller)

        response = self.client.post(
            reverse("wallet:withdrawal_create"),
            {
                "amount": "200.00",
                "payout_method": "bank_transfer",
                "account_title": "Ali Raza",
                "account_number": "PK00TEST111",
                "bank_name": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bank name is required for bank transfer withdrawals")
