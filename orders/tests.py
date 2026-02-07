from datetime import timedelta
from decimal import Decimal

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserRole
from listings.models import Listing, ListingCategory, ListingStatus
from wallet.models import WalletLedgerEntry, WalletLedgerType
from wallet.services import get_or_create_wallet

from .admin import DisputeAdmin
from .models import DisputeStatus, Order, OrderStatus
from .services import (
    create_order_from_listing,
    mark_order_delivered,
    open_dispute,
    resolve_dispute_buyer_refund,
)

User = get_user_model()


class OrderLifecycleTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(
            email="order-buyer@example.com",
            password="StrongPass123!",
            role=UserRole.BUYER,
        )
        self.other_buyer = User.objects.create_user(
            email="order-buyer2@example.com",
            password="StrongPass123!",
            role=UserRole.BUYER,
        )
        self.seller = User.objects.create_user(
            email="order-seller@example.com",
            password="StrongPass123!",
            role=UserRole.SELLER,
        )
        self.admin_user = User.objects.create_superuser(
            email="order-admin@example.com",
            password="StrongPass123!",
        )
        self.listing = Listing.objects.create(
            seller=self.seller,
            category=ListingCategory.ACCOUNT,
            game_title="Valorant",
            title="Diamond Account",
            description="Competitive account.",
            price_pkr=Decimal("1000.00"),
            stock=4,
            status=ListingStatus.ACTIVE,
        )
        self._set_wallet(self.buyer, Decimal("5000.00"))
        self._set_wallet(self.other_buyer, Decimal("5000.00"))

    def _set_wallet(self, user, available):
        wallet = get_or_create_wallet(user)
        wallet.available_balance = available
        wallet.held_balance = Decimal("0.00")
        wallet.save(update_fields=["available_balance", "held_balance", "updated_at"])
        return wallet

    def _build_admin_action_request(self, path, data=None):
        request = RequestFactory().post(path, data=data or {})
        request.user = self.admin_user
        session_middleware = SessionMiddleware(lambda req: None)
        session_middleware.process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def test_buyer_can_place_order_with_wallet_funds(self):
        self.client.force_login(self.buyer)
        create_response = self.client.post(
            reverse("orders:create", kwargs={"listing_id": self.listing.id}),
            {"quantity": 2},
        )
        checkout_url = f'{reverse("orders:checkout", kwargs={"listing_id": self.listing.id})}?quantity=2'
        self.assertRedirects(create_response, checkout_url, fetch_redirect_response=False)

        checkout_response = self.client.get(checkout_url)
        self.assertEqual(checkout_response.status_code, 200)
        self.assertContains(checkout_response, "Balance After Order")
        self.assertContains(checkout_response, "PKR 3000.00")

        response = self.client.post(
            reverse("orders:checkout", kwargs={"listing_id": self.listing.id}),
            {"quantity": 2},
        )

        order = Order.objects.get()
        self.assertRedirects(response, reverse("orders:detail", kwargs={"pk": order.pk}))

        buyer_wallet = get_or_create_wallet(self.buyer)
        seller_wallet = get_or_create_wallet(self.seller)
        self.listing.refresh_from_db()

        self.assertEqual(order.status, OrderStatus.PENDING_DELIVERY)
        self.assertEqual(order.total_amount, Decimal("2000.00"))
        self.assertEqual(order.platform_fee_amount, Decimal("100.00"))
        self.assertEqual(order.seller_net_amount, Decimal("1900.00"))
        self.assertEqual(buyer_wallet.available_balance, Decimal("3000.00"))
        self.assertEqual(seller_wallet.held_balance, Decimal("2000.00"))
        self.assertEqual(self.listing.stock, 2)
        self.assertTrue(
            WalletLedgerEntry.objects.filter(
                entry_type=WalletLedgerType.ORDER_PAYMENT,
                reference_type="order",
                reference_id=str(order.pk),
            ).exists()
        )
        self.assertTrue(
            WalletLedgerEntry.objects.filter(
                entry_type=WalletLedgerType.ORDER_SALE_HOLD,
                reference_type="order",
                reference_id=str(order.pk),
            ).exists()
        )

    def test_buyer_cannot_buy_own_listing(self):
        own_listing = Listing.objects.create(
            seller=self.buyer,
            category=ListingCategory.ITEM,
            game_title="PUBG",
            title="Crate Item Pack",
            description="Bundle",
            price_pkr=Decimal("500.00"),
            stock=1,
            status=ListingStatus.ACTIVE,
        )
        self.client.force_login(self.buyer)

        response = self.client.get(reverse("orders:checkout", kwargs={"listing_id": own_listing.id}))

        self.assertRedirects(response, reverse("listings:detail", kwargs={"pk": own_listing.id}))
        self.assertFalse(Order.objects.filter(listing=own_listing).exists())

    def test_seller_marks_delivered_and_buyer_confirms(self):
        order = create_order_from_listing(buyer=self.buyer, listing_id=self.listing.id)

        self.client.force_login(self.seller)
        deliver_response = self.client.post(
            reverse("orders:mark_delivered", kwargs={"order_id": order.id}),
            {"delivery_note": "Credentials sent in chat."},
        )
        self.assertRedirects(deliver_response, reverse("orders:detail", kwargs={"pk": order.id}))

        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.DELIVERED)
        self.assertIsNotNone(order.auto_release_at)

        self.client.force_login(self.buyer)
        confirm_response = self.client.post(reverse("orders:confirm", kwargs={"order_id": order.id}))
        self.assertRedirects(confirm_response, reverse("orders:detail", kwargs={"pk": order.id}))

        order.refresh_from_db()
        seller_wallet = get_or_create_wallet(self.seller)
        self.assertEqual(order.status, OrderStatus.COMPLETED)
        self.assertIsNotNone(order.buyer_confirmed_at)
        self.assertEqual(seller_wallet.available_balance, Decimal("950.00"))
        self.assertEqual(seller_wallet.held_balance, Decimal("0.00"))
        self.assertTrue(
            WalletLedgerEntry.objects.filter(
                entry_type=WalletLedgerType.ORDER_FEE_CAPTURE,
                reference_id=str(order.pk),
            ).exists()
        )

    def test_auto_release_command_completes_due_orders(self):
        order = create_order_from_listing(buyer=self.buyer, listing_id=self.listing.id)
        mark_order_delivered(order=order, actor=self.seller, note="Delivered")
        Order.objects.filter(pk=order.pk).update(auto_release_at=timezone.now() - timedelta(minutes=1))

        call_command("process_auto_releases")

        order.refresh_from_db()
        seller_wallet = get_or_create_wallet(self.seller)
        self.assertEqual(order.status, OrderStatus.COMPLETED)
        self.assertEqual(seller_wallet.available_balance, Decimal("950.00"))
        self.assertEqual(seller_wallet.held_balance, Decimal("0.00"))

    def test_dispute_blocks_auto_release(self):
        order = create_order_from_listing(buyer=self.buyer, listing_id=self.listing.id)
        mark_order_delivered(order=order, actor=self.seller, note="Delivered")
        open_dispute(order=order, actor=self.buyer, reason="Credentials invalid", details="Cannot login")
        Order.objects.filter(pk=order.pk).update(auto_release_at=timezone.now() - timedelta(minutes=1))

        call_command("process_auto_releases")

        order.refresh_from_db()
        seller_wallet = get_or_create_wallet(self.seller)
        self.assertEqual(order.status, OrderStatus.DISPUTED)
        self.assertEqual(seller_wallet.held_balance, Decimal("1000.00"))

    def test_resolve_dispute_buyer_refund_restores_buyer_funds(self):
        order = create_order_from_listing(buyer=self.buyer, listing_id=self.listing.id)
        mark_order_delivered(order=order, actor=self.seller, note="Delivered")
        dispute = open_dispute(order=order, actor=self.buyer, reason="Wrong item", details="")

        resolve_dispute_buyer_refund(dispute=dispute, reviewer=self.admin_user, note="Refund approved")

        order.refresh_from_db()
        dispute.refresh_from_db()
        buyer_wallet = get_or_create_wallet(self.buyer)
        seller_wallet = get_or_create_wallet(self.seller)
        self.assertEqual(order.status, OrderStatus.REFUNDED)
        self.assertEqual(dispute.status, DisputeStatus.RESOLVED)
        self.assertEqual(buyer_wallet.available_balance, Decimal("5000.00"))
        self.assertEqual(seller_wallet.held_balance, Decimal("0.00"))

    def test_order_list_shows_only_orders_for_logged_in_user(self):
        first_order = create_order_from_listing(buyer=self.buyer, listing_id=self.listing.id)
        second_order = create_order_from_listing(buyer=self.other_buyer, listing_id=self.listing.id)

        self.client.force_login(self.buyer)
        response = self.client.get(reverse("orders:list"))

        self.assertContains(response, reverse("orders:detail", kwargs={"pk": first_order.id}))
        self.assertNotContains(response, reverse("orders:detail", kwargs={"pk": second_order.id}))

    def test_dispute_can_be_resolved_from_change_page_button(self):
        order = create_order_from_listing(buyer=self.buyer, listing_id=self.listing.id)
        mark_order_delivered(order=order, actor=self.seller, note="Delivered")
        dispute = open_dispute(order=order, actor=self.buyer, reason="Wrong details", details="")
        request = self._build_admin_action_request(
            f"/admin/orders/dispute/{dispute.pk}/change/",
            data={"_resolve_buyer_refund": "1"},
        )
        admin_model = DisputeAdmin(dispute.__class__, AdminSite())

        admin_model.response_change(request, dispute)

        order.refresh_from_db()
        dispute.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.REFUNDED)
        self.assertEqual(dispute.status, DisputeStatus.RESOLVED)
