"""
Tests for groups app API endpoints.

Tests all 13 API endpoints with various scenarios.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token

from groups.models import Group, GroupMember
from groups.services import GroupService, InviteLinkService

User = get_user_model()


class GroupAPITests(TestCase):
    """Test Group API endpoints."""
    
    def setUp(self):
        """Set up test client and auth."""
        self.client = APIClient()
        
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        # Get token for authentication
        self.token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
    
    def test_list_groups(self):
        """Test GET /api/v1/groups/ - list user's groups."""
        # Create a group
        group = GroupService.create_group(
            name="My Group",
            type=Group.GroupType.TRIP,
            created_by=self.user
        )
        
        response = self.client.get('/api/v1/groups/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], "My Group")
    
    def test_list_groups_only_shows_user_groups(self):
        """Test list only shows groups user is member of."""
        # Create group for this user
        my_group = GroupService.create_group(
            name="My Group",
            type=Group.GroupType.TRIP,
            created_by=self.user
        )
        
        # Create group for another user
        other_user = User.objects.create_user(username='other', email='other@example.com')
        other_group = GroupService.create_group(
            name="Other Group",
            type=Group.GroupType.TRIP,
            created_by=other_user
        )
        
        response = self.client.get('/api/v1/groups/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], "My Group")
    
    def test_create_group(self):
        """Test POST /api/v1/groups/ - create new group."""
        data = {
            'name': 'New Group',
            'type': 'HOUSEHOLD',
            'simplify_debts': True
        }
        
        response = self.client.post('/api/v1/groups/', data)
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'New Group')
        self.assertEqual(response.data['type'], 'HOUSEHOLD')
        self.assertEqual(response.data['owner']['username'], self.user.username)
        self.assertEqual(response.data['member_count'], 1)
    
    def test_create_group_invalid_type(self):
        """Test creating group with invalid type."""
        data = {
            'name': 'Bad Group',
            'type': 'INVALID_TYPE'
        }
        
        response = self.client.post('/api/v1/groups/', data)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_retrieve_group(self):
        """Test GET /api/v1/groups/{id}/ - get group details."""
        group = GroupService.create_group(
            name="Detail Group",
            type=Group.GroupType.TRIP,
            created_by=self.user
        )
        
        response = self.client.get(f'/api/v1/groups/{group.id}/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Detail Group')
        self.assertIn('members', response.data)
        self.assertIn('user_role', response.data)
        self.assertEqual(response.data['user_role'], 'OWNER')
    
    def test_retrieve_group_not_member(self):
        """Test cannot retrieve group if not a member."""
        other_user = User.objects.create_user(username='other', email='other@example.com')
        group = GroupService.create_group(
            name="Private Group",
            type=Group.GroupType.TRIP,
            created_by=other_user
        )
        
        response = self.client.get(f'/api/v1/groups/{group.id}/')
        
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_update_group(self):
        """Test PUT /api/v1/groups/{id}/ - update group."""
        group = GroupService.create_group(
            name="Original Name",
            type=Group.GroupType.TRIP,
            created_by=self.user
        )
        
        data = {
            'name': 'Updated Name',
            'type': 'PROJECT',
            'simplify_debts': False
        }
        
        response = self.client.put(f'/api/v1/groups/{group.id}/', data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Updated Name')
        self.assertEqual(response.data['type'], 'PROJECT')
        self.assertFalse(response.data['simplify_debts'])
    
    def test_update_group_partial(self):
        """Test PATCH /api/v1/groups/{id}/ - partial update."""
        group = GroupService.create_group(
            name="Original Name",
            type=Group.GroupType.TRIP,
            created_by=self.user
        )
        
        data = {'name': 'New Name Only'}
        
        response = self.client.patch(f'/api/v1/groups/{group.id}/', data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'New Name Only')
        self.assertEqual(response.data['type'], 'TRIP')  # Unchanged
    
    def test_delete_group(self):
        """Test DELETE /api/v1/groups/{id}/ - delete group."""
        group = GroupService.create_group(
            name="To Delete",
            type=Group.GroupType.OTHER,
            created_by=self.user
        )
        
        group_id = group.id
        
        response = self.client.delete(f'/api/v1/groups/{group_id}/')
        
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Group.objects.filter(id=group_id).exists())
    
    def test_delete_group_non_owner(self):
        """Test only owner can delete group."""
        owner = User.objects.create_user(username='owner', email='owner@example.com')
        group = GroupService.create_group(
            name="Protected Group",
            type=Group.GroupType.TRIP,
            created_by=owner
        )
        
        # Add current user as admin (not owner)
        from groups.services import GroupMembershipService
        GroupMembershipService.add_member(
            group=group,
            user_to_add=self.user,
            role=GroupMember.Role.ADMIN,
            added_by=owner
        )
        
        response = self.client.delete(f'/api/v1/groups/{group.id}/')
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class GroupMemberAPITests(TestCase):
    """Test Group Member management API endpoints."""
    
    def setUp(self):
        """Set up test client and auth."""
        self.client = APIClient()
        
        self.owner = User.objects.create_user(
            username='owner',
            email='owner@example.com',
            password='testpass123'
        )
        self.user_to_add = User.objects.create_user(
            username='newmember',
            email='new@example.com',
            password='testpass123'
        )
        
        self.token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        
        self.group = GroupService.create_group(
            name="Test Group",
            type=Group.GroupType.TRIP,
            created_by=self.owner
        )
    
    def test_add_member(self):
        """Test POST /api/v1/groups/{id}/add_member/."""
        data = {
            'user_id': str(self.user_to_add.id),
            'role': 'MEMBER'
        }
        
        response = self.client.post(f'/api/v1/groups/{self.group.id}/add_member/', data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['member_count'], 2)
        self.assertTrue(self.group.is_member(self.user_to_add))
    
    def test_add_member_as_owner_fails(self):
        """Test cannot add member directly as OWNER."""
        data = {
            'user_id': str(self.user_to_add.id),
            'role': 'OWNER'
        }
        
        response = self.client.post(f'/api/v1/groups/{self.group.id}/add_member/', data)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_remove_member(self):
        """Test DELETE /api/v1/groups/{id}/remove_member/{user_id}/."""
        # Add member first
        from groups.services import GroupMembershipService
        GroupMembershipService.add_member(
            group=self.group,
            user_to_add=self.user_to_add,
            role=GroupMember.Role.MEMBER,
            added_by=self.owner
        )
        
        response = self.client.delete(
            f'/api/v1/groups/{self.group.id}/remove_member/{self.user_to_add.id}/'
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(self.group.is_member(self.user_to_add))
    
    def test_change_role(self):
        """Test POST /api/v1/groups/{id}/change_role/."""
        # Add member first
        from groups.services import GroupMembershipService
        GroupMembershipService.add_member(
            group=self.group,
            user_to_add=self.user_to_add,
            role=GroupMember.Role.MEMBER,
            added_by=self.owner
        )
        
        data = {
            'user_id': str(self.user_to_add.id),
            'new_role': 'ADMIN'
        }
        
        response = self.client.post(f'/api/v1/groups/{self.group.id}/change_role/', data)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        member = self.group.get_member(self.user_to_add)
        self.assertEqual(member.role, GroupMember.Role.ADMIN)
    
    def test_transfer_ownership(self):
        """Test POST /api/v1/groups/{id}/transfer_ownership/."""
        # Add member first
        from groups.services import GroupMembershipService
        GroupMembershipService.add_member(
            group=self.group,
            user_to_add=self.user_to_add,
            role=GroupMember.Role.ADMIN,
            added_by=self.owner
        )
        
        data = {
            'new_owner_id': str(self.user_to_add.id)
        }
        
        response = self.client.post(
            f'/api/v1/groups/{self.group.id}/transfer_ownership/',
            data
        )
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.group.refresh_from_db()
        self.assertEqual(self.group.owner, self.user_to_add)
    
    def test_leave_group(self):
        """Test POST /api/v1/groups/{id}/leave/."""
        # Add another user as member
        from groups.services import GroupMembershipService
        GroupMembershipService.add_member(
            group=self.group,
            user_to_add=self.user_to_add,
            role=GroupMember.Role.MEMBER,
            added_by=self.owner
        )
        
        # Switch to member's token
        member_token = Token.objects.create(user=self.user_to_add)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {member_token.key}')
        
        response = self.client.post(f'/api/v1/groups/{self.group.id}/leave/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(self.group.is_member(self.user_to_add))
    
    def test_owner_cannot_leave_group(self):
        """Test owner cannot leave group without transferring ownership."""
        response = self.client.post(f'/api/v1/groups/{self.group.id}/leave/')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class InviteLinkAPITests(TestCase):
    """Test invite link API endpoints."""
    
    def setUp(self):
        """Set up test client and auth."""
        self.client = APIClient()
        
        self.owner = User.objects.create_user(
            username='owner',
            email='owner@example.com',
            password='testpass123'
        )
        self.joiner = User.objects.create_user(
            username='joiner',
            email='joiner@example.com',
            password='testpass123'
        )
        
        self.owner_token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.owner_token.key}')
        
        self.group = GroupService.create_group(
            name="Test Group",
            type=Group.GroupType.TRIP,
            created_by=self.owner
        )
    
    def test_generate_invite_link(self):
        """Test POST /api/v1/groups/{id}/generate_invite/."""
        response = self.client.post(f'/api/v1/groups/{self.group.id}/generate_invite/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('invite_link', response.data)
        self.assertIsNotNone(response.data['invite_link'])
        
        self.group.refresh_from_db()
        self.assertIsNotNone(self.group.invite_link)
    
    def test_revoke_invite_link(self):
        """Test DELETE /api/v1/groups/{id}/revoke_invite/."""
        # Generate link first
        InviteLinkService.generate_invite_link(
            group=self.group,
            generated_by=self.owner
        )
        
        response = self.client.delete(f'/api/v1/groups/{self.group.id}/revoke_invite/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.group.refresh_from_db()
        self.assertIsNone(self.group.invite_link)
    
    def test_join_via_invite_link(self):
        """Test POST /api/v1/groups/join/{invite_link}/."""
        # Generate invite link
        link = InviteLinkService.generate_invite_link(
            group=self.group,
            generated_by=self.owner
        )
        
        # Switch to joiner's credentials
        joiner_token = Token.objects.create(user=self.joiner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {joiner_token.key}')
        
        response = self.client.post(f'/api/v1/groups/join/{link}/')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(self.group.is_member(self.joiner))
        
        # Check role is MEMBER
        member = self.group.get_member(self.joiner)
        self.assertEqual(member.role, GroupMember.Role.MEMBER)
    
    def test_join_via_invalid_link(self):
        """Test joining with invalid link."""
        joiner_token = Token.objects.create(user=self.joiner)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {joiner_token.key}')
        
        response = self.client.post('/api/v1/groups/join/invalid-link-123/')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_authentication_required(self):
        """Test all endpoints require authentication."""
        # Remove credentials
        self.client.credentials()
        
        response = self.client.get('/api/v1/groups/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)