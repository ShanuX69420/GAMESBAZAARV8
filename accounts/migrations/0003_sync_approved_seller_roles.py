from django.db import migrations
from django.utils import timezone


def sync_approved_roles(apps, schema_editor):
    SellerApplication = apps.get_model("accounts", "SellerApplication")
    User = apps.get_model("accounts", "User")

    approved_user_ids = SellerApplication.objects.filter(status="approved").values_list("user_id", flat=True)
    User.objects.filter(id__in=approved_user_ids).exclude(role="seller").update(
        role="seller",
        updated_at=timezone.now(),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_sellerapplication"),
    ]

    operations = [
        migrations.RunPython(sync_approved_roles, migrations.RunPython.noop),
    ]
