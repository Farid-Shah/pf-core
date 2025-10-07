"""
Tests for management commands.
"""
from io import StringIO
from django.test import TestCase
from django.core.management import call_command
from django.conf import settings
from accounts.models import User, ReservedUsername


class SeedReservedUsernamesCommandTests(TestCase):
    """Test seed_reserved_usernames management command."""
    
    def test_seed_creates_reservations(self):
        """Should create reservations from settings."""
        out = StringIO()
        call_command('seed_reserved_usernames', stdout=out)
        
        # Check that some were created
        reserved_count = ReservedUsername.objects.filter(
            protected=True,
            expires_at__isnull=True
        ).count()
        
        self.assertGreater(reserved_count, 0)
        self.assertIn('Created:', out.getvalue())
    
    def test_seed_idempotent(self):
        """Should be idempotent (running twice doesn't duplicate)."""
        # Run once
        call_command('seed_reserved_usernames', stdout=StringIO())
        count_first = ReservedUsername.objects.count()
        
        # Run again
        call_command('seed_reserved_usernames', stdout=StringIO())
        count_second = ReservedUsername.objects.count()
        
        self.assertEqual(count_first, count_second)
    
    def test_seed_with_clear(self):
        """Should clear existing when --clear flag is used."""
        # Create some existing
        ReservedUsername.objects.create(name='existing', protected=True)
        
        # Seed with clear
        out = StringIO()
        call_command('seed_reserved_usernames', '--clear', stdout=out)
        
        self.assertIn('Cleared', out.getvalue())


class NormalizeUsernamesCommandTests(TestCase):
    """Test normalize_usernames management command."""
    
    def test_normalize_fixes_usernames(self):
        """Should normalize non-normalized usernames."""
        # Create user with uppercase (bypassing validation for test)
        user = User(username='TestUser', email='test@example.com')
        user.set_password('pass123')
        # Use queryset.update to bypass validation (simulating old data)
        user.save()
        User.objects.filter(pk=user.pk).update(username='TestUser')
        
        # Run command
        out = StringIO()
        call_command('normalize_usernames', stdout=out)
        
        user.refresh_from_db()
        self.assertEqual(user.username, 'testuser')
        self.assertIn('CHANGE:', out.getvalue())
    
    def test_normalize_dry_run(self):
        """Should preview changes without applying in dry-run mode."""
        user = User(username='TestUser', email='test@example.com')
        user.set_password('pass123')
        user.save()
        User.objects.filter(pk=user.pk).update(username='TestUser')
        
        # Dry run
        out = StringIO()
        call_command('normalize_usernames', '--dry-run', stdout=out)
        
        user.refresh_from_db()
        self.assertEqual(user.username, 'TestUser')  # unchanged
        self.assertIn('DRY RUN', out.getvalue())
        self.assertIn('No changes were applied', out.getvalue())