from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserRole
from orders.models import Order

from .models import Game, GameCategoryOption, Listing, ListingCategory, ListingStatus

User = get_user_model()


class ListingViewsTests(TestCase):
    def setUp(self):
        self.seller = User.objects.create_user(
            email="seller1@example.com",
            password="StrongPass123!",
            role=UserRole.SELLER,
        )
        self.buyer = User.objects.create_user(
            email="buyer2@example.com",
            password="StrongPass123!",
            role=UserRole.BUYER,
        )
        self.valorant_game = Game.objects.create(name="Valorant", is_active=True)
        self.pubg_game = Game.objects.create(name="PUBG Mobile", is_active=True)
        self.valorant_account_category = GameCategoryOption.objects.create(
            game=self.valorant_game,
            canonical_category=ListingCategory.ACCOUNT,
            display_name="Account",
            is_active=True,
        )
        self.valorant_currency_category = GameCategoryOption.objects.create(
            game=self.valorant_game,
            canonical_category=ListingCategory.CURRENCY,
            display_name="VP Points",
            is_active=True,
        )
        self.pubg_currency_category = GameCategoryOption.objects.create(
            game=self.pubg_game,
            canonical_category=ListingCategory.CURRENCY,
            display_name="UC",
            is_active=True,
        )

    def test_seller_can_create_listing(self):
        self.client.force_login(self.seller)

        response = self.client.post(
            reverse("listings:create"),
            {
                "game": self.valorant_game.id,
                "game_category": self.valorant_account_category.id,
                "title": "Immortal Account",
                "description": "High rank account with skins.",
                "price_pkr": "12500.00",
                "stock": 1,
            },
        )

        listing = Listing.objects.get(title="Immortal Account")
        self.assertRedirects(response, reverse("listings:detail", kwargs={"pk": listing.pk}))
        self.assertEqual(listing.seller, self.seller)
        self.assertEqual(listing.status, ListingStatus.ACTIVE)
        self.assertEqual(listing.game, self.valorant_game)
        self.assertEqual(listing.game_category, self.valorant_account_category)
        self.assertEqual(listing.game_title, "Valorant")
        self.assertEqual(listing.category, ListingCategory.ACCOUNT)

    def test_seller_cannot_create_listing_with_mismatched_game_category(self):
        self.client.force_login(self.seller)

        response = self.client.post(
            reverse("listings:create"),
            {
                "game": self.valorant_game.id,
                "game_category": self.pubg_currency_category.id,
                "title": "Invalid Pair",
                "description": "Should fail",
                "price_pkr": "1000.00",
                "stock": 1,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.assertFalse(Listing.objects.filter(title="Invalid Pair").exists())

    def test_seller_cannot_create_listing_with_zero_stock(self):
        self.client.force_login(self.seller)

        response = self.client.post(
            reverse("listings:create"),
            {
                "game": self.valorant_game.id,
                "game_category": self.valorant_account_category.id,
                "title": "Zero Stock Listing",
                "description": "Should fail",
                "price_pkr": "1000.00",
                "stock": 0,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Stock must be at least 1")
        self.assertFalse(Listing.objects.filter(title="Zero Stock Listing").exists())

    def test_seller_cannot_create_listing_with_non_numeric_stock(self):
        self.client.force_login(self.seller)

        response = self.client.post(
            reverse("listings:create"),
            {
                "game": self.valorant_game.id,
                "game_category": self.valorant_account_category.id,
                "title": "Invalid Stock Listing",
                "description": "Should fail",
                "price_pkr": "1000.00",
                "stock": "abc",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a whole number")
        self.assertFalse(Listing.objects.filter(title="Invalid Stock Listing").exists())

    def test_buyer_cannot_access_listing_create(self):
        self.client.force_login(self.buyer)

        response = self.client.get(reverse("listings:create"))

        self.assertRedirects(response, reverse("accounts:seller_application"))

    def test_listing_catalog_filters_by_query_and_category(self):
        Listing.objects.create(
            seller=self.seller,
            category=ListingCategory.GIFT_CARD,
            game_title="Steam",
            title="Steam PK Gift Card",
            description="Redeemable gift card.",
            price_pkr="5000.00",
            stock=2,
            status=ListingStatus.ACTIVE,
        )
        Listing.objects.create(
            seller=self.seller,
            game=self.valorant_game,
            game_category=self.valorant_account_category,
            category=ListingCategory.ACCOUNT,
            game_title="Valorant",
            title="Valorant Account",
            description="Ranked account.",
            price_pkr="8000.00",
            stock=1,
            status=ListingStatus.ACTIVE,
        )
        Listing.objects.create(
            seller=self.seller,
            category=ListingCategory.GIFT_CARD,
            game_title="PlayStation",
            title="PSN Gift Card",
            description="Paused listing should not show.",
            price_pkr="6000.00",
            stock=1,
            status=ListingStatus.PAUSED,
        )

        response = self.client.get(
            reverse("listings:list"),
            {"category": ListingCategory.GIFT_CARD, "q": "Steam"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Steam PK Gift Card")
        self.assertNotContains(response, "Valorant Account")
        self.assertNotContains(response, "PSN Gift Card")

    def test_listing_detail_hidden_if_not_active(self):
        paused_listing = Listing.objects.create(
            seller=self.seller,
            game=self.pubg_game,
            game_category=self.pubg_currency_category,
            category=ListingCategory.ITEM,
            game_title="PUBG",
            title="Rare Skin Bundle",
            description="Paused entry",
            price_pkr="3000.00",
            stock=1,
            status=ListingStatus.PAUSED,
        )

        response = self.client.get(reverse("listings:detail", kwargs={"pk": paused_listing.pk}))

        self.assertEqual(response.status_code, 404)

    def test_seller_can_view_own_sold_out_listing_detail(self):
        sold_out_listing = Listing.objects.create(
            seller=self.seller,
            game=self.pubg_game,
            game_category=self.pubg_currency_category,
            category=ListingCategory.ACCOUNT,
            game_title="PUBG",
            title="Sold Out Account",
            description="Out of stock listing.",
            price_pkr="3000.00",
            stock=0,
            status=ListingStatus.SOLD_OUT,
        )
        self.client.force_login(self.seller)

        response = self.client.get(reverse("listings:detail", kwargs={"pk": sold_out_listing.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Restock Listing")

    def test_seller_can_restock_sold_out_listing(self):
        sold_out_listing = Listing.objects.create(
            seller=self.seller,
            game=self.pubg_game,
            game_category=self.pubg_currency_category,
            category=ListingCategory.ACCOUNT,
            game_title="PUBG",
            title="Need Restock",
            description="Out of stock listing.",
            price_pkr="3000.00",
            stock=0,
            status=ListingStatus.SOLD_OUT,
        )
        self.client.force_login(self.seller)

        response = self.client.post(
            reverse("listings:restock", kwargs={"listing_id": sold_out_listing.pk}),
            {"stock": 5},
        )

        self.assertRedirects(response, reverse("listings:detail", kwargs={"pk": sold_out_listing.pk}))
        sold_out_listing.refresh_from_db()
        self.assertEqual(sold_out_listing.stock, 5)
        self.assertEqual(sold_out_listing.status, ListingStatus.ACTIVE)

    def test_other_seller_cannot_restock_foreign_listing(self):
        other_seller = User.objects.create_user(
            email="other-seller@example.com",
            password="StrongPass123!",
            role=UserRole.SELLER,
        )
        sold_out_listing = Listing.objects.create(
            seller=self.seller,
            game=self.pubg_game,
            game_category=self.pubg_currency_category,
            category=ListingCategory.ACCOUNT,
            game_title="PUBG",
            title="Foreign Listing",
            description="Out of stock listing.",
            price_pkr="3000.00",
            stock=0,
            status=ListingStatus.SOLD_OUT,
        )
        self.client.force_login(other_seller)

        response = self.client.post(
            reverse("listings:restock", kwargs={"listing_id": sold_out_listing.pk}),
            {"stock": 3},
        )

        self.assertEqual(response.status_code, 404)

    def test_seller_can_edit_own_listing(self):
        listing = Listing.objects.create(
            seller=self.seller,
            game=self.valorant_game,
            game_category=self.valorant_account_category,
            category=ListingCategory.ACCOUNT,
            game_title="Valorant",
            title="Old Title",
            description="Old description.",
            price_pkr="3000.00",
            stock=2,
            status=ListingStatus.ACTIVE,
        )
        self.client.force_login(self.seller)

        response = self.client.post(
            reverse("listings:edit", kwargs={"pk": listing.pk}),
            {
                "game": self.pubg_game.id,
                "game_category": self.pubg_currency_category.id,
                "title": "New Title",
                "description": "Updated description.",
                "price_pkr": "3500.00",
                "stock": 5,
            },
        )

        self.assertRedirects(response, reverse("listings:detail", kwargs={"pk": listing.pk}))
        listing.refresh_from_db()
        self.assertEqual(listing.title, "New Title")
        self.assertEqual(listing.game, self.pubg_game)
        self.assertEqual(listing.game_category, self.pubg_currency_category)
        self.assertEqual(listing.category, ListingCategory.CURRENCY)
        self.assertEqual(listing.stock, 5)

    def test_seller_can_pause_and_activate_listing(self):
        listing = Listing.objects.create(
            seller=self.seller,
            game=self.valorant_game,
            game_category=self.valorant_account_category,
            category=ListingCategory.ACCOUNT,
            game_title="Valorant",
            title="Toggle Listing",
            description="Toggle flow.",
            price_pkr="2200.00",
            stock=2,
            status=ListingStatus.ACTIVE,
        )
        self.client.force_login(self.seller)

        pause_response = self.client.post(reverse("listings:pause", kwargs={"listing_id": listing.pk}))
        self.assertRedirects(pause_response, reverse("listings:detail", kwargs={"pk": listing.pk}))
        listing.refresh_from_db()
        self.assertEqual(listing.status, ListingStatus.PAUSED)

        activate_response = self.client.post(reverse("listings:activate", kwargs={"listing_id": listing.pk}))
        self.assertRedirects(activate_response, reverse("listings:detail", kwargs={"pk": listing.pk}))
        listing.refresh_from_db()
        self.assertEqual(listing.status, ListingStatus.ACTIVE)

    def test_seller_can_delete_listing_without_orders(self):
        listing = Listing.objects.create(
            seller=self.seller,
            game=self.valorant_game,
            game_category=self.valorant_account_category,
            category=ListingCategory.ACCOUNT,
            game_title="Valorant",
            title="Delete Me",
            description="Delete flow.",
            price_pkr="2200.00",
            stock=2,
            status=ListingStatus.ACTIVE,
        )
        self.client.force_login(self.seller)

        response = self.client.post(reverse("listings:delete", kwargs={"listing_id": listing.pk}))

        self.assertRedirects(response, reverse("listings:mine"))
        self.assertFalse(Listing.objects.filter(pk=listing.pk).exists())

    def test_listing_with_orders_is_archived_instead_of_deleted(self):
        listing = Listing.objects.create(
            seller=self.seller,
            game=self.valorant_game,
            game_category=self.valorant_account_category,
            category=ListingCategory.ACCOUNT,
            game_title="Valorant",
            title="Archive Me",
            description="Has order history.",
            price_pkr="2200.00",
            stock=2,
            status=ListingStatus.ACTIVE,
        )
        Order.objects.create(
            buyer=self.buyer,
            seller=self.seller,
            listing=listing,
            quantity=1,
            unit_price=Decimal("2200.00"),
            total_amount=Decimal("2200.00"),
        )
        self.client.force_login(self.seller)

        response = self.client.post(reverse("listings:delete", kwargs={"listing_id": listing.pk}))

        self.assertRedirects(response, reverse("listings:mine"))
        listing.refresh_from_db()
        self.assertEqual(listing.status, ListingStatus.ARCHIVED)
