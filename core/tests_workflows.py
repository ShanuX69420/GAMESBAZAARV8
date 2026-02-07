from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import SellerApplication, UserRole
from listings.models import Game, GameCategoryOption, Listing, ListingCategory
from orders.models import Order, OrderStatus
from orders.services import resolve_dispute_buyer_refund
from wallet.services import get_or_create_wallet

User = get_user_model()


class MarketplaceJourneyTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            email="journey-admin@example.com",
            password="StrongPass123!",
        )
        self.game = Game.objects.create(name="PUBG Mobile", is_active=True)
        self.currency_option = GameCategoryOption.objects.create(
            game=self.game,
            canonical_category=ListingCategory.CURRENCY,
            display_name="UC",
            is_active=True,
        )

    def _fund_wallet(self, user, amount):
        wallet = get_or_create_wallet(user)
        wallet.available_balance = amount
        wallet.held_balance = Decimal("0.00")
        wallet.save(update_fields=["available_balance", "held_balance", "updated_at"])
        return wallet

    def _onboard_seller_and_create_listing(self):
        seller = User.objects.create_user(
            email="journey-seller@example.com",
            password="StrongPass123!",
            role=UserRole.BUYER,
        )
        seller_client = Client()
        seller_client.force_login(seller)

        apply_response = seller_client.post(
            reverse("accounts:seller_application"),
            {
                "display_name": "Journey Seller",
                "experience": "Experienced marketplace seller.",
            },
        )
        self.assertRedirects(apply_response, reverse("accounts:seller_application"))

        application = SellerApplication.objects.get(user=seller)
        application.mark_approved(reviewer=self.admin_user, note="Approved for testing.")
        seller.refresh_from_db()
        self.assertEqual(seller.role, UserRole.SELLER)

        create_response = seller_client.post(
            reverse("listings:create"),
            {
                "game": self.game.id,
                "game_category": self.currency_option.id,
                "title": "PUBG UC Bundle",
                "description": "Fast delivery UC package.",
                "price_pkr": "500.00",
                "stock": 5,
            },
        )
        listing = Listing.objects.get(title="PUBG UC Bundle")
        self.assertRedirects(create_response, reverse("listings:detail", kwargs={"pk": listing.pk}))
        return seller, seller_client, listing

    def _create_buyer_with_balance(self, email, amount):
        buyer = User.objects.create_user(
            email=email,
            password="StrongPass123!",
            role=UserRole.BUYER,
        )
        self._fund_wallet(buyer, amount)
        buyer_client = Client()
        buyer_client.force_login(buyer)
        return buyer, buyer_client

    def test_full_journey_purchase_to_completion(self):
        seller, seller_client, listing = self._onboard_seller_and_create_listing()
        buyer, buyer_client = self._create_buyer_with_balance(
            email="journey-buyer@example.com",
            amount=Decimal("5000.00"),
        )

        start_checkout = buyer_client.post(
            reverse("orders:create", kwargs={"listing_id": listing.pk}),
            {"quantity": 2},
        )
        checkout_url = f'{reverse("orders:checkout", kwargs={"listing_id": listing.pk})}?quantity=2'
        self.assertRedirects(start_checkout, checkout_url, fetch_redirect_response=False)

        place_order = buyer_client.post(
            reverse("orders:checkout", kwargs={"listing_id": listing.pk}),
            {"quantity": 2},
        )
        order = Order.objects.get(buyer=buyer, seller=seller, listing=listing)
        self.assertRedirects(place_order, reverse("orders:detail", kwargs={"pk": order.pk}))
        self.assertEqual(order.status, OrderStatus.PENDING_DELIVERY)

        deliver_response = seller_client.post(
            reverse("orders:mark_delivered", kwargs={"order_id": order.pk}),
            {"delivery_note": "Sent credentials via secure chat."},
        )
        self.assertRedirects(deliver_response, reverse("orders:detail", kwargs={"pk": order.pk}))

        confirm_response = buyer_client.post(reverse("orders:confirm", kwargs={"order_id": order.pk}))
        self.assertRedirects(confirm_response, reverse("orders:detail", kwargs={"pk": order.pk}))

        order.refresh_from_db()
        buyer_wallet = get_or_create_wallet(buyer)
        seller_wallet = get_or_create_wallet(seller)
        listing.refresh_from_db()

        self.assertEqual(order.status, OrderStatus.COMPLETED)
        self.assertEqual(buyer_wallet.available_balance, Decimal("4000.00"))
        self.assertEqual(seller_wallet.available_balance, Decimal("950.00"))
        self.assertEqual(seller_wallet.held_balance, Decimal("0.00"))
        self.assertEqual(listing.stock, 3)

    def test_full_journey_dispute_to_refund(self):
        seller, seller_client, listing = self._onboard_seller_and_create_listing()
        buyer, buyer_client = self._create_buyer_with_balance(
            email="journey-refund-buyer@example.com",
            amount=Decimal("2000.00"),
        )

        buyer_client.post(
            reverse("orders:create", kwargs={"listing_id": listing.pk}),
            {"quantity": 1},
        )
        buyer_client.post(
            reverse("orders:checkout", kwargs={"listing_id": listing.pk}),
            {"quantity": 1},
        )
        order = Order.objects.get(buyer=buyer, seller=seller, listing=listing)

        seller_client.post(
            reverse("orders:mark_delivered", kwargs={"order_id": order.pk}),
            {"delivery_note": "Delivered details."},
        )
        dispute_response = buyer_client.post(
            reverse("orders:open_dispute", kwargs={"order_id": order.pk}),
            {"reason": "Wrong details", "details": "Credentials did not work."},
        )
        self.assertRedirects(dispute_response, reverse("orders:detail", kwargs={"pk": order.pk}))

        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.DISPUTED)
        resolve_dispute_buyer_refund(
            dispute=order.dispute,
            reviewer=self.admin_user,
            note="Refund approved after verification.",
        )

        order.refresh_from_db()
        buyer_wallet = get_or_create_wallet(buyer)
        seller_wallet = get_or_create_wallet(seller)

        self.assertEqual(order.status, OrderStatus.REFUNDED)
        self.assertEqual(buyer_wallet.available_balance, Decimal("2000.00"))
        self.assertEqual(seller_wallet.held_balance, Decimal("0.00"))
