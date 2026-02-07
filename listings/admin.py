from django.contrib import admin
from django.db.models import Count

from .models import Game, GameCategoryOption, Listing


class GameCategoryOptionInline(admin.TabularInline):
    model = GameCategoryOption
    extra = 1
    fields = ("display_name", "canonical_category", "sort_order", "is_active")
    ordering = ("sort_order", "display_name")


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "category_option_count", "created_at")
    list_editable = ("is_active",)
    list_filter = ("is_active", "created_at")
    search_fields = ("name",)
    ordering = ("name",)
    actions = ("activate_selected_games", "deactivate_selected_games")
    inlines = (GameCategoryOptionInline,)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(category_option_total=Count("category_options"))

    def category_option_count(self, obj):
        return obj.category_option_total

    category_option_count.short_description = "Category options"
    category_option_count.admin_order_field = "category_option_total"

    @admin.action(description="Activate selected games")
    def activate_selected_games(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Activated {updated} game(s).")

    @admin.action(description="Deactivate selected games")
    def deactivate_selected_games(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {updated} game(s).")


@admin.register(GameCategoryOption)
class GameCategoryOptionAdmin(admin.ModelAdmin):
    list_display = ("display_name", "game", "canonical_category", "sort_order", "is_active")
    list_filter = ("canonical_category", "is_active", "game")
    search_fields = ("display_name", "game__name")
    list_editable = ("sort_order", "is_active")
    list_select_related = ("game",)
    ordering = ("game__name", "sort_order", "display_name")
    actions = ("activate_selected_options", "deactivate_selected_options")

    @admin.action(description="Activate selected category options")
    def activate_selected_options(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Activated {updated} category option(s).")

    @admin.action(description="Deactivate selected category options")
    def deactivate_selected_options(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {updated} category option(s).")


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "display_game_name",
        "display_category_name",
        "price_pkr",
        "stock",
        "status",
        "seller",
        "created_at",
    )
    list_filter = ("status", "category", "game", "game_category", "created_at")
    search_fields = ("title", "game_title", "game__name", "game_category__display_name", "seller__email")
    autocomplete_fields = ("game", "game_category", "seller")
    list_select_related = ("seller", "game", "game_category")
    date_hierarchy = "created_at"
