from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class UserRole(models.TextChoices):
    BUYER = "buyer", "Buyer"
    SELLER = "seller", "Seller"
    MODERATOR = "moderator", "Moderator"
    ADMIN = "admin", "Admin"


class SellerApplicationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("The email field must be set.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("role", UserRole.BUYER)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", UserRole.ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.BUYER)
    is_email_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email


class SellerApplication(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="seller_application")
    display_name = models.CharField(max_length=80)
    experience = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=SellerApplicationStatus.choices,
        default=SellerApplicationStatus.PENDING,
    )
    admin_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_seller_applications",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} ({self.status})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.status == SellerApplicationStatus.APPROVED and self.user.role != UserRole.SELLER:
            self.user.role = UserRole.SELLER
            self.user.save(update_fields=["role", "updated_at"])

    def mark_approved(self, reviewer=None, note=""):
        self.status = SellerApplicationStatus.APPROVED
        self.admin_note = note
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "admin_note", "reviewed_by", "reviewed_at", "updated_at"])

    def mark_rejected(self, reviewer=None, note=""):
        self.status = SellerApplicationStatus.REJECTED
        self.admin_note = note
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "admin_note", "reviewed_by", "reviewed_at", "updated_at"])
