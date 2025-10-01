import uuid
import unicodedata
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


def normalize_username(raw: str) -> str:
    if raw is None:
        return raw
    s = raw.strip()
    s = unicodedata.normalize("NFKC", s)
    return s.lower()


class ReservedUsername(models.Model):
    """
    Dynamic list of reserved usernames (case-insensitive).
    name     = user-facing value
    name_ci  = lowercase version used for indexing and lookups
    """
    name = models.CharField(max_length=64, unique=True)
    name_ci = models.CharField(max_length=64, unique=True, db_index=True)
    protected = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        self.name_ci = normalize_username(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class User(AbstractUser):
    """Auth principal for the application."""
    # --- Primary key and email (kept as before)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)

    # --- Profile
    bio = models.CharField(max_length=160, blank=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)

    # --- Username change control (handle)
    username_change_count = models.PositiveIntegerField(default=0)
    username_changed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # Case-insensitive uniqueness on username
        constraints = [
            models.UniqueConstraint(
                Lower("username"),
                name="uniq_username_case_insensitive",
            )
        ]

    def __str__(self):
        return self.username

    # --- Allowed window to change the username (one-time within 7 days)
    @property
    def username_change_allowed_until(self):
        if self.username_change_count >= 1:
            return None
        base = getattr(self, "date_joined", None) or timezone.now()
        return base + timedelta(days=getattr(settings, "USERNAME_CHANGE_WINDOW_DAYS", 7))

    def can_change_username(self) -> bool:
        if self.username_change_count >= 1:
            return False
        until = self.username_change_allowed_until
        return until is not None and timezone.now() <= until

    # --- Full username policy (applies to the same `username` field)
    def clean_username_policy(self, new_username: str, *, changing: bool = False):
        """
        Rules:
        - regex/length from settings (USERNAME_REGEX / MIN / MAX)
        - reserved check (DB + fallback from settings.RESERVED_USERNAMES_DEFAULT)
        - case-insensitive uniqueness
        - if changing=True: enforce the 7-day window / immutability
        """
        import re
        if not new_username:
            raise ValidationError("username_required")

        normalized = normalize_username(new_username)

        pattern = getattr(settings, "USERNAME_REGEX", r"^[a-z0-9_]{3,32}$")
        if not re.match(pattern, normalized):
            if len(normalized) < getattr(settings, "USERNAME_MIN_LEN", 3):
                raise ValidationError("too_short")
            if len(normalized) > getattr(settings, "USERNAME_MAX_LEN", 32):
                raise ValidationError("too_long")
            raise ValidationError("invalid_format")

        # reserved: from DB
        if ReservedUsername.objects.filter(name_ci=normalized).exists():
            raise ValidationError("reserved")
        # reserved: fallback from settings
        fallback = set(getattr(settings, "RESERVED_USERNAMES_DEFAULT", set()))
        if normalized in {normalize_username(x) for x in fallback}:
            raise ValidationError("reserved")

        # uniqueness (case-insensitive)
        qs = User.objects.all()
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.extra(where=["LOWER(username) = %s"], params=[normalized]).exists():
            raise ValidationError("taken")

        # change rule
        if changing and getattr(settings, "USERNAME_IMMUTABLE_AFTER_WINDOW", True):
            if not self.can_change_username():
                raise ValidationError("immutable_username")

    # --- Official path to change the username
    def change_username(self, new_username: str):
        self.clean_username_policy(new_username, changing=True)
        self.username = new_username
        self.username_change_count += 1
        self.username_changed_at = timezone.now()
        self.save(update_fields=["username", "username_change_count", "username_changed_at"])

    # --- Prevent bypassing the rules by direct save on `username`
    def save(self, *args, **kwargs):
        if self._state.adding:
            # Creation
            self.clean_username_policy(self.username, changing=False)
        else:
            # If `username` changes on update, enforce `changing=True` policy
            if "update_fields" in kwargs and kwargs["update_fields"] is not None:
                if "username" in kwargs["update_fields"]:
                    self.clean_username_policy(self.username, changing=True)
            else:
                old = type(self).objects.filter(pk=self.pk).values_list("username", flat=True).first()
                if old is not None and old != self.username:
                    self.clean_username_policy(self.username, changing=True)

        super().save(*args, **kwargs)
