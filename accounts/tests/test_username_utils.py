"""
Unit tests for username utility functions.
"""
from django.test import TestCase
from accounts.utils import (
    normalize_username,
    is_username_format_valid,
    get_username_error_message
)


class NormalizeUsernameTests(TestCase):
    """Test username normalization function."""
    
    def test_normalize_lowercase(self):
        """Should convert to lowercase."""
        self.assertEqual(normalize_username("JohnDoe"), "johndoe")
        self.assertEqual(normalize_username("ADMIN"), "admin")
        self.assertEqual(normalize_username("Test123"), "test123")
    
    def test_normalize_strip_whitespace(self):
        """Should strip leading/trailing whitespace."""
        self.assertEqual(normalize_username("  username  "), "username")
        self.assertEqual(normalize_username("\tusername\n"), "username")
        self.assertEqual(normalize_username("   admin   "), "admin")
    
    def test_normalize_unicode_nfkc(self):
        """Should apply NFKC normalization."""
        # NFKC normalization examples
        self.assertEqual(normalize_username("ℌello"), "hello")  # ℌ → h
        self.assertEqual(normalize_username("Ⅸ"), "ix")  # Roman IX → ix
    
    def test_normalize_preserves_internal_spaces(self):
        """Should preserve internal characters (though spaces aren't valid in username regex)."""
        # Note: This will normalize, but validation will reject spaces
        result = normalize_username("john doe")
        self.assertEqual(result, "john doe")
    
    def test_normalize_none(self):
        """Should handle None input."""
        self.assertIsNone(normalize_username(None))
    
    def test_normalize_empty_string(self):
        """Should handle empty string."""
        self.assertEqual(normalize_username(""), "")
    
    def test_normalize_underscores_hyphens(self):
        """Should preserve underscores (valid in username)."""
        self.assertEqual(normalize_username("john_doe"), "john_doe")
        self.assertEqual(normalize_username("test_123"), "test_123")


class UsernameFormatValidationTests(TestCase):
    """Test username format validation function."""
    
    def test_valid_usernames(self):
        """Should accept valid usernames."""
        valid_names = [
            "abc",
            "test123",
            "john_doe",
            "user_123",
            "a" * 32,  # max length
        ]
        for username in valid_names:
            is_valid, error = is_username_format_valid(username)
            self.assertTrue(is_valid, f"{username} should be valid")
            self.assertIsNone(error, f"{username} should have no error")
    
    def test_too_short(self):
        """Should reject usernames shorter than 3 characters."""
        is_valid, error = is_username_format_valid("ab")
        self.assertFalse(is_valid)
        self.assertEqual(error, "too_short")
        
        is_valid, error = is_username_format_valid("a")
        self.assertFalse(is_valid)
        self.assertEqual(error, "too_short")
    
    def test_too_long(self):
        """Should reject usernames longer than 32 characters."""
        is_valid, error = is_username_format_valid("a" * 33)
        self.assertFalse(is_valid)
        self.assertEqual(error, "too_long")
    
    def test_empty_username(self):
        """Should reject empty usernames."""
        is_valid, error = is_username_format_valid("")
        self.assertFalse(is_valid)
        self.assertEqual(error, "username_required")
        
        is_valid, error = is_username_format_valid(None)
        self.assertFalse(is_valid)
        self.assertEqual(error, "username_required")
    
    def test_invalid_characters(self):
        """Should reject usernames with invalid characters."""
        invalid_names = [
            "john doe",  # space
            "test@123",  # @
            "user.name",  # dot
            "test-user",  # hyphen (not in default regex)
            "admin!",  # special char
            "user#123",  # hash
        ]
        for username in invalid_names:
            is_valid, error = is_username_format_valid(username)
            self.assertFalse(is_valid, f"{username} should be invalid")
            self.assertEqual(error, "invalid_format", f"{username} should fail format check")
    
    def test_uppercase_normalized(self):
        """Should validate after normalization (lowercase)."""
        is_valid, error = is_username_format_valid("TestUser123")
        self.assertTrue(is_valid)
        self.assertIsNone(error)


class ErrorMessageTests(TestCase):
    """Test error message mapping."""
    
    def test_all_error_codes_have_messages(self):
        """Should have messages for all known error codes."""
        error_codes = [
            'username_required',
            'too_short',
            'too_long',
            'invalid_format',
            'reserved',
            'taken',
            'immutable_username',
            'same_username',
        ]
        
        for code in error_codes:
            message = get_username_error_message(code)
            self.assertIsNotNone(message, f"Code '{code}' should have a message")
            self.assertNotEqual(message, 'Invalid username.', f"Code '{code}' should not use default message")
            # Just verify we got a non-empty string
            self.assertTrue(len(message) > 0, f"Code '{code}' should have a non-empty message")
    
    def test_unknown_error_code(self):
        """Should return default message for unknown codes."""
        message = get_username_error_message('unknown_code_xyz')
        self.assertEqual(message, 'Invalid username.')
    
    def test_specific_error_messages(self):
        """Test specific error messages are reasonable."""
        # Just verify messages contain relevant keywords
        
        # username_required: should mention "username" and "required"
        required_msg = get_username_error_message('username_required').lower()
        self.assertIn('username', required_msg)
        self.assertIn('required', required_msg)
        
        # too_short: should mention characters/length
        short_msg = get_username_error_message('too_short').lower()
        self.assertTrue('at least' in short_msg or 'character' in short_msg)
        
        # too_long: should mention characters/length
        long_msg = get_username_error_message('too_long').lower()
        self.assertTrue('at most' in long_msg or 'character' in long_msg)
        
        # invalid_format: should mention what's allowed (letters, numbers, etc.)
        format_msg = get_username_error_message('invalid_format').lower()
        self.assertTrue(
            'letter' in format_msg or 
            'number' in format_msg or 
            'contain' in format_msg,
            f"Format message should describe allowed characters: {format_msg}"
        )
        
        # reserved: should mention "reserved"
        reserved_msg = get_username_error_message('reserved').lower()
        self.assertIn('reserved', reserved_msg)
        
        # taken: should mention "taken" or "already"
        taken_msg = get_username_error_message('taken').lower()
        self.assertTrue('taken' in taken_msg or 'already' in taken_msg)
        
        # immutable_username: should mention change-related concepts
        immutable_msg = get_username_error_message('immutable_username').lower()
        self.assertTrue(
            'change' in immutable_msg or 
            'one-time' in immutable_msg or 
            'already' in immutable_msg or
            'used' in immutable_msg
        )
        
        # same_username: should mention "same" or "current"
        same_msg = get_username_error_message('same_username').lower()
        self.assertTrue('same' in same_msg or 'current' in same_msg)