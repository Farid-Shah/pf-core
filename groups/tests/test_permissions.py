"""
Tests for groups app permissions.

Tests all 13 granular permissions in the permission system.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model

from groups.models import Group, GroupMember
from groups.services import GroupService, GroupMembershipService
from groups.permissions import PermissionChecker, GroupPermission

User = get_user_model()


class PermissionCheckerTests(TestCase):
    """Test PermissionChecker for all roles."""
    
    def setUp(self):
        """Set up test data with all role types."""
        # Create users for each role
        self.owner = User.objects.create_user(username='owner', email='owner@example.com')
        self.admin = User.objects.create_user(username='admin', email='admin@example.com')
        self.member = User.objects.create_user(username='member', email='member@example.com')
        self.viewer = User.objects.create_user(username='viewer', email='viewer@example.com')
        self.non_member = User.objects.create_user(username='outsider', email='outsider@example.com')
        
        # Create group
        self.group = GroupService.create_group(
            name="Test Group",
            type=Group.GroupType.TRIP,
            created_by=self.owner
        )
        
        # Add members with different roles
        GroupMembershipService.add_member(
            group=self.group,
            user_to_add=self.admin,
            role=GroupMember.Role.ADMIN,
            added_by=self.owner
        )
        GroupMembershipService.add_member(
            group=self.group,
            user_to_add=self.member,
            role=GroupMember.Role.MEMBER,
            added_by=self.owner
        )
        GroupMembershipService.add_member(
            group=self.group,
            user_to_add=self.viewer,
            role=GroupMember.Role.VIEWER,
            added_by=self.owner
        )
    
    def test_view_group_permission(self):
        """Test VIEW_GROUP permission - all members can view."""
        # All members can view
        self.assertTrue(PermissionChecker(self.group, self.owner).can(GroupPermission.VIEW_GROUP))
        self.assertTrue(PermissionChecker(self.group, self.admin).can(GroupPermission.VIEW_GROUP))
        self.assertTrue(PermissionChecker(self.group, self.member).can(GroupPermission.VIEW_GROUP))
        self.assertTrue(PermissionChecker(self.group, self.viewer).can(GroupPermission.VIEW_GROUP))
        
        # Non-member cannot view
        self.assertFalse(PermissionChecker(self.group, self.non_member).can(GroupPermission.VIEW_GROUP))
    
    def test_create_expense_permission(self):
        """Test CREATE_EXPENSE permission - all except viewers."""
        self.assertTrue(PermissionChecker(self.group, self.owner).can(GroupPermission.CREATE_EXPENSE))
        self.assertTrue(PermissionChecker(self.group, self.admin).can(GroupPermission.CREATE_EXPENSE))
        self.assertTrue(PermissionChecker(self.group, self.member).can(GroupPermission.CREATE_EXPENSE))
        
        # Viewer cannot create expenses
        self.assertFalse(PermissionChecker(self.group, self.viewer).can(GroupPermission.CREATE_EXPENSE))
        self.assertFalse(PermissionChecker(self.group, self.non_member).can(GroupPermission.CREATE_EXPENSE))
    
    def test_edit_any_expense_permission(self):
        """Test EDIT_ANY_EXPENSE permission - admin and owner only."""
        self.assertTrue(PermissionChecker(self.group, self.owner).can(GroupPermission.EDIT_ANY_EXPENSE))
        self.assertTrue(PermissionChecker(self.group, self.admin).can(GroupPermission.EDIT_ANY_EXPENSE))
        
        # Member and viewer cannot edit any expense
        self.assertFalse(PermissionChecker(self.group, self.member).can(GroupPermission.EDIT_ANY_EXPENSE))
        self.assertFalse(PermissionChecker(self.group, self.viewer).can(GroupPermission.EDIT_ANY_EXPENSE))
    
    def test_delete_any_expense_permission(self):
        """Test DELETE_ANY_EXPENSE permission - admin and owner only."""
        self.assertTrue(PermissionChecker(self.group, self.owner).can(GroupPermission.DELETE_ANY_EXPENSE))
        self.assertTrue(PermissionChecker(self.group, self.admin).can(GroupPermission.DELETE_ANY_EXPENSE))
        
        self.assertFalse(PermissionChecker(self.group, self.member).can(GroupPermission.DELETE_ANY_EXPENSE))
        self.assertFalse(PermissionChecker(self.group, self.viewer).can(GroupPermission.DELETE_ANY_EXPENSE))
    
    def test_invite_member_permission(self):
        """Test INVITE_MEMBER permission - admin and owner only."""
        self.assertTrue(PermissionChecker(self.group, self.owner).can(GroupPermission.INVITE_MEMBER))
        self.assertTrue(PermissionChecker(self.group, self.admin).can(GroupPermission.INVITE_MEMBER))
        
        self.assertFalse(PermissionChecker(self.group, self.member).can(GroupPermission.INVITE_MEMBER))
        self.assertFalse(PermissionChecker(self.group, self.viewer).can(GroupPermission.INVITE_MEMBER))
    
    def test_remove_member_permission(self):
        """Test REMOVE_MEMBER permission - admin and owner only."""
        self.assertTrue(PermissionChecker(self.group, self.owner).can(GroupPermission.REMOVE_MEMBER))
        self.assertTrue(PermissionChecker(self.group, self.admin).can(GroupPermission.REMOVE_MEMBER))
        
        self.assertFalse(PermissionChecker(self.group, self.member).can(GroupPermission.REMOVE_MEMBER))
        self.assertFalse(PermissionChecker(self.group, self.viewer).can(GroupPermission.REMOVE_MEMBER))
    
    def test_change_member_role_permission(self):
        """Test CHANGE_MEMBER_ROLE permission - admin and owner only."""
        self.assertTrue(PermissionChecker(self.group, self.owner).can(GroupPermission.CHANGE_MEMBER_ROLE))
        self.assertTrue(PermissionChecker(self.group, self.admin).can(GroupPermission.CHANGE_MEMBER_ROLE))
        
        self.assertFalse(PermissionChecker(self.group, self.member).can(GroupPermission.CHANGE_MEMBER_ROLE))
        self.assertFalse(PermissionChecker(self.group, self.viewer).can(GroupPermission.CHANGE_MEMBER_ROLE))
    
    def test_update_group_settings_permission(self):
        """Test UPDATE_GROUP_SETTINGS permission - admin and owner only."""
        self.assertTrue(PermissionChecker(self.group, self.owner).can(GroupPermission.UPDATE_GROUP_SETTINGS))
        self.assertTrue(PermissionChecker(self.group, self.admin).can(GroupPermission.UPDATE_GROUP_SETTINGS))
        
        self.assertFalse(PermissionChecker(self.group, self.member).can(GroupPermission.UPDATE_GROUP_SETTINGS))
        self.assertFalse(PermissionChecker(self.group, self.viewer).can(GroupPermission.UPDATE_GROUP_SETTINGS))
    
    def test_transfer_ownership_permission(self):
        """Test TRANSFER_OWNERSHIP permission - owner only."""
        self.assertTrue(PermissionChecker(self.group, self.owner).can(GroupPermission.TRANSFER_OWNERSHIP))
        
        # Even admin cannot transfer ownership
        self.assertFalse(PermissionChecker(self.group, self.admin).can(GroupPermission.TRANSFER_OWNERSHIP))
        self.assertFalse(PermissionChecker(self.group, self.member).can(GroupPermission.TRANSFER_OWNERSHIP))
        self.assertFalse(PermissionChecker(self.group, self.viewer).can(GroupPermission.TRANSFER_OWNERSHIP))
    
    def test_delete_group_permission(self):
        """Test DELETE_GROUP permission - owner only."""
        self.assertTrue(PermissionChecker(self.group, self.owner).can(GroupPermission.DELETE_GROUP))
        
        # Even admin cannot delete group
        self.assertFalse(PermissionChecker(self.group, self.admin).can(GroupPermission.DELETE_GROUP))
        self.assertFalse(PermissionChecker(self.group, self.member).can(GroupPermission.DELETE_GROUP))
        self.assertFalse(PermissionChecker(self.group, self.viewer).can(GroupPermission.DELETE_GROUP))
    
    def test_generate_invite_link_permission(self):
        """Test GENERATE_INVITE_LINK permission - admin and owner only."""
        self.assertTrue(PermissionChecker(self.group, self.owner).can(GroupPermission.GENERATE_INVITE_LINK))
        self.assertTrue(PermissionChecker(self.group, self.admin).can(GroupPermission.GENERATE_INVITE_LINK))
        
        self.assertFalse(PermissionChecker(self.group, self.member).can(GroupPermission.GENERATE_INVITE_LINK))
        self.assertFalse(PermissionChecker(self.group, self.viewer).can(GroupPermission.GENERATE_INVITE_LINK))
    
    def test_revoke_invite_link_permission(self):
        """Test REVOKE_INVITE_LINK permission - admin and owner only."""
        self.assertTrue(PermissionChecker(self.group, self.owner).can(GroupPermission.REVOKE_INVITE_LINK))
        self.assertTrue(PermissionChecker(self.group, self.admin).can(GroupPermission.REVOKE_INVITE_LINK))
        
        self.assertFalse(PermissionChecker(self.group, self.member).can(GroupPermission.REVOKE_INVITE_LINK))
        self.assertFalse(PermissionChecker(self.group, self.viewer).can(GroupPermission.REVOKE_INVITE_LINK))
    
    def test_view_audit_log_permission(self):
        """Test VIEW_AUDIT_LOG permission - all members can view."""
        self.assertTrue(PermissionChecker(self.group, self.owner).can(GroupPermission.VIEW_AUDIT_LOG))
        self.assertTrue(PermissionChecker(self.group, self.admin).can(GroupPermission.VIEW_AUDIT_LOG))
        self.assertTrue(PermissionChecker(self.group, self.member).can(GroupPermission.VIEW_AUDIT_LOG))
        self.assertTrue(PermissionChecker(self.group, self.viewer).can(GroupPermission.VIEW_AUDIT_LOG))
        
        self.assertFalse(PermissionChecker(self.group, self.non_member).can(GroupPermission.VIEW_AUDIT_LOG))
    
    def test_require_method_success(self):
        """Test require() method when permission is granted."""
        checker = PermissionChecker(self.group, self.owner)
        
        # Should not raise exception
        try:
            checker.require(GroupPermission.DELETE_GROUP)
        except Exception as e:
            self.fail(f"require() raised exception: {e}")
    
    def test_require_method_failure(self):
        """Test require() method when permission is denied."""
        from django.core.exceptions import PermissionDenied
        
        checker = PermissionChecker(self.group, self.member)
        
        with self.assertRaises(PermissionDenied) as context:
            checker.require(GroupPermission.DELETE_GROUP)
        
        self.assertIn("delete this group", str(context.exception))
    
    def test_permission_matrix_owner(self):
        """Test that owner has all 13 permissions."""
        checker = PermissionChecker(self.group, self.owner)
        
        all_permissions = [
            GroupPermission.VIEW_GROUP,
            GroupPermission.CREATE_EXPENSE,
            GroupPermission.EDIT_ANY_EXPENSE,
            GroupPermission.DELETE_ANY_EXPENSE,
            GroupPermission.INVITE_MEMBER,
            GroupPermission.REMOVE_MEMBER,
            GroupPermission.CHANGE_MEMBER_ROLE,
            GroupPermission.UPDATE_GROUP_SETTINGS,
            GroupPermission.TRANSFER_OWNERSHIP,
            GroupPermission.DELETE_GROUP,
            GroupPermission.GENERATE_INVITE_LINK,
            GroupPermission.REVOKE_INVITE_LINK,
            GroupPermission.VIEW_AUDIT_LOG,
        ]
        
        for permission in all_permissions:
            self.assertTrue(checker.can(permission), f"Owner should have {permission.value}")
    
    def test_permission_matrix_admin(self):
        """Test admin permissions (11 out of 13)."""
        checker = PermissionChecker(self.group, self.admin)
        
        # Admin has these permissions
        admin_permissions = [
            GroupPermission.VIEW_GROUP,
            GroupPermission.CREATE_EXPENSE,
            GroupPermission.EDIT_ANY_EXPENSE,
            GroupPermission.DELETE_ANY_EXPENSE,
            GroupPermission.INVITE_MEMBER,
            GroupPermission.REMOVE_MEMBER,
            GroupPermission.CHANGE_MEMBER_ROLE,
            GroupPermission.UPDATE_GROUP_SETTINGS,
            GroupPermission.GENERATE_INVITE_LINK,
            GroupPermission.REVOKE_INVITE_LINK,
            GroupPermission.VIEW_AUDIT_LOG,
        ]
        
        for permission in admin_permissions:
            self.assertTrue(checker.can(permission), f"Admin should have {permission.value}")
        
        # Admin does NOT have these
        admin_forbidden = [
            GroupPermission.TRANSFER_OWNERSHIP,
            GroupPermission.DELETE_GROUP,
        ]
        
        for permission in admin_forbidden:
            self.assertFalse(checker.can(permission), f"Admin should NOT have {permission.value}")
    
    def test_permission_matrix_member(self):
        """Test member permissions (3 out of 13)."""
        checker = PermissionChecker(self.group, self.member)
        
        # Member has these permissions
        member_permissions = [
            GroupPermission.VIEW_GROUP,
            GroupPermission.CREATE_EXPENSE,
            GroupPermission.VIEW_AUDIT_LOG,
        ]
        
        for permission in member_permissions:
            self.assertTrue(checker.can(permission), f"Member should have {permission.value}")
        
        # Member does NOT have these
        member_forbidden = [
            GroupPermission.EDIT_ANY_EXPENSE,
            GroupPermission.DELETE_ANY_EXPENSE,
            GroupPermission.INVITE_MEMBER,
            GroupPermission.REMOVE_MEMBER,
            GroupPermission.CHANGE_MEMBER_ROLE,
            GroupPermission.UPDATE_GROUP_SETTINGS,
            GroupPermission.TRANSFER_OWNERSHIP,
            GroupPermission.DELETE_GROUP,
            GroupPermission.GENERATE_INVITE_LINK,
            GroupPermission.REVOKE_INVITE_LINK,
        ]
        
        for permission in member_forbidden:
            self.assertFalse(checker.can(permission), f"Member should NOT have {permission.value}")
    
    def test_permission_matrix_viewer(self):
        """Test viewer permissions (2 out of 13)."""
        checker = PermissionChecker(self.group, self.viewer)
        
        # Viewer has only these permissions
        viewer_permissions = [
            GroupPermission.VIEW_GROUP,
            GroupPermission.VIEW_AUDIT_LOG,
        ]
        
        for permission in viewer_permissions:
            self.assertTrue(checker.can(permission), f"Viewer should have {permission.value}")
        
        # Viewer cannot even create expenses
        self.assertFalse(checker.can(GroupPermission.CREATE_EXPENSE))