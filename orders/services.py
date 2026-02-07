from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db import transaction
from django.utils import timezone

from listings.models import Listing, ListingStatus
from wallet.models import WalletAccount, WalletLedgerDirection, WalletLedgerType
from wallet.services import WalletError, append_wallet_entry, get_or_create_wallet

from .models import Dispute, DisputeStatus, Order, OrderStatus

MONEY_STEP = Decimal("0.01")
PLATFORM_FEE_PERCENT = Decimal("5.00")
AUTO_RELEASE_HOURS = 72


class OrderError(ValueError):
    pass


def _q(amount):
    return amount.quantize(MONEY_STEP, rounding=ROUND_HALF_UP)


def _calc_fee_and_net(total_amount):
    fee = _q((total_amount * PLATFORM_FEE_PERCENT) / Decimal("100"))
    if fee < 0:
        fee = Decimal("0.00")
    if fee > total_amount:
        fee = total_amount
    net = _q(total_amount - fee)
    return fee, net


def create_order_from_listing(*, buyer, listing_id, quantity=1):
    if quantity < 1:
        raise OrderError("Quantity must be at least 1.")

    with transaction.atomic():
        listing = Listing.objects.select_for_update().select_related("seller").get(pk=listing_id)

        if listing.status != ListingStatus.ACTIVE:
            raise OrderError("This listing is not available for purchase.")
        if listing.stock < quantity:
            raise OrderError("Listing is out of stock.")
        if listing.seller_id == buyer.id:
            raise OrderError("You cannot buy your own listing.")

        total_amount = _q(listing.price_pkr * quantity)
        fee_amount, seller_net_amount = _calc_fee_and_net(total_amount)

        buyer_wallet = get_or_create_wallet(buyer)
        buyer_wallet = WalletAccount.objects.select_for_update().get(pk=buyer_wallet.pk)
        if buyer_wallet.available_balance < total_amount:
            raise WalletError("Insufficient wallet balance for this order.")

        seller_wallet = get_or_create_wallet(listing.seller)
        seller_wallet = WalletAccount.objects.select_for_update().get(pk=seller_wallet.pk)

        order = Order.objects.create(
            buyer=buyer,
            seller=listing.seller,
            listing=listing,
            quantity=quantity,
            unit_price=listing.price_pkr,
            total_amount=total_amount,
            platform_fee_amount=fee_amount,
            seller_net_amount=seller_net_amount,
            status=OrderStatus.PENDING_DELIVERY,
            paid_at=timezone.now(),
        )

        append_wallet_entry(
            buyer_wallet,
            entry_type=WalletLedgerType.ORDER_PAYMENT,
            direction=WalletLedgerDirection.DEBIT,
            amount=total_amount,
            available_delta=-total_amount,
            note=f"Payment for order #{order.pk}.",
            reference_type="order",
            reference_id=str(order.pk),
            created_by=buyer,
        )

        append_wallet_entry(
            seller_wallet,
            entry_type=WalletLedgerType.ORDER_SALE_HOLD,
            direction=WalletLedgerDirection.CREDIT,
            amount=total_amount,
            held_delta=total_amount,
            note=f"Funds held for order #{order.pk}.",
            reference_type="order",
            reference_id=str(order.pk),
            created_by=buyer,
        )

        listing.stock -= quantity
        if listing.stock == 0:
            listing.status = ListingStatus.SOLD_OUT
        listing.save(update_fields=["stock", "status", "updated_at"])

        return order


def mark_order_delivered(*, order, actor, note=""):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if actor.id != order.seller_id:
            raise OrderError("Only the seller can mark an order as delivered.")
        if order.status != OrderStatus.PENDING_DELIVERY:
            raise OrderError("Only pending-delivery orders can be marked delivered.")

        now = timezone.now()
        order.status = OrderStatus.DELIVERED
        order.delivery_note = note
        order.delivered_at = now
        order.auto_release_at = now + timedelta(hours=AUTO_RELEASE_HOURS)
        order.save(
            update_fields=[
                "status",
                "delivery_note",
                "delivered_at",
                "auto_release_at",
                "updated_at",
            ]
        )
        return order


def _release_order_funds(*, order, actor=None, by_auto=False, resolution_note=""):
    with transaction.atomic():
        order = Order.objects.select_for_update().select_related("buyer", "seller").get(pk=order.pk)
        if order.status not in {OrderStatus.DELIVERED, OrderStatus.DISPUTED}:
            raise OrderError("Order cannot be completed in current state.")

        seller_wallet = get_or_create_wallet(order.seller)
        seller_wallet = WalletAccount.objects.select_for_update().get(pk=seller_wallet.pk)

        if seller_wallet.held_balance < order.total_amount:
            raise WalletError("Seller held balance is insufficient for order release.")

        append_wallet_entry(
            seller_wallet,
            entry_type=WalletLedgerType.ORDER_SALE_RELEASE,
            direction=WalletLedgerDirection.TRANSFER,
            amount=order.seller_net_amount,
            available_delta=order.seller_net_amount,
            held_delta=-order.seller_net_amount,
            note=f"Released seller net for order #{order.pk}.",
            reference_type="order",
            reference_id=str(order.pk),
            created_by=actor,
        )

        if order.platform_fee_amount > 0:
            append_wallet_entry(
                seller_wallet,
                entry_type=WalletLedgerType.ORDER_FEE_CAPTURE,
                direction=WalletLedgerDirection.DEBIT,
                amount=order.platform_fee_amount,
                held_delta=-order.platform_fee_amount,
                note=f"Platform fee captured for order #{order.pk}.",
                reference_type="order",
                reference_id=str(order.pk),
                created_by=actor,
            )

        now = timezone.now()
        order.status = OrderStatus.COMPLETED
        order.completed_at = now
        if not by_auto and actor and actor.id == order.buyer_id:
            order.buyer_confirmed_at = now
        order.save(
            update_fields=[
                "status",
                "completed_at",
                "buyer_confirmed_at",
                "updated_at",
            ]
        )

        dispute = Dispute.objects.filter(order=order, status=DisputeStatus.OPEN).first()
        if dispute:
            dispute.status = DisputeStatus.RESOLVED
            dispute.resolution_note = resolution_note or "Resolved in seller favor."
            dispute.resolved_by = actor if actor and actor.is_staff else None
            dispute.resolved_at = now
            dispute.save(
                update_fields=[
                    "status",
                    "resolution_note",
                    "resolved_by",
                    "resolved_at",
                    "updated_at",
                ]
            )

        return order


