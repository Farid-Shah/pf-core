"""
Integration tests for groups app.

Tests complete workflows across multiple services and API endpoints.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token

from groups.models import Group, GroupMember
from groups.services import GroupService, GroupMembershipService, InviteLinkService

User = get_user_model()


class GroupLifecycleIntegrationTests(TestCase):
    """Test complete group lifecycle scenarios."""
    
    def setUp(self):
        """Set up test users and client."""
        self.client = APIClient()
        
        # Create users
        self.alice = User.objects.create_user(
            username='alice',
            email='alice@example.com',
            password='testpass123'
        )
        self.bob = User.objects.create_user(
            username='bob',
            email='bob@example.com',
            password='testpass123'
        )
        self.charlie = User.objects.create_user(
            username='charlie',
            email='charlie@example.com',
            password='testpass123'
        )
        self.diana = User.objects.create_user(
            username='diana',
            email='diana@example.com',
            password='testpass123'
        )
        
        # Create tokens
        self.alice_token = Token.objects.create(user=self.alice)
        self.bob_token = Token.objects.create(user=self.bob)
        self.charlie_token = Token.objects.create(user=self.charlie)
        self.diana_token = Token.objects.create(user=self.diana)
    
    def test_complete_group_workflow(self):
        """
        Test complete workflow:
        1. Alice creates a group
        2. Alice adds Bob as admin
        3. Bob adds Charlie as member
        4. Charlie joins and becomes viewer
        5. Bob changes Charlie to member
        6. Alice transfers ownership to Bob
        7. Bob removes Charlie
        8. Bob deletes group
        """
        # 1. Alice creates group
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.alice_token.key}')
        
        response = self.client.post('/api/v1/groups/', {
            'name': 'Summer Trip 2025',
            'type': 'TRIP',
            'simplify_debts': True
        })
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        group_id = response.data['id']
        self.assertEqual(response.data['owner']['username'], 'alice')
        
        # 2. Alice adds Bob as admin
        response = self.client.post(f'/api/v1/groups/{group_id}/add_member/', {
            'user_id': str(self.bob.id),
            'role': 'ADMIN'
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['member_count'], 2)
        
        # 3. Bob adds Charlie as member
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.bob_token.key}')
        
        response = self.client.post(f'/api/v1/groups/{group_id}/add_member/', {
            'user_id': str(self.charlie.id),
            'role': 'MEMBER'
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['member_count'], 3)
        
        # 4. Bob changes Charlie to viewer
        response = self.client.post(f'/api/v1/groups/{group_id}/change_role/', {
            'user_id': str(self.charlie.id),
            'new_role': 'VIEWER'
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        group = Group.objects.get(id=group_id)
        charlie_member = group.get_member(self.charlie)
        self.assertEqual(charlie_member.role, GroupMember.Role.VIEWER)
        
        # 5. Bob changes Charlie back to member
        response = self.client.post(f'/api/v1/groups/{group_id}/change_role/', {
            'user_id': str(self.charlie.id),
            'new_role': 'MEMBER'
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # 6. Alice transfers ownership to Bob
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.alice_token.key}')
        
        response = self.client.post(f'/api/v1/groups/{group_id}/transfer_ownership/', {
            'new_owner_id': str(self.bob.id)
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        group.refresh_from_db()
        self.assertEqual(group.owner, self.bob)
        
        # 7. Bob removes Charlie
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.bob_token.key}')
        
        response = self.client.delete(f'/api/v1/groups/{group_id}/remove_member/{self.charlie.id}/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(group.is_member(self.charlie))
        
        # 8. Bob deletes group
        response = self.client.delete(f'/api/v1/groups/{group_id}/')
        
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Group.objects.filter(id=group_id).exists())
    
    def test_invite_link_workflow(self):
        """
        Test invite link workflow:
        1. Alice creates group
        2. Alice generates invite link
        3. Bob joins via link
        4. Charlie joins via link
        5. Alice revokes link
        6. Diana cannot join
        """
        # 1. Alice creates group
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.alice_token.key}')
        
        group = GroupService.create_group(
            name="Invite Test Group",
            type=Group.GroupType.PROJECT,
            created_by=self.alice
        )
        
        # 2. Generate invite link
        response = self.client.post(f'/api/v1/groups/{group.id}/generate_invite/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        invite_link = response.data['invite_link']
        self.assertIsNotNone(invite_link)
        
        # 3. Bob joins via link
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.bob_token.key}')
        
        response = self.client.post(f'/api/v1/groups/join/{invite_link}/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(group.is_member(self.bob))
        
        # 4. Charlie joins via link
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.charlie_token.key}')
        
        response = self.client.post(f'/api/v1/groups/join/{invite_link}/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(group.is_member(self.charlie))
        
        # 5. Alice revokes link
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.alice_token.key}')
        
        response = self.client.delete(f'/api/v1/groups/{group.id}/revoke_invite/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # 6. Diana cannot join with old link
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.diana_token.key}')
        
        response = self.client.post(f'/api/v1/groups/join/{invite_link}/')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(group.is_member(self.diana))
    
    def test_permission_escalation_prevention(self):
        """
        Test that members cannot escalate their own permissions:
        1. Alice creates group
        2. Alice adds Bob as member
        3. Bob cannot change his own role to admin
        4. Bob cannot add Charlie
        5. Bob cannot remove Alice
        """
        # 1. Alice creates group
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.alice_token.key}')
        
        group = GroupService.create_group(
            name="Security Test",
            type=Group.GroupType.OTHER,
            created_by=self.alice
        )
        
        # 2. Add Bob as member
        GroupMembershipService.add_member(
            group=group,
            user_to_add=self.bob,
            role=GroupMember.Role.MEMBER,
            added_by=self.alice
        )
        
        # 3. Bob cannot change his own role
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.bob_token.key}')
        
        response = self.client.post(f'/api/v1/groups/{group.id}/change_role/', {
            'user_id': str(self.bob.id),
            'new_role': 'ADMIN'
        })
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # 4. Bob cannot add Charlie
        response = self.client.post(f'/api/v1/groups/{group.id}/add_member/', {
            'user_id': str(self.charlie.id),
            'role': 'MEMBER'
        })
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # 5. Bob cannot remove Alice
        response = self.client.delete(f'/api/v1/groups/{group.id}/remove_member/{self.alice.id}/')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_multi_group_membership(self):
        """
        Test user can be member of multiple groups with different roles.
        """
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.alice_token.key}')
        
        # Alice creates group 1 (she's owner)
        group1 = GroupService.create_group(
            name="Group 1",
            type=Group.GroupType.TRIP,
            created_by=self.alice
        )
        
        # Bob creates group 2
        group2 = GroupService.create_group(
            name="Group 2",
            type=Group.GroupType.HOUSEHOLD,
            created_by=self.bob
        )
        
        # Charlie creates group 3
        group3 = GroupService.create_group(
            name="Group 3",
            type=Group.GroupType.PROJECT,
            created_by=self.charlie
        )
        
        # Add Alice to group 2 as admin
        GroupMembershipService.add_member(
            group=group2,
            user_to_add=self.alice,
            role=GroupMember.Role.ADMIN,
            added_by=self.bob
        )
        
        # Add Alice to group 3 as viewer
        GroupMembershipService.add_member(
            group=group3,
            user_to_add=self.alice,
            role=GroupMember.Role.VIEWER,
            added_by=self.charlie
        )
        
        # Alice should see all 3 groups
        response = self.client.get('/api/v1/groups/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)
        
        # Verify Alice's roles in each group
        self.assertEqual(group1.get_role(self.alice), GroupMember.Role.OWNER)
        self.assertEqual(group2.get_role(self.alice), GroupMember.Role.ADMIN)
        self.assertEqual(group3.get_role(self.alice), GroupMember.Role.VIEWER)
    
    def test_concurrent_operations(self):
        """
        Test handling of concurrent operations (simplified test).
        """
        # Alice creates group
        group = GroupService.create_group(
            name="Concurrent Test",
            type=Group.GroupType.OTHER,
            created_by=self.alice
        )
        
        # Add Bob and Charlie
        GroupMembershipService.add_member(
            group=group,
            user_to_add=self.bob,
            role=GroupMember.Role.ADMIN,
            added_by=self.alice
        )
        
        GroupMembershipService.add_member(
            group=group,
            user_to_add=self.charlie,
            role=GroupMember.Role.MEMBER,
            added_by=self.alice
        )
        
        # Both Bob and Alice try to remove Charlie simultaneously
        # (In real scenario, these would be truly concurrent)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.alice_token.key}')
        response1 = self.client.delete(f'/api/v1/groups/{group.id}/remove_member/{self.charlie.id}/')
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.bob_token.key}')
        response2 = self.client.delete(f'/api/v1/groups/{group.id}/remove_member/{self.charlie.id}/')
        
        # One should succeed, one should fail
        responses = [response1.status_code, response2.status_code]
        self.assertIn(status.HTTP_200_OK, responses)
        self.assertIn(status.HTTP_400_BAD_REQUEST, responses)
        
        # Charlie should not be a member
        self.assertFalse(group.is_member(self.charlie))


class RoleHierarchyIntegrationTests(TestCase):
    """Test role hierarchy and permission inheritance."""
    
    def setUp(self):
        """Set up users with different roles."""
        self.owner = User.objects.create_user(username='owner', email='owner@example.com')
        self.admin = User.objects.create_user(username='admin', email='admin@example.com')
        self.member = User.objects.create_user(username='member', email='member@example.com')
        self.viewer = User.objects.create_user(username='viewer', email='viewer@example.com')
        
        self.group = GroupService.create_group(
            name="Role Test Group",
            type=Group.GroupType.TRIP,
            created_by=self.owner
        )
        
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
    
    def test_admin_cannot_remove_owner(self):
        """Test admin cannot remove the owner."""
        from django.core.exceptions import PermissionDenied
        
        with self.assertRaises(PermissionDenied):
            GroupMembershipService.remove_member(
                group=self.group,
                user_to_remove=self.owner,
                removed_by=self.admin
            )
    
    def test_admin_can_remove_member(self):
        """Test admin can remove regular member."""
        # Should not raise exception
        GroupMembershipService.remove_member(
            group=self.group,
            user_to_remove=self.member,
            removed_by=self.admin
        )
        
        self.assertFalse(self.group.is_member(self.member))
    
    def test_member_cannot_change_admin_role(self):
        """Test member cannot change admin's role."""
        from django.core.exceptions import PermissionDenied
        
        admin_member = self.group.get_member(self.admin)
        
        with self.assertRaises(PermissionDenied):
            GroupMembershipService.change_role(
                group=self.group,
                member=admin_member,
                new_role=GroupMember.Role.VIEWER,
                changed_by=self.member
            )
    
    def test_viewer_has_minimal_permissions(self):
        """Test viewer can only view, cannot create expenses."""
        from groups.permissions import PermissionChecker, GroupPermission
        
        checker = PermissionChecker(self.group, self.viewer)
        
        # Can view
        self.assertTrue(checker.can(GroupPermission.VIEW_GROUP))
        self.assertTrue(checker.can(GroupPermission.VIEW_AUDIT_LOG))
        
        # Cannot do anything else
        self.assertFalse(checker.can(GroupPermission.CREATE_EXPENSE))
        self.assertFalse(checker.can(GroupPermission.INVITE_MEMBER))
        self.assertFalse(checker.can(GroupPermission.UPDATE_GROUP_SETTINGS))


