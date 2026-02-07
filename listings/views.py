from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.models import UserRole

from .forms import ListingForm, ListingRestockForm
from .models import GameCategoryOption, Listing, ListingCategory, ListingStatus


class SellerRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.role == UserRole.SELLER:
            return super().dispatch(request, *args, **kwargs)
        messages.info(request, "Only approved sellers can create listings.")
        return redirect("accounts:seller_application")


class ListingCatalogContextMixin:
    def get_catalog_options_map(self):
        options = GameCategoryOption.objects.filter(
            is_active=True,
            game__is_active=True,
        ).select_related("game")
        options_by_game = {}
        for option in options:
            options_by_game.setdefault(str(option.game_id), []).append(
                {
                    "id": option.id,
                    "label": option.display_name,
                }
            )
        return options_by_game

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["game_category_options"] = self.get_catalog_options_map()
        return context


class ListingListView(ListView):
    model = Listing
    template_name = "listings/listing_list.html"
    context_object_name = "listings"
    paginate_by = 20

    def get_queryset(self):
        queryset = Listing.objects.select_related("seller", "game", "game_category").filter(status=ListingStatus.ACTIVE)

        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(game__name__icontains=query)
                | Q(game_title__icontains=query)
                | Q(game_category__display_name__icontains=query)
            )

        category = self.request.GET.get("category", "").strip()
        valid_categories = {value for value, _ in ListingCategory.choices}
        if category in valid_categories:
            queryset = queryset.filter(
                Q(game_category__canonical_category=category)
                | Q(game_category__isnull=True, category=category)
            )

        min_price = self.request.GET.get("min_price", "").strip()
        if min_price:
            try:
                queryset = queryset.filter(price_pkr__gte=Decimal(min_price))
            except InvalidOperation:
                pass

        max_price = self.request.GET.get("max_price", "").strip()
        if max_price:
            try:
                queryset = queryset.filter(price_pkr__lte=Decimal(max_price))
            except InvalidOperation:
                pass

        sort = self.request.GET.get("sort", "newest")
        if sort == "price_low":
            queryset = queryset.order_by("price_pkr", "-created_at")
        elif sort == "price_high":
            queryset = queryset.order_by("-price_pkr", "-created_at")
        else:
            queryset = queryset.order_by("-created_at")

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["category_choices"] = ListingCategory.choices
        context["current_query"] = self.request.GET.get("q", "").strip()
        context["current_category"] = self.request.GET.get("category", "").strip()
        context["current_min_price"] = self.request.GET.get("min_price", "").strip()
        context["current_max_price"] = self.request.GET.get("max_price", "").strip()
        context["current_sort"] = self.request.GET.get("sort", "newest")
        return context


class ListingDetailView(DetailView):
    model = Listing
    template_name = "listings/listing_detail.html"
    context_object_name = "listing"

    def get_queryset(self):
        queryset = Listing.objects.select_related("seller", "game", "game_category")
        if self.request.user.is_authenticated:
            return queryset.filter(Q(status=ListingStatus.ACTIVE) | Q(seller=self.request.user))
        return queryset.filter(status=ListingStatus.ACTIVE)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        listing = self.object
        user = self.request.user
        is_owner = user.is_authenticated and user.id == listing.seller_id
        can_buy = (
            user.is_authenticated
            and user.id != listing.seller_id
            and listing.stock > 0
            and listing.status == ListingStatus.ACTIVE
        )
        can_restock = is_owner and listing.status in {ListingStatus.SOLD_OUT, ListingStatus.PAUSED}
        context["can_buy"] = can_buy
        context["is_owner"] = is_owner
        context["can_restock"] = can_restock
        context["can_pause"] = is_owner and listing.status == ListingStatus.ACTIVE
        context["can_activate"] = (
            is_owner
            and listing.stock > 0
            and listing.status in {ListingStatus.PAUSED, ListingStatus.SOLD_OUT, ListingStatus.ARCHIVED}
        )
        context["restock_form"] = ListingRestockForm(initial={"stock": 1})
        return context


