"""
Tests for groups app models.

Tests:
- Group model properties and methods
- GroupMember model properties and validation
- Database constraints
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from groups.models import Group, GroupMember

User = get_user_model()


class GroupModelTests(TestCase):
    """Test Group model."""
    
    def setUp(self):
        """Set up test data."""
        self.user1 = User.objects.create_user(
            username='user1',
            email='user1@example.com',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@example.com',
            password='testpass123'
        )
        
        self.group = Group.objects.create(
            name="Test Group",
            type=Group.GroupType.TRIP,
            simplify_debts=True
        )
        
        # Add owner
        GroupMember.objects.create(
            group=self.group,
            user=self.user1,
            role=GroupMember.Role.OWNER
        )
    
    def test_group_creation(self):
        """Test creating a group."""
        self.assertEqual(self.group.name, "Test Group")
        self.assertEqual(self.group.type, Group.GroupType.TRIP)
        self.assertTrue(self.group.simplify_debts)
        self.assertIsNotNone(self.group.id)
        self.assertIsNotNone(self.group.created_at)
    
    def test_group_str_representation(self):
        """Test string representation."""
        self.assertEqual(str(self.group), "Test Group")
    
    def test_group_owner_property(self):
        """Test owner property."""
        self.assertEqual(self.group.owner, self.user1)
    
    def test_group_owner_when_no_owner(self):
        """Test owner property when no owner exists."""
        group = Group.objects.create(name="No Owner Group", type=Group.GroupType.OTHER)
        self.assertIsNone(group.owner)
    
    def test_get_member(self):
        """Test getting a member."""
        member = self.group.get_member(self.user1)
        self.assertIsNotNone(member)
        self.assertEqual(member.user, self.user1)
        self.assertEqual(member.role, GroupMember.Role.OWNER)
    
    def test_get_member_not_exists(self):
        """Test getting non-existent member."""
        member = self.group.get_member(self.user2)
        self.assertIsNone(member)
    
    def test_is_member(self):
        """Test is_member method."""
        self.assertTrue(self.group.is_member(self.user1))
        self.assertFalse(self.group.is_member(self.user2))
    
    def test_get_role(self):
        """Test getting user's role."""
        role = self.group.get_role(self.user1)
        self.assertEqual(role, GroupMember.Role.OWNER)
        
        role = self.group.get_role(self.user2)
        self.assertIsNone(role)
    
    def test_member_count(self):
        """Test member count."""
        self.assertEqual(self.group.member_count(), 1)
        
        # Add another member
        GroupMember.objects.create(
            group=self.group,
            user=self.user2,
            role=GroupMember.Role.MEMBER
        )
        
        self.assertEqual(self.group.member_count(), 2)
    
    def test_active_member_count(self):
        """Test active member count (non-viewers)."""
        # Add a viewer
        viewer = User.objects.create_user(username='viewer', email='viewer@example.com')
        GroupMember.objects.create(
            group=self.group,
            user=viewer,
            role=GroupMember.Role.VIEWER
        )
        
        # Owner + viewer = 2 total, but only 1 active
        self.assertEqual(self.group.member_count(), 2)
        self.assertEqual(self.group.active_member_count(), 1)
    
    def test_get_members_by_role(self):
        """Test getting members by role."""
        # Add members with different roles
        admin = User.objects.create_user(username='admin', email='admin@example.com')
        GroupMember.objects.create(group=self.group, user=admin, role=GroupMember.Role.ADMIN)
        
        owners = self.group.get_members_by_role(GroupMember.Role.OWNER)
        self.assertEqual(owners.count(), 1)
        self.assertEqual(owners.first().user, self.user1)
        
        admins = self.group.get_members_by_role(GroupMember.Role.ADMIN)
        self.assertEqual(admins.count(), 1)
        self.assertEqual(admins.first().user, admin)


