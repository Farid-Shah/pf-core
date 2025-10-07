"""
Unit tests for User and ReservedUsername models.
"""
from datetime import timedelta
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings
from accounts.models import User, ReservedUsername
from accounts.utils import normalize_username


class ReservedUsernameModelTests(TestCase):
    """Test ReservedUsername model."""
    
    def test_create_permanent_reservation(self):
        """Should create permanent (system) reserved username."""
        reserved = ReservedUsername.objects.create(
            name="admin",
            protected=True,
            reason="system"
        )
        self.assertEqual(reserved.name, "admin")
        self.assertEqual(reserved.name_ci, "admin")
        self.assertTrue(reserved.protected)
        self.assertIsNone(reserved.expires_at)
        self.assertIsNone(reserved.reserved_by)
    
    def test_auto_normalize_on_save(self):
        """Should auto-normalize name_ci on save."""
        reserved = ReservedUsername.objects.create(name="Admin")
        self.assertEqual(reserved.name, "Admin")
        self.assertEqual(reserved.name_ci, "admin")  # normalized
    
    def test_is_reserved_permanent(self):
        """Should detect permanent reserved usernames."""
        ReservedUsername.objects.create(name="root", protected=True)
        
        self.assertTrue(ReservedUsername.is_reserved("root"))
        self.assertTrue(ReservedUsername.is_reserved("ROOT"))  # case-insensitive
        self.assertTrue(ReservedUsername.is_reserved("  Root  "))  # with whitespace
    
    def test_is_reserved_temporary_not_expired(self):
        """Should detect temporary reservations that haven't expired."""
        user = User.objects.create_user(username="testuser", email="test@example.com")
        future = timezone.now() + timedelta(days=7)
        
        ReservedUsername.objects.create(
            name="oldname",
            protected=False,
            reserved_by=user,
            expires_at=future,
            reason="previous_username"
        )
        
        self.assertTrue(ReservedUsername.is_reserved("oldname"))
    
    def test_is_reserved_temporary_expired(self):
        """Should NOT detect expired temporary reservations."""
        user = User.objects.create_user(username="testuser", email="test@example.com")
        past = timezone.now() - timedelta(days=1)
        
        ReservedUsername.objects.create(
            name="expired",
            protected=False,
            reserved_by=user,
            expires_at=past,
            reason="previous_username"
        )
        
        self.assertFalse(ReservedUsername.is_reserved("expired"))
    
    def test_is_reserved_fallback_to_settings(self):
        """Should fall back to settings if not in DB."""
        # Assuming 'support' is in RESERVED_USERNAMES_DEFAULT
        self.assertTrue(ReservedUsername.is_reserved("support"))
        self.assertTrue(ReservedUsername.is_reserved("admin"))
    
    def test_cleanup_expired(self):
        """Should delete expired reservations."""
        user = User.objects.create_user(username="testuser", email="test@example.com")
        
        # Create expired reservation
        past = timezone.now() - timedelta(days=1)
        ReservedUsername.objects.create(
            name="expired1",
            expires_at=past,
            reserved_by=user
        )
        
        # Create active reservation
        future = timezone.now() + timedelta(days=7)
        ReservedUsername.objects.create(
            name="active",
            expires_at=future,
            reserved_by=user
        )
        
        # Create permanent
        ReservedUsername.objects.create(
            name="permanent",
            protected=True
        )
        
        # Cleanup
        count = ReservedUsername.cleanup_expired()
        
        self.assertEqual(count, 1)
        self.assertFalse(ReservedUsername.objects.filter(name_ci="expired1").exists())
        self.assertTrue(ReservedUsername.objects.filter(name_ci="active").exists())
        self.assertTrue(ReservedUsername.objects.filter(name_ci="permanent").exists())


