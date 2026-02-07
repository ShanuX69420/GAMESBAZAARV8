from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import WalletAccount


@receiver(post_save, sender=get_user_model())
def create_wallet_on_user_create(sender, instance, created, **kwargs):
    if created:
        WalletAccount.objects.get_or_create(user=instance)
