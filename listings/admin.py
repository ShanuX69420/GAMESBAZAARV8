from django.contrib import admin

from .models import Game, GameCategoryOption, Listing


class GameCategoryOptionInline(admin.TabularInline):
    model = GameCategoryOption
    extra = 1
    fields = ("display_name", "canonical_category", "sort_order", "is_active")
    ordering = ("sort_order", "display_name")


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "category_option_count", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name",)
    inlines = (GameCategoryOptionInline,)

    def category_option_count(self, obj):
        return obj.category_options.count()

    category_option_count.short_description = "Category options"


@admin.register(GameCategoryOption)
class GameCategoryOptionAdmin(admin.ModelAdmin):
    list_display = ("display_name", "game", "canonical_category", "sort_order", "is_active")
    list_filter = ("canonical_category", "is_active", "game")
    search_fields = ("display_name", "game__name")
    ordering = ("game__name", "sort_order", "display_name")


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ("title", "display_game_name", "display_category_name", "price_pkr", "status", "seller", "created_at")
    list_filter = ("category", "status", "created_at")
    search_fields = ("title", "game_title", "game__name", "game_category__display_name", "seller__email")
    autocomplete_fields = ("game", "game_category", "seller")