def confirm_order_delivery(*, order, actor):
    if actor.id != order.buyer_id:
        raise OrderError("Only the buyer can confirm delivery.")
    return _release_order_funds(order=order, actor=actor, by_auto=False)


def open_dispute(*, order, actor, reason, details=""):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if actor.id != order.buyer_id:
            raise OrderError("Only the buyer can open disputes.")
        if order.status != OrderStatus.DELIVERED:
            raise OrderError("Disputes can only be opened after delivery.")

        dispute, created = Dispute.objects.get_or_create(
            order=order,
            defaults={
                "opened_by": actor,
                "reason": reason,
                "details": details,
                "status": DisputeStatus.OPEN,
            },
        )
        if not created and dispute.status == DisputeStatus.OPEN:
            raise OrderError("A dispute is already open for this order.")
        if not created:
            dispute.opened_by = actor
            dispute.reason = reason
            dispute.details = details
            dispute.status = DisputeStatus.OPEN
            dispute.resolution_note = ""
            dispute.resolved_by = None
            dispute.resolved_at = None
            dispute.save(
                update_fields=[
                    "opened_by",
                    "reason",
                    "details",
                    "status",
                    "resolution_note",
                    "resolved_by",
                    "resolved_at",
                    "updated_at",
                ]
            )

        order.status = OrderStatus.DISPUTED
        order.save(update_fields=["status", "updated_at"])
        return dispute


def refund_order(*, order, actor=None, resolution_note=""):
    with transaction.atomic():
        order = Order.objects.select_for_update().select_related("buyer", "seller").get(pk=order.pk)
        if order.status not in {OrderStatus.PENDING_DELIVERY, OrderStatus.DELIVERED, OrderStatus.DISPUTED}:
            raise OrderError("Order cannot be refunded in current state.")

        seller_wallet = get_or_create_wallet(order.seller)
        seller_wallet = WalletAccount.objects.select_for_update().get(pk=seller_wallet.pk)
        buyer_wallet = get_or_create_wallet(order.buyer)
        buyer_wallet = WalletAccount.objects.select_for_update().get(pk=buyer_wallet.pk)

        if seller_wallet.held_balance < order.total_amount:
            raise WalletError("Seller held balance is insufficient to refund this order.")

        append_wallet_entry(
            seller_wallet,
            entry_type=WalletLedgerType.ORDER_REFUND,
            direction=WalletLedgerDirection.TRANSFER,
            amount=order.total_amount,
            held_delta=-order.total_amount,
            note=f"Held amount reversed for refunded order #{order.pk}.",
            reference_type="order",
            reference_id=str(order.pk),
            created_by=actor,
        )

        append_wallet_entry(
            buyer_wallet,
            entry_type=WalletLedgerType.ORDER_REFUND,
            direction=WalletLedgerDirection.CREDIT,
            amount=order.total_amount,
            available_delta=order.total_amount,
            note=f"Refund credited for order #{order.pk}.",
            reference_type="order",
            reference_id=str(order.pk),
            created_by=actor,
        )

        now = timezone.now()
        order.status = OrderStatus.REFUNDED
        order.completed_at = now
        order.save(update_fields=["status", "completed_at", "updated_at"])

        dispute = Dispute.objects.filter(order=order, status=DisputeStatus.OPEN).first()
        if dispute:
            dispute.status = DisputeStatus.RESOLVED
            dispute.resolution_note = resolution_note or "Resolved with buyer refund."
            dispute.resolved_by = actor if actor and actor.is_staff else None
            dispute.resolved_at = now
            dispute.save(
                update_fields=[
                    "status",
                    "resolution_note",
                    "resolved_by",
                    "resolved_at",
                    "updated_at",
                ]
            )

        return order


def process_due_auto_releases(*, now: Optional[datetime] = None):
    current_time = now or timezone.now()
    order_ids = list(
        Order.objects.filter(
            status=OrderStatus.DELIVERED,
            auto_release_at__isnull=False,
            auto_release_at__lte=current_time,
        ).values_list("id", flat=True)
    )

    released_count = 0
    for order_id in order_ids:
        try:
            order = Order.objects.get(pk=order_id)
            _release_order_funds(order=order, actor=None, by_auto=True)
            released_count += 1
        except (Order.DoesNotExist, OrderError, WalletError):
            continue

    return released_count


def resolve_dispute_seller_win(*, dispute, reviewer, note=""):
    if dispute.status != DisputeStatus.OPEN:
        raise OrderError("Only open disputes can be resolved.")
    return _release_order_funds(order=dispute.order, actor=reviewer, resolution_note=note)


def resolve_dispute_buyer_refund(*, dispute, reviewer, note=""):
    if dispute.status != DisputeStatus.OPEN:
        raise OrderError("Only open disputes can be resolved.")
    return refund_order(order=dispute.order, actor=reviewer, resolution_note=note)


def release_order_by_admin(*, order, reviewer, note=""):
    return _release_order_funds(order=order, actor=reviewer, resolution_note=note)