class GroupMemberModelTests(TestCase):
    """Test GroupMember model."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.group = Group.objects.create(
            name="Test Group",
            type=Group.GroupType.TRIP
        )
    
    def test_member_creation(self):
        """Test creating a member."""
        member = GroupMember.objects.create(
            group=self.group,
            user=self.user,
            role=GroupMember.Role.OWNER
        )
        
        self.assertEqual(member.group, self.group)
        self.assertEqual(member.user, self.user)
        self.assertEqual(member.role, GroupMember.Role.OWNER)
        self.assertIsNotNone(member.id)
        self.assertIsNotNone(member.created_at)
    
    def test_member_str_representation(self):
        """Test string representation."""
        member = GroupMember.objects.create(
            group=self.group,
            user=self.user,
            role=GroupMember.Role.OWNER
        )
        
        expected = f"{self.user.username} - Owner in {self.group.name}"
        self.assertEqual(str(member), expected)
    
    def test_unique_group_user_constraint(self):
        """Test unique (group, user) constraint."""
        GroupMember.objects.create(
            group=self.group,
            user=self.user,
            role=GroupMember.Role.OWNER
        )
        
        # Try to add same user again
        with self.assertRaises(Exception):  # IntegrityError
            GroupMember.objects.create(
                group=self.group,
                user=self.user,
                role=GroupMember.Role.MEMBER
            )
    
    def test_is_owner_property(self):
        """Test is_owner property."""
        owner = GroupMember.objects.create(
            group=self.group,
            user=self.user,
            role=GroupMember.Role.OWNER
        )
        
        member_user = User.objects.create_user(username='member', email='m@example.com')
        member = GroupMember.objects.create(
            group=self.group,
            user=member_user,
            role=GroupMember.Role.MEMBER
        )
        
        self.assertTrue(owner.is_owner)
        self.assertFalse(member.is_owner)
    
    def test_is_admin_or_higher_property(self):
        """Test is_admin_or_higher property."""
        owner = GroupMember.objects.create(
            group=self.group,
            user=self.user,
            role=GroupMember.Role.OWNER
        )
        
        admin_user = User.objects.create_user(username='admin', email='admin@example.com')
        admin = GroupMember.objects.create(
            group=self.group,
            user=admin_user,
            role=GroupMember.Role.ADMIN
        )
        
        member_user = User.objects.create_user(username='member', email='m@example.com')
        member = GroupMember.objects.create(
            group=self.group,
            user=member_user,
            role=GroupMember.Role.MEMBER
        )
        
        self.assertTrue(owner.is_admin_or_higher)
        self.assertTrue(admin.is_admin_or_higher)
        self.assertFalse(member.is_admin_or_higher)
    
    def test_can_create_expenses_property(self):
        """Test can_create_expenses property."""
        member = GroupMember.objects.create(
            group=self.group,
            user=self.user,
            role=GroupMember.Role.MEMBER
        )
        
        viewer_user = User.objects.create_user(username='viewer', email='v@example.com')
        viewer = GroupMember.objects.create(
            group=self.group,
            user=viewer_user,
            role=GroupMember.Role.VIEWER
        )
        
        self.assertTrue(member.can_create_expenses)
        self.assertFalse(viewer.can_create_expenses)
    
    def test_can_manage_members_property(self):
        """Test can_manage_members property."""
        owner = GroupMember.objects.create(
            group=self.group,
            user=self.user,
            role=GroupMember.Role.OWNER
        )
        
        member_user = User.objects.create_user(username='member', email='m@example.com')
        member = GroupMember.objects.create(
            group=self.group,
            user=member_user,
            role=GroupMember.Role.MEMBER
        )
        
        self.assertTrue(owner.can_manage_members)
        self.assertFalse(member.can_manage_members)
    
    def test_rank_property(self):
        """Test rank property."""
        owner = GroupMember(role=GroupMember.Role.OWNER)
        admin = GroupMember(role=GroupMember.Role.ADMIN)
        member = GroupMember(role=GroupMember.Role.MEMBER)
        viewer = GroupMember(role=GroupMember.Role.VIEWER)
        
        self.assertEqual(owner.rank, 4)
        self.assertEqual(admin.rank, 3)
        self.assertEqual(member.rank, 2)
        self.assertEqual(viewer.rank, 1)
    
    def test_clean_method_invalid_role(self):
        """Test clean method with invalid role."""
        member = GroupMember(
            group=self.group,
            user=self.user,
            role='INVALID_ROLE'
        )
        
        with self.assertRaises(ValidationError) as context:
            member.clean()
        
        self.assertIn('role', context.exception.message_dict)