class UserUsernameChangeTests(TestCase):
    """Test User username change functionality."""
    
    def setUp(self):
        """Create test user."""
        self.user = User.objects.create_user(
            username="original",
            email="user@example.com",
            password="testpass123"
        )
    
    def test_can_change_username_initially(self):
        """New user should be able to change username within window."""
        self.assertTrue(self.user.can_change_username())
    
    def test_cannot_change_after_first_change(self):
        """Should not allow change after first change (one-time rule)."""
        self.user.change_username("newname")
        self.assertFalse(self.user.can_change_username())
    
    def test_username_change_allowed_until(self):
        """Should calculate correct change window."""
        window_days = getattr(settings, 'USERNAME_CHANGE_WINDOW_DAYS', 7)
        expected = self.user.date_joined + timedelta(days=window_days)
        
        # Allow small time difference due to test execution time
        actual = self.user.username_change_allowed_until
        self.assertIsNotNone(actual)
        self.assertAlmostEqual(
            actual.timestamp(),
            expected.timestamp(),
            delta=1  # 1 second tolerance
        )
    
    def test_username_change_allowed_until_after_change(self):
        """Should return None after username has been changed."""
        self.user.change_username("newname")
        self.assertIsNone(self.user.username_change_allowed_until)
    
    def test_change_username_success(self):
        """Should successfully change username."""
        self.user.change_username("newusername")
        
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "newusername")
        self.assertEqual(self.user.username_change_count, 1)
        self.assertIsNotNone(self.user.username_changed_at)
    
    def test_change_username_creates_reservation(self):
        """Should reserve old username when changed."""
        old_username = self.user.username
        self.user.change_username("newusername")
        
        # Check reservation was created
        self.assertTrue(
            ReservedUsername.objects.filter(
                name_ci=normalize_username(old_username),
                reserved_by=self.user,
                reason="previous_username"
            ).exists()
        )
    
    def test_change_username_reservation_expires(self):
        """Old username reservation should have expiration date."""
        self.user.change_username("newusername")
        
        reservation = ReservedUsername.objects.get(name_ci="original")
        self.assertIsNotNone(reservation.expires_at)
        
        window_days = getattr(settings, 'USERNAME_CHANGE_WINDOW_DAYS', 7)
        expected_expiry = timezone.now() + timedelta(days=window_days)
        
        # Allow small time difference
        self.assertAlmostEqual(
            reservation.expires_at.timestamp(),
            expected_expiry.timestamp(),
            delta=2  # 2 seconds tolerance
        )
    
    def test_change_username_normalizes(self):
        """Should normalize new username."""
        self.user.change_username("NewUserName")
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "newusername")
    
    def test_change_username_validates_format(self):
        """Should validate username format."""
        with self.assertRaises(ValidationError) as cm:
            self.user.change_username("ab")  # too short
        self.assertIn("too_short", str(cm.exception))
    
    def test_change_username_checks_reserved(self):
        """Should reject reserved usernames."""
        ReservedUsername.objects.create(name="reserved", protected=True)
        
        with self.assertRaises(ValidationError) as cm:
            self.user.change_username("reserved")
        self.assertIn("reserved", str(cm.exception))
    
    def test_change_username_checks_taken(self):
        """Should reject username already taken by another user."""
        User.objects.create_user(username="taken", email="other@example.com")
        
        with self.assertRaises(ValidationError) as cm:
            self.user.change_username("taken")
        self.assertIn("taken", str(cm.exception))
    
    def test_change_username_case_insensitive_taken(self):
        """Should reject username taken with different case."""
        User.objects.create_user(username="existing", email="other@example.com")
        
        with self.assertRaises(ValidationError) as cm:
            self.user.change_username("EXISTING")
        self.assertIn("taken", str(cm.exception))
    
    def test_change_username_after_window_fails(self):
        """Should reject change after first change (already used one-time window)."""
        self.user.change_username("firstchange")
        
        with self.assertRaises(ValidationError) as cm:
            self.user.change_username("secondchange")
        self.assertIn("immutable_username", str(cm.exception))


class UserRegistrationTests(TestCase):
    """Test user registration with username validation."""
    
    def test_create_user_normalizes_username(self):
        """Should normalize username on creation."""
        user = User.objects.create_user(
            username="TestUser",
            email="test@example.com",
            password="testpass123"
        )
        self.assertEqual(user.username, "testuser")
    
    def test_create_user_validates_format(self):
        """Should validate username format on creation."""
        with self.assertRaises(ValidationError):
            User.objects.create_user(
                username="ab",  # too short
                email="test@example.com",
                password="testpass123"
            )
    
    def test_create_user_checks_reserved(self):
        """Should reject reserved usernames on creation."""
        ReservedUsername.objects.create(name="admin", protected=True)
        
        with self.assertRaises(ValidationError):
            User.objects.create_user(
                username="admin",
                email="test@example.com",
                password="testpass123"
            )
    
    def test_create_user_enforces_uniqueness(self):
        """Should enforce case-insensitive uniqueness."""
        User.objects.create_user(username="existing", email="user1@example.com")
        
        with self.assertRaises(ValidationError):
            User.objects.create_user(username="EXISTING", email="user2@example.com")


class UserSaveBypassPreventionTests(TestCase):
    """Test that direct save() cannot bypass username policy."""
    
    def test_direct_save_validates_on_create(self):
        """Direct save on new user should validate."""
        user = User(username="ab", email="test@example.com")  # too short
        user.set_password("testpass123")
        
        with self.assertRaises(ValidationError):
            user.save()
    
    def test_direct_save_validates_on_update(self):
        """Direct save on existing user should validate username changes."""
        user = User.objects.create_user(
            username="original",
            email="test@example.com",
            password="testpass123"
        )
        
        # Try to change username directly (should enforce change=True policy)
        user.username = "newname"
        
        # This should work for first change within window
        user.save()
        
        user.refresh_from_db()
        self.assertEqual(user.username, "newname")
        
        # Try second change - should fail
        user.username = "thirdname"
        with self.assertRaises(ValidationError):
            user.save()
    
    def test_queryset_update_bypasses_validation(self):
        """
        KNOWN ISSUE: queryset.update() bypasses model validation.
        This test documents the issue - should be caught in code review.
        """
        user = User.objects.create_user(
            username="original",
            email="test@example.com",
            password="testpass123"
        )
        
        # This WILL bypass validation (documented issue)
        # In production, we audit for this and forbid it
        User.objects.filter(pk=user.pk).update(username="bypassed")
        
        user.refresh_from_db()
        self.assertEqual(user.username, "bypassed")
        
        # This test serves as documentation that queryset.update() must be audited