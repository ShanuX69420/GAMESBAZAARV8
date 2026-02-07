from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.client import RequestFactory
from django.urls import reverse

from .admin import SellerApplicationAdmin
from .models import SellerApplication, SellerApplicationStatus, UserRole


User = get_user_model()


class AccountAuthTests(TestCase):
    def test_register_creates_user_with_default_buyer_role(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "email": "buyer@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertRedirects(response, reverse("core:home"))
        user = User.objects.get(email="buyer@example.com")
        self.assertEqual(user.role, "buyer")
        self.assertEqual(self.client.session.get("_auth_user_id"), str(user.id))

    def test_login_and_logout_flow(self):
        User.objects.create_user(
            email="seller@example.com",
            password="StrongPass123!",
            role=UserRole.SELLER,
        )

        login_response = self.client.post(
            reverse("accounts:login"),
            {
                "username": "seller@example.com",
                "password": "StrongPass123!",
            },
        )
        self.assertRedirects(login_response, reverse("core:home"))

        logout_response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(logout_response, reverse("core:home"))
        self.assertIsNone(self.client.session.get("_auth_user_id"))


class SellerApplicationTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user(
            email="buyer1@example.com",
            password="StrongPass123!",
            role=UserRole.BUYER,
        )

    def test_buyer_can_submit_seller_application(self):
        self.client.force_login(self.buyer)

        response = self.client.post(
            reverse("accounts:seller_application"),
            {"display_name": "Trusted Trader", "experience": "I sell game accounts for 2 years."},
        )

        self.assertRedirects(response, reverse("accounts:seller_application"))
        application = SellerApplication.objects.get(user=self.buyer)
        self.assertEqual(application.status, SellerApplicationStatus.PENDING)
        self.assertEqual(application.display_name, "Trusted Trader")

    def test_pending_application_cannot_be_resubmitted(self):
        self.client.force_login(self.buyer)
        SellerApplication.objects.create(
            user=self.buyer,
            display_name="Original Name",
            experience="Original experience.",
            status=SellerApplicationStatus.PENDING,
        )

        response = self.client.post(
            reverse("accounts:seller_application"),
            {"display_name": "Edited Name", "experience": "Edited experience."},
        )

        self.assertRedirects(response, reverse("accounts:seller_application"))
        application = SellerApplication.objects.get(user=self.buyer)
        self.assertEqual(application.display_name, "Original Name")
        self.assertEqual(application.status, SellerApplicationStatus.PENDING)

    def test_rejected_application_can_be_resubmitted(self):
        self.client.force_login(self.buyer)
        application = SellerApplication.objects.create(
            user=self.buyer,
            display_name="Old Name",
            experience="Old experience.",
            status=SellerApplicationStatus.REJECTED,
            admin_note="Needs better detail.",
        )

        response = self.client.post(
            reverse("accounts:seller_application"),
            {"display_name": "New Name", "experience": "Now with full details."},
        )

        self.assertRedirects(response, reverse("accounts:seller_application"))
        application.refresh_from_db()
        self.assertEqual(application.display_name, "New Name")
        self.assertEqual(application.status, SellerApplicationStatus.PENDING)
        self.assertEqual(application.admin_note, "")
        self.assertIsNone(application.reviewed_at)
        self.assertIsNone(application.reviewed_by)

    def test_admin_approve_action_promotes_user_to_seller(self):
        admin_user = User.objects.create_superuser(
            email="admin@example.com",
            password="StrongPass123!",
        )
        application = SellerApplication.objects.create(
            user=self.buyer,
            display_name="Approval Test",
            status=SellerApplicationStatus.PENDING,
        )
        request = RequestFactory().post("/admin/accounts/sellerapplication/")
        request.user = admin_user

        admin_model = SellerApplicationAdmin(SellerApplication, AdminSite())
        admin_model.approve_applications(request, SellerApplication.objects.filter(pk=application.pk))

        application.refresh_from_db()
        self.buyer.refresh_from_db()
        self.assertEqual(application.status, SellerApplicationStatus.APPROVED)
        self.assertEqual(application.reviewed_by, admin_user)
        self.assertEqual(self.buyer.role, UserRole.SELLER)

    def test_manual_status_update_to_approved_promotes_user_to_seller(self):
        application = SellerApplication.objects.create(
            user=self.buyer,
            display_name="Manual Approval",
            status=SellerApplicationStatus.PENDING,
        )

        application.status = SellerApplicationStatus.APPROVED
        application.save()

        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.role, UserRole.SELLER)
