from django.conf import settings
from django.db import models
from django.utils import timezone


class ListingCategory(models.TextChoices):
    ACCOUNT = "account", "Account"
    ITEM = "item", "Item"
    CURRENCY = "currency", "Currency"
    TOPUP = "topup", "Top Up"
    GIFT_CARD = "gift_card", "Gift Card"
    BOOSTING = "boosting", "Boosting"


class ListingStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    SOLD_OUT = "sold_out", "Sold Out"
    ARCHIVED = "archived", "Archived"


class Game(models.Model):
    name = models.CharField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class GameCategoryOption(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name="category_options")
    canonical_category = models.CharField(max_length=20, choices=ListingCategory.choices)
    display_name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("game__name", "sort_order", "display_name")
        unique_together = ("game", "display_name")
        indexes = [
            models.Index(fields=["game", "canonical_category", "is_active"]),
        ]

    def __str__(self):
        return f"{self.game.name} - {self.display_name}"


class Listing(models.Model):
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="listings",
    )
    game = models.ForeignKey(
        Game,
        on_delete=models.PROTECT,
        related_name="listings",
        null=True,
        blank=True,
    )
    game_category = models.ForeignKey(
        GameCategoryOption,
        on_delete=models.PROTECT,
        related_name="listings",
        null=True,
        blank=True,
    )
    category = models.CharField(max_length=20, choices=ListingCategory.choices)
    game_title = models.CharField(max_length=120)
    title = models.CharField(max_length=160)
    description = models.TextField()
    price_pkr = models.DecimalField(max_digits=12, decimal_places=2)
    stock = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=ListingStatus.choices, default=ListingStatus.ACTIVE)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "category"]),
            models.Index(fields=["price_pkr"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.price_pkr} PKR)"

    @property
    def display_game_name(self):
        if self.game_id:
            return self.game.name
        return self.game_title

    @property
    def display_category_name(self):
        if self.game_category_id:
            return self.game_category.display_name
        return self.get_category_display()
