from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from listings.models import Game, GameCategoryOption, ListingCategory


DEFAULT_CATALOG = [
    {
        "name": "PUBG Mobile",
        "options": [
            (ListingCategory.CURRENCY, "UC"),
            (ListingCategory.ACCOUNT, "Account"),
        ],
    },
    {
        "name": "8 Ball Pool",
        "options": [
            (ListingCategory.CURRENCY, "Coins"),
            (ListingCategory.ACCOUNT, "Account"),
        ],
    },
    {
        "name": "FC Mobile",
        "options": [
            (ListingCategory.CURRENCY, "Points"),
            (ListingCategory.ACCOUNT, "Account"),
        ],
    },
    {
        "name": "Valorant",
        "options": [
            (ListingCategory.CURRENCY, "VP Points"),
            (ListingCategory.ACCOUNT, "Account"),
        ],
    },
    {
        "name": "Free Fire",
        "options": [
            (ListingCategory.CURRENCY, "Diamonds"),
            (ListingCategory.ACCOUNT, "Account"),
        ],
    },
    {
        "name": "Call of Duty Mobile",
        "options": [
            (ListingCategory.CURRENCY, "CP"),
            (ListingCategory.ACCOUNT, "Account"),
        ],
    },
    {
        "name": "Roblox",
        "options": [
            (ListingCategory.CURRENCY, "Robux"),
            (ListingCategory.ACCOUNT, "Account"),
        ],
    },
    {
        "name": "Steam",
        "options": [
            (ListingCategory.GIFT_CARD, "Wallet Code"),
            (ListingCategory.GIFT_CARD, "Gift Card"),
        ],
    },
    {
        "name": "PlayStation",
        "options": [
            (ListingCategory.GIFT_CARD, "PSN Gift Card"),
        ],
    },
    {
        "name": "Xbox",
        "options": [
            (ListingCategory.GIFT_CARD, "Xbox Gift Card"),
        ],
    },
]


class Command(BaseCommand):
    help = "Seed admin-managed game catalog and per-game category options."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only-game",
            dest="only_game",
            type=str,
            default="",
            help="Seed only one game by exact name (case-insensitive).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        only_game = (options.get("only_game") or "").strip()

        target_catalog = DEFAULT_CATALOG
        if only_game:
            target_catalog = [entry for entry in DEFAULT_CATALOG if entry["name"].lower() == only_game.lower()]
            if not target_catalog:
                raise CommandError(
                    f'No seed definition found for "{only_game}". '
                    "Run without --only-game to seed full catalog."
                )

        games_created = 0
        games_updated = 0
        options_created = 0
        options_updated = 0

        for game_entry in target_catalog:
            game, created = Game.objects.get_or_create(
                name=game_entry["name"],
                defaults={"is_active": True},
            )
            if created:
                games_created += 1
            elif not game.is_active:
                game.is_active = True
                game.save(update_fields=["is_active", "updated_at"])
                games_updated += 1

            for index, (canonical_category, display_name) in enumerate(game_entry["options"], start=1):
                option, option_created = GameCategoryOption.objects.get_or_create(
                    game=game,
                    display_name=display_name,
                    defaults={
                        "canonical_category": canonical_category,
                        "sort_order": index,
                        "is_active": True,
                    },
                )
                if option_created:
                    options_created += 1
                    continue

                changed_fields = []
                if option.canonical_category != canonical_category:
                    option.canonical_category = canonical_category
                    changed_fields.append("canonical_category")
                if option.sort_order != index:
                    option.sort_order = index
                    changed_fields.append("sort_order")
                if not option.is_active:
                    option.is_active = True
                    changed_fields.append("is_active")
                if changed_fields:
                    changed_fields.append("updated_at")
                    option.save(update_fields=changed_fields)
                    options_updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Catalog seed complete: "
                f"games created={games_created}, games updated={games_updated}, "
                f"options created={options_created}, options updated={options_updated}."
            )
        )
