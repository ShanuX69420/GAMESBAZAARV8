from django.core.management.base import BaseCommand

from orders.services import process_due_auto_releases


class Command(BaseCommand):
    help = "Process delivered orders that have passed auto-release time."

    def handle(self, *args, **options):
        released = process_due_auto_releases()
        self.stdout.write(self.style.SUCCESS(f"Auto-released {released} order(s)."))
