from django.conf import settings
from django.db import models
from django.utils import timezone


class OrderStatus(models.TextChoices):
    PENDING_DELIVERY = "pending_delivery", "Pending Delivery"
    DELIVERED = "delivered", "Delivered"
    COMPLETED = "completed", "Completed"
    DISPUTED = "disputed", "Disputed"
    REFUNDED = "refunded", "Refunded"
    CANCELLED = "cancelled", "Cancelled"


class DisputeStatus(models.TextChoices):
    OPEN = "open", "Open"
    RESOLVED = "resolved", "Resolved"


class Order(models.Model):
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="buy_orders",
    )
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sell_orders",
    )
    listing = models.ForeignKey("listings.Listing", on_delete=models.PROTECT, related_name="orders")
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    platform_fee_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    seller_net_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=24, choices=OrderStatus.choices, default=OrderStatus.PENDING_DELIVERY)
    delivery_note = models.TextField(blank=True)
    paid_at = models.DateTimeField(default=timezone.now)
    delivered_at = models.DateTimeField(null=True, blank=True)
    auto_release_at = models.DateTimeField(null=True, blank=True)
    buyer_confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "auto_release_at"]),
            models.Index(fields=["buyer", "created_at"]),
            models.Index(fields=["seller", "created_at"]),
        ]

    def __str__(self):
        return f"Order #{self.pk} ({self.status})"


class Dispute(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="dispute")
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="opened_disputes",
    )
    reason = models.CharField(max_length=120)
    details = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=DisputeStatus.choices, default=DisputeStatus.OPEN)
    resolution_note = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_disputes",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Dispute for order #{self.order_id} ({self.status})"