class EdgeCaseIntegrationTests(TestCase):
    """Test edge cases and error handling."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com'
        )
    
    def test_create_group_with_special_characters(self):
        """Test creating group with special characters in name."""
        group = GroupService.create_group(
            name="🎉 Summer Trip 2025 🌴",
            type=Group.GroupType.TRIP,
            created_by=self.user
        )
        
        self.assertEqual(group.name, "🎉 Summer Trip 2025 🌴")
    
    def test_create_group_with_very_long_name(self):
        """Test creating group with maximum length name."""
        long_name = "A" * 255
        
        group = GroupService.create_group(
            name=long_name,
            type=Group.GroupType.OTHER,
            created_by=self.user
        )
        
        self.assertEqual(group.name, long_name)
    
    def test_cannot_add_same_user_twice(self):
        """Test adding same user twice fails."""
        from groups.services import AlreadyMemberError
        
        group = GroupService.create_group(
            name="Test Group",
            type=Group.GroupType.OTHER,
            created_by=self.user
        )
        
        other_user = User.objects.create_user(username='other', email='other@example.com')
        
        GroupMembershipService.add_member(
            group=group,
            user_to_add=other_user,
            role=GroupMember.Role.MEMBER,
            added_by=self.user
        )
        
        with self.assertRaises(AlreadyMemberError):
            GroupMembershipService.add_member(
                group=group,
                user_to_add=other_user,
                role=GroupMember.Role.ADMIN,
                added_by=self.user
            )
    
    def test_last_member_leaving_deletes_group(self):
        """Test what happens when last member leaves (owner scenario)."""
        from groups.services import OwnershipTransferError
        
        group = GroupService.create_group(
            name="Solo Group",
            type=Group.GroupType.OTHER,
            created_by=self.user
        )
        
        # Owner cannot leave (would leave group orphaned)
        with self.assertRaises(OwnershipTransferError):
            GroupMembershipService.leave_group(
                group=group,
                user=self.user
            )
    
    def test_regenerate_invite_link_invalidates_old(self):
        """Test regenerating invite link invalidates the old one."""
        group = GroupService.create_group(
            name="Invite Group",
            type=Group.GroupType.TRIP,
            created_by=self.user
        )
        
        # Generate first link
        link1 = InviteLinkService.generate_invite_link(
            group=group,
            generated_by=self.user
        )
        
        # Generate second link
        link2 = InviteLinkService.generate_invite_link(
            group=group,
            generated_by=self.user
        )
        
        # Links should be different
        self.assertNotEqual(link1, link2)
        
        # Old link should not work
        from django.core.exceptions import ValidationError
        other_user = User.objects.create_user(username='other', email='other@example.com')
        
        with self.assertRaises(ValidationError):
            InviteLinkService.join_via_invite_link(
                invite_link=link1,
                user=other_user
            )
        
        # New link should work
        joined_group = InviteLinkService.join_via_invite_link(
            invite_link=link2,
            user=other_user
        )
        
        self.assertEqual(joined_group, group)