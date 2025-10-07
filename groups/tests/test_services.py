"""
Tests for groups app services.

Tests all business logic in:
- GroupService
- GroupMembershipService
- InviteLinkService
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied

from groups.models import Group, GroupMember
from groups.services import (
    GroupService,
    GroupMembershipService,
    InviteLinkService,
    AlreadyMemberError,
    NotMemberError,
    InvalidRoleError,
    CannotRemoveOwnerError,
    OwnershipTransferError,
)

User = get_user_model()


class GroupServiceTests(TestCase):
    """Test GroupService."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_group(self):
        """Test creating a group."""
        group = GroupService.create_group(
            name="My Group",
            type=Group.GroupType.TRIP,
            created_by=self.user,
            simplify_debts=True
        )
        
        self.assertEqual(group.name, "My Group")
        self.assertEqual(group.type, Group.GroupType.TRIP)
        self.assertTrue(group.simplify_debts)
        self.assertEqual(group.owner, self.user)
        self.assertEqual(group.member_count(), 1)
    
    def test_create_group_invalid_type(self):
        """Test creating group with invalid type."""
        with self.assertRaises(ValidationError):
            GroupService.create_group(
                name="Bad Group",
                type="INVALID_TYPE",
                created_by=self.user
            )
    
    def test_create_group_with_invite_link(self):
        """Test creating group with custom invite link."""
        group = GroupService.create_group(
            name="Invite Group",
            type=Group.GroupType.HOUSEHOLD,
            created_by=self.user,
            invite_link="custom-invite-123"
        )
        
        self.assertEqual(group.invite_link, "custom-invite-123")
    
    def test_update_group_settings(self):
        """Test updating group settings."""
        group = GroupService.create_group(
            name="Original Name",
            type=Group.GroupType.TRIP,
            created_by=self.user
        )
        
        updated = GroupService.update_group_settings(
            group=group,
            updated_by=self.user,
            name="New Name",
            type=Group.GroupType.PROJECT,
            simplify_debts=False
        )
        
        self.assertEqual(updated.name, "New Name")
        self.assertEqual(updated.type, Group.GroupType.PROJECT)
        self.assertFalse(updated.simplify_debts)
    
    def test_update_group_settings_permission_denied(self):
        """Test updating settings without permission."""
        owner = User.objects.create_user(username='owner', email='owner@example.com')
        group = GroupService.create_group(
            name="Group",
            type=Group.GroupType.TRIP,
            created_by=owner
        )
        
        # Non-member tries to update
        with self.assertRaises(PermissionDenied):
            GroupService.update_group_settings(
                group=group,
                updated_by=self.user,
                name="Hacked Name"
            )
    
    def test_delete_group(self):
        """Test deleting a group."""
        group = GroupService.create_group(
            name="To Delete",
            type=Group.GroupType.OTHER,
            created_by=self.user
        )
        
        group_id = group.id
        
        GroupService.delete_group(group=group, deleted_by=self.user)
        
        # Group should no longer exist
        self.assertFalse(Group.objects.filter(id=group_id).exists())
    
    def test_delete_group_permission_denied(self):
        """Test only owner can delete group."""
        owner = User.objects.create_user(username='owner', email='owner@example.com')
        group = GroupService.create_group(
            name="Group",
            type=Group.GroupType.TRIP,
            created_by=owner
        )
        
        # Add member (not owner)
        GroupMembershipService.add_member(
            group=group,
            user_to_add=self.user,
            role=GroupMember.Role.MEMBER,
            added_by=owner
        )
        
        # Member tries to delete
        with self.assertRaises(PermissionDenied):
            GroupService.delete_group(group=group, deleted_by=self.user)


class GroupMembershipServiceTests(TestCase):
    """Test GroupMembershipService."""
    
    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(
            username='owner',
            email='owner@example.com'
        )
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com'
        )
        
        self.group = GroupService.create_group(
            name="Test Group",
            type=Group.GroupType.TRIP,
            created_by=self.owner
        )
    
    def test_add_member(self):
        """Test adding a member."""
        member = GroupMembershipService.add_member(
            group=self.group,
            user_to_add=self.user1,
            role=GroupMember.Role.MEMBER,
            added_by=self.owner
        )
        
        self.assertEqual(member.user, self.user1)
        self.assertEqual(member.role, GroupMember.Role.MEMBER)
        self.assertEqual(self.group.member_count(), 2)
    
    def test_add_member_already_member(self):
        """Test adding user who is already a member."""
        GroupMembershipService.add_member(
            group=self.group,
            user_to_add=self.user1,
            role=GroupMember.Role.MEMBER,
            added_by=self.owner
        )
        
        # Try to add again
        with self.assertRaises(AlreadyMemberError):
            GroupMembershipService.add_member(
                group=self.group,
                user_to_add=self.user1,
                role=GroupMember.Role.MEMBER,
                added_by=self.owner
            )
    
    def test_add_member_as_owner_fails(self):
        """Test cannot add member directly as OWNER."""
        with self.assertRaises(InvalidRoleError):
            GroupMembershipService.add_member(
                group=self.group,
                user_to_add=self.user1,
                role=GroupMember.Role.OWNER,
                added_by=self.owner
            )
    
    def test_add_member_permission_denied(self):
        """Test non-admin cannot add members."""
        # Add user1 as regular member
        GroupMembershipService.add_member(
            group=self.group,
            user_to_add=self.user1,
            role=GroupMember.Role.MEMBER,
            added_by=self.owner
        )
        
        # user1 tries to add user2
        with self.assertRaises(PermissionDenied):
            GroupMembershipService.add_member(
                group=self.group,
                user_to_add=self.user2,
                role=GroupMember.Role.MEMBER,
                added_by=self.user1
            )
    
    def test_remove_member(self):
        """Test removing a member."""
        member = GroupMembershipService.add_member(
            group=self.group,
            user_to_add=self.user1,
            role=GroupMember.Role.MEMBER,
            added_by=self.owner
        )
        
        GroupMembershipService.remove_member(
            group=self.group,
            user_to_remove=self.user1,
            removed_by=self.owner
        )
        
        self.assertEqual(self.group.member_count(), 1)
        self.assertFalse(self.group.is_member(self.user1))
    
    def test_remove_member_not_member(self):
        """Test removing non-member."""
        with self.assertRaises(NotMemberError):
            GroupMembershipService.remove_member(
                group=self.group,
                user_to_remove=self.user1,
                removed_by=self.owner
            )
    
    def test_cannot_remove_owner(self):
        """Test cannot remove owner."""
        with self.assertRaises(CannotRemoveOwnerError):
            GroupMembershipService.remove_member(
                group=self.group,
                user_to_remove=self.owner,
                removed_by=self.owner
            )
    
    def test_change_role(self):
        """Test changing member role."""
        member = GroupMembershipService.add_member(
            group=self.group,
            user_to_add=self.user1,
            role=GroupMember.Role.MEMBER,
            added_by=self.owner
        )
        
        updated = GroupMembershipService.change_role(
            group=self.group,
            member=member,
            new_role=GroupMember.Role.ADMIN,
            changed_by=self.owner
        )
        
        self.assertEqual(updated.role, GroupMember.Role.ADMIN)
    
    def test_change_role_to_owner_fails(self):
        """Test cannot change role to OWNER."""
        member = GroupMembershipService.add_member(
            group=self.group,
            user_to_add=self.user1,
            role=GroupMember.Role.MEMBER,
            added_by=self.owner
        )
        
        with self.assertRaises(InvalidRoleError):
            GroupMembershipService.change_role(
                group=self.group,
                member=member,
                new_role=GroupMember.Role.OWNER,
                changed_by=self.owner
            )
    
    def test_cannot_change_owner_role(self):
        """Test cannot change owner's role."""
        owner_member = self.group.get_member(self.owner)
        
        with self.assertRaises(InvalidRoleError):
            GroupMembershipService.change_role(
                group=self.group,
                member=owner_member,
                new_role=GroupMember.Role.ADMIN,
                changed_by=self.owner
            )
    
    def test_transfer_ownership(self):
        """Test transferring ownership."""
        # Add new member
        GroupMembershipService.add_member(
            group=self.group,
            user_to_add=self.user1,
            role=GroupMember.Role.ADMIN,
            added_by=self.owner
        )
        
        # Transfer ownership
        GroupMembershipService.transfer_ownership(
            group=self.group,
            new_owner_user=self.user1,
            current_owner=self.owner
        )
        
        # Check ownership changed
        self.assertEqual(self.group.owner, self.user1)
        
        # Check roles swapped
        old_owner_member = self.group.get_member(self.owner)
        new_owner_member = self.group.get_member(self.user1)
        
        self.assertEqual(old_owner_member.role, GroupMember.Role.ADMIN)
        self.assertEqual(new_owner_member.role, GroupMember.Role.OWNER)
    
    def test_transfer_ownership_to_non_member(self):
        """Test cannot transfer ownership to non-member."""
        with self.assertRaises(NotMemberError):
            GroupMembershipService.transfer_ownership(
                group=self.group,
                new_owner_user=self.user1,
                current_owner=self.owner
            )
    
    def test_transfer_ownership_by_non_owner(self):
        """Test only owner can transfer ownership."""
        GroupMembershipService.add_member(
            group=self.group,
            user_to_add=self.user1,
            role=GroupMember.Role.ADMIN,
            added_by=self.owner
        )
        
        with self.assertRaises(PermissionDenied):
            GroupMembershipService.transfer_ownership(
                group=self.group,
                new_owner_user=self.user1,
                current_owner=self.user1
            )
    
    def test_leave_group(self):
        """Test leaving a group."""
        # Add member
        GroupMembershipService.add_member(
            group=self.group,
            user_to_add=self.user1,
            role=GroupMember.Role.MEMBER,
            added_by=self.owner
        )
        
        # Member leaves
        GroupMembershipService.leave_group(
            group=self.group,
            user=self.user1
        )
        
        self.assertFalse(self.group.is_member(self.user1))
    
    def test_owner_cannot_leave_group(self):
        """Test owner cannot leave group."""
        with self.assertRaises(OwnershipTransferError):
            GroupMembershipService.leave_group(
                group=self.group,
                user=self.owner
            )


class InviteLinkServiceTests(TestCase):
    """Test InviteLinkService."""
    
    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(
            username='owner',
            email='owner@example.com'
        )
        self.user = User.objects.create_user(
            username='user',
            email='user@example.com'
        )
        
        self.group = GroupService.create_group(
            name="Test Group",
            type=Group.GroupType.TRIP,
            created_by=self.owner
        )
    
    def test_generate_invite_link(self):
        """Test generating invite link."""
        link = InviteLinkService.generate_invite_link(
            group=self.group,
            generated_by=self.owner
        )
        
        self.assertIsNotNone(link)
        self.assertEqual(self.group.invite_link, link)
    
    def test_regenerate_invite_link(self):
        """Test regenerating invite link."""
        link1 = InviteLinkService.generate_invite_link(
            group=self.group,
            generated_by=self.owner
        )
        
        link2 = InviteLinkService.generate_invite_link(
            group=self.group,
            generated_by=self.owner
        )
        
        self.assertNotEqual(link1, link2)
    
    def test_revoke_invite_link(self):
        """Test revoking invite link."""
        InviteLinkService.generate_invite_link(
            group=self.group,
            generated_by=self.owner
        )
        
        InviteLinkService.revoke_invite_link(
            group=self.group,
            revoked_by=self.owner
        )
        
        self.group.refresh_from_db()
        self.assertIsNone(self.group.invite_link)
    
    def test_join_via_invite_link(self):
        """Test joining group via invite link."""
        link = InviteLinkService.generate_invite_link(
            group=self.group,
            generated_by=self.owner
        )
        
        joined_group = InviteLinkService.join_via_invite_link(
            invite_link=link,
            user=self.user
        )
        
        self.assertEqual(joined_group, self.group)
        self.assertTrue(self.group.is_member(self.user))
        
        # Check role is MEMBER by default
        member = self.group.get_member(self.user)
        self.assertEqual(member.role, GroupMember.Role.MEMBER)
    
    def test_join_via_invalid_link(self):
        """Test joining with invalid link."""
        with self.assertRaises(ValidationError):
            InviteLinkService.join_via_invite_link(
                invite_link="invalid-link-123",
                user=self.user
            )
    
    def test_join_when_already_member(self):
        """Test joining when already a member."""
        link = InviteLinkService.generate_invite_link(
            group=self.group,
            generated_by=self.owner
        )
        
        # Join first time
        InviteLinkService.join_via_invite_link(
            invite_link=link,
            user=self.user
        )
        
        # Try to join again
        with self.assertRaises(AlreadyMemberError):
            InviteLinkService.join_via_invite_link(
                invite_link=link,
                user=self.user
            )