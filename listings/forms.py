from decimal import Decimal

from django import forms

from .models import Game, GameCategoryOption, Listing, ListingStatus


class ListingForm(forms.ModelForm):
    stock = forms.IntegerField(
        min_value=1,
        required=True,
        error_messages={
            "required": "Stock is required.",
            "invalid": "Enter a whole number.",
            "min_value": "Stock must be at least 1.",
        },
    )

    class Meta:
        model = Listing
        fields = ("game", "game_category", "title", "description", "price_pkr", "stock")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["game"].queryset = Game.objects.filter(is_active=True).order_by("name")
        self.fields["game"].required = True
        self.fields["game_category"].required = True
        self.fields["game_category"].queryset = GameCategoryOption.objects.none()
        self.fields["game_category"].label = "Category"
        self.fields["stock"].widget.attrs.update({"min": "1", "step": "1"})

        game_id = self.data.get("game") or self.initial.get("game")
        if not game_id and self.instance.pk and self.instance.game_id:
            game_id = self.instance.game_id

        if game_id:
            self.fields["game_category"].queryset = GameCategoryOption.objects.filter(
                game_id=game_id,
                is_active=True,
            ).order_by("sort_order", "display_name")

    def clean_price_pkr(self):
        price = self.cleaned_data["price_pkr"]
        if price <= Decimal("0"):
            raise forms.ValidationError("Price must be greater than zero.")
        return price

    def clean_stock(self):
        stock = self.cleaned_data["stock"]
        if stock < 1:
            raise forms.ValidationError("Stock must be at least 1.")
        return stock

    def clean(self):
        cleaned_data = super().clean()
        game = cleaned_data.get("game")
        game_category = cleaned_data.get("game_category")
        if game and game_category and game_category.game_id != game.id:
            self.add_error("game_category", "Selected category does not belong to selected game.")
        return cleaned_data

    def save(self, commit=True):
        listing = super().save(commit=False)
        if listing.game_id and listing.game_category_id:
            listing.game_title = listing.game.name
            listing.category = listing.game_category.canonical_category
        listing.status = ListingStatus.ACTIVE if listing.stock > 0 else ListingStatus.SOLD_OUT
        if commit:
            listing.save()
        return listing


class ListingRestockForm(forms.Form):
    stock = forms.IntegerField(min_value=1)
