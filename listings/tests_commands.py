from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from listings.management.commands.seed_game_catalog import DEFAULT_CATALOG
from listings.models import Game, GameCategoryOption, ListingCategory


class SeedGameCatalogCommandTests(TestCase):
    def test_seed_game_catalog_creates_default_catalog(self):
        output = StringIO()

        call_command("seed_game_catalog", stdout=output)

        self.assertIn("Catalog seed complete", output.getvalue())
        self.assertEqual(Game.objects.count(), len(DEFAULT_CATALOG))
        expected_option_count = sum(len(entry["options"]) for entry in DEFAULT_CATALOG)
        self.assertEqual(GameCategoryOption.objects.count(), expected_option_count)

        pubg = Game.objects.get(name="PUBG Mobile")
        self.assertTrue(pubg.is_active)
        self.assertTrue(
            GameCategoryOption.objects.filter(
                game=pubg,
                display_name="UC",
                canonical_category=ListingCategory.CURRENCY,
                is_active=True,
            ).exists()
        )

    def test_seed_game_catalog_is_idempotent(self):
        call_command("seed_game_catalog")
        game_count = Game.objects.count()
        option_count = GameCategoryOption.objects.count()

        call_command("seed_game_catalog")

        self.assertEqual(Game.objects.count(), game_count)
        self.assertEqual(GameCategoryOption.objects.count(), option_count)

    def test_seed_only_game_creates_subset(self):
        call_command("seed_game_catalog", only_game="Valorant")

        self.assertEqual(Game.objects.count(), 1)
        valorant = Game.objects.get(name="Valorant")
        self.assertEqual(valorant.category_options.count(), 2)

    def test_seed_only_game_rejects_unknown_name(self):
        with self.assertRaises(CommandError):
            call_command("seed_game_catalog", only_game="Unknown Game")