class ListingCreateView(SellerRequiredMixin, ListingCatalogContextMixin, CreateView):
    model = Listing
    form_class = ListingForm
    template_name = "listings/listing_form.html"

    def form_valid(self, form):
        form.instance.seller = self.request.user
        messages.success(self.request, "Listing created successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("listings:detail", kwargs={"pk": self.object.pk})


class ListingUpdateView(SellerRequiredMixin, ListingCatalogContextMixin, UpdateView):
    model = Listing
    form_class = ListingForm
    template_name = "listings/listing_form.html"

    def get_queryset(self):
        return Listing.objects.filter(seller=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_edit"] = True
        return context

    def form_valid(self, form):
        existing_status = self.get_object().status
        response = super().form_valid(form)
        if self.object.stock < 1:
            self.object.status = ListingStatus.SOLD_OUT
        elif existing_status == ListingStatus.PAUSED:
            self.object.status = ListingStatus.PAUSED
        elif existing_status == ListingStatus.ARCHIVED:
            self.object.status = ListingStatus.ARCHIVED
        else:
            self.object.status = ListingStatus.ACTIVE
        self.object.save(update_fields=["status", "updated_at"])
        messages.success(self.request, "Listing updated successfully.")
        return response

    def get_success_url(self):
        return reverse("listings:detail", kwargs={"pk": self.object.pk})


class SellerListingListView(SellerRequiredMixin, ListView):
    model = Listing
    template_name = "listings/seller_listing_list.html"
    context_object_name = "listings"

    def get_queryset(self):
        return Listing.objects.select_related("game", "game_category").filter(seller=self.request.user).order_by("-created_at")


class ListingRestockView(SellerRequiredMixin, View):
    def post(self, request, listing_id):
        listing = get_object_or_404(Listing, pk=listing_id, seller=request.user)
        form = ListingRestockForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Please provide a valid stock value.")
            return redirect("listings:detail", pk=listing.pk)

        listing.stock = form.cleaned_data["stock"]
        listing.status = ListingStatus.ACTIVE
        listing.save(update_fields=["stock", "status", "updated_at"])
        messages.success(request, "Listing restocked and activated.")
        return redirect("listings:detail", pk=listing.pk)


class ListingStatusUpdateView(SellerRequiredMixin, View):
    def post(self, request, listing_id, action):
        listing = get_object_or_404(Listing, pk=listing_id, seller=request.user)
        next_url = request.POST.get("next") or reverse("listings:detail", kwargs={"pk": listing.pk})

        if action == "pause":
            if listing.status == ListingStatus.ACTIVE:
                listing.status = ListingStatus.PAUSED
                listing.save(update_fields=["status", "updated_at"])
                messages.success(request, "Listing paused.")
            else:
                messages.info(request, "Only active listings can be paused.")
            return redirect(next_url)

        if action == "activate":
            if listing.stock < 1:
                messages.error(request, "Cannot activate listing with zero stock. Please restock first.")
                return redirect(next_url)
            if listing.status == ListingStatus.ACTIVE:
                messages.info(request, "Listing is already active.")
                return redirect(next_url)
            listing.status = ListingStatus.ACTIVE
            listing.save(update_fields=["status", "updated_at"])
            messages.success(request, "Listing activated.")
            return redirect(next_url)

        messages.error(request, "Invalid listing action.")
        return redirect(next_url)


class ListingDeleteView(SellerRequiredMixin, View):
    def post(self, request, listing_id):
        listing = get_object_or_404(Listing, pk=listing_id, seller=request.user)
        if listing.orders.exists():
            if listing.status != ListingStatus.ARCHIVED:
                listing.status = ListingStatus.ARCHIVED
                listing.save(update_fields=["status", "updated_at"])
                messages.info(
                    request,
                    "Listing has order history, so it was archived instead of permanently deleted.",
                )
            else:
                messages.info(request, "Listing is already archived.")
        else:
            listing.delete()
            messages.success(request, "Listing deleted.")
        return redirect("listings:mine")
