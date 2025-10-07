"""
API tests for username availability and change endpoints.
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from accounts.models import User, ReservedUsername
from accounts.utils import normalize_username


class UsernameAvailabilityAPITests(TestCase):
    """Test /api/v1/username-availability/ endpoint."""
    
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('username-availability')
    
    def test_available_username(self):
        """Should return ok=True for available username."""
        response = self.client.get(self.url, {'username': 'available'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['ok'])
        self.assertIsNone(response.data['reason'])
    
    def test_taken_username(self):
        """Should return ok=False for taken username."""
        User.objects.create_user(username='taken', email='user@example.com')
        
        response = self.client.get(self.url, {'username': 'taken'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['ok'])
        self.assertEqual(response.data['reason'], 'taken')
    
    def test_taken_case_insensitive(self):
        """Should detect taken username regardless of case."""
        User.objects.create_user(username='existing', email='user@example.com')
        
        response = self.client.get(self.url, {'username': 'EXISTING'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['ok'])
        self.assertEqual(response.data['reason'], 'taken')
    
    def test_reserved_username(self):
        """Should return ok=False for reserved username."""
        ReservedUsername.objects.create(name='admin', protected=True)
        
        response = self.client.get(self.url, {'username': 'admin'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['ok'])
        self.assertEqual(response.data['reason'], 'reserved')
    
    def test_too_short_username(self):
        """Should return ok=False for too short username."""
        response = self.client.get(self.url, {'username': 'ab'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['ok'])
        self.assertEqual(response.data['reason'], 'too_short')
    
    def test_too_long_username(self):
        """Should return ok=False for too long username."""
        response = self.client.get(self.url, {'username': 'a' * 33})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['ok'])
        self.assertEqual(response.data['reason'], 'too_long')
    
    def test_invalid_format_username(self):
        """Should return ok=False for invalid format."""
        response = self.client.get(self.url, {'username': 'test@user'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['ok'])
        self.assertEqual(response.data['reason'], 'invalid_format')
    
    def test_empty_username(self):
        """Should handle empty username parameter."""
        response = self.client.get(self.url, {'username': ''})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['ok'])
        self.assertIsNotNone(response.data['reason'])
    
    def test_missing_username_parameter(self):
        """Should handle missing username parameter."""
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['ok'])


class UsernameChangeAPITests(TestCase):
    """Test /api/v1/user/username-change/ endpoint."""
    
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('user-username-change')
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_change_username_success(self):
        """Should successfully change username."""
        response = self.client.post(self.url, {'new_username': 'newusername'})
        
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'newusername')
        self.assertEqual(self.user.username_change_count, 1)
    
    def test_change_username_unauthenticated(self):
        """Should require authentication."""
        self.client.force_authenticate(user=None)
        response = self.client.post(self.url, {'new_username': 'newusername'})
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_change_username_same_as_current(self):
        """Should reject same username."""
        response = self.client.post(self.url, {'new_username': 'testuser'})
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('same_username', str(response.data))
    
    def test_change_username_too_short(self):
        """Should reject too short username."""
        response = self.client.post(self.url, {'new_username': 'ab'})
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('too_short', str(response.data))
    
    def test_change_username_invalid_format(self):
        """Should reject invalid format."""
        response = self.client.post(self.url, {'new_username': 'test@user'})
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('invalid_format', str(response.data))
    
    def test_change_username_reserved(self):
        """Should reject reserved username."""
        ReservedUsername.objects.create(name='admin', protected=True)
        response = self.client.post(self.url, {'new_username': 'admin'})
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('reserved', str(response.data))
    
    def test_change_username_taken(self):
        """Should reject taken username."""
        User.objects.create_user(username='taken', email='other@example.com')
        response = self.client.post(self.url, {'new_username': 'taken'})
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('taken', str(response.data))
    
    def test_change_username_after_first_change(self):
        """Should reject second change (one-time rule)."""
        # First change
        self.client.post(self.url, {'new_username': 'firstchange'})
        
        # Second change should fail
        response = self.client.post(self.url, {'new_username': 'secondchange'})
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('immutable_username', str(response.data))
    
    def test_change_username_normalizes(self):
        """Should normalize username."""
        response = self.client.post(self.url, {'new_username': 'NewUserName'})
        
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'newusername')


class MeSerializerTests(TestCase):
    """Test that MeSerializer exposes username_change_allowed_until."""
    
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('user-me')
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
    
    def test_me_includes_username_change_allowed_until(self):
        """Should include username_change_allowed_until in response."""
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('username_change_allowed_until', response.data)
        self.assertIsNotNone(response.data['username_change_allowed_until'])
    
    def test_me_shows_null_after_change(self):
        """Should show null after username has been changed."""
        self.user.change_username('newname')
        
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['username_change_allowed_until'])


class ConcurrencyTests(TestCase):
    """Test concurrent username claims (race conditions)."""
    
    def test_concurrent_registration_same_username(self):
        """
        Test that two concurrent registrations with same username
        are handled correctly (one succeeds, one fails).
        
        Note: This is a simplified test. In production, use database
        transactions and retry logic.
        """
        from django.db import transaction
        
        # Both try to claim "sameuser"
        user1_created = False
        user2_created = False
        
        try:
            with transaction.atomic():
                user1 = User.objects.create_user(
                    username='sameuser',
                    email='user1@example.com',
                    password='pass123'
                )
                user1_created = True
        except:
            pass
        
        try:
            with transaction.atomic():
                user2 = User.objects.create_user(
                    username='sameuser',
                    email='user2@example.com',
                    password='pass123'
                )
                user2_created = True
        except:
            pass
        
        # Exactly one should succeed
        self.assertTrue(user1_created != user2_created)