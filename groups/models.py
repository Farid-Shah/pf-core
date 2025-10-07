"""
Groups app models.

Defines:
- Group: Expense containers for shared costs
- GroupMember: Membership with role-based access control
"""

import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Group(models.Model):
    """
    Expense container for shared costs.
    
    Types: HOUSEHOLD, TRIP, PROJECT, OTHER
    Members have roles: OWNER, ADMIN, MEMBER, VIEWER
    """
    
    class GroupType(models.TextChoices):
        HOUSEHOLD = 'HOUSEHOLD', 'Household'
        TRIP = 'TRIP', 'Trip'
        PROJECT = 'PROJECT', 'Project'
        OTHER = 'OTHER', 'Other'
    
    # Primary key
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    # Core fields
    name = models.CharField(max_length=255)
    
    type = models.CharField(
        max_length=20,
        choices=GroupType.choices,
        default=GroupType.OTHER
    )
    
    default_currency = models.ForeignKey(
        'currencies.Currency',
        on_delete=models.PROTECT,
        related_name='groups',
        to_field='code',
        help_text="Default currency for expenses in this group"
    )
    
    # Settings
    simplify_debts = models.BooleanField(
        default=True,
        help_text="Whether to simplify debts using graph algorithms"
    )
    
    invite_link = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        help_text="Optional shareable invite link"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'groups_group'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['type']),
            models.Index(fields=['default_currency']),
        ]
    
    def __str__(self):
        return self.name
    
    # ==================== Helper Methods ====================
    
    @property
    def owner(self):
        """
        Get the group owner.
        
        Returns:
            User: Owner user or None if no owner exists
        """
        try:
            return self.members.get(role=GroupMember.Role.OWNER).user
        except GroupMember.DoesNotExist:
            return None
        except GroupMember.MultipleObjectsReturned:
            # Should never happen - log and return first
            return self.members.filter(role=GroupMember.Role.OWNER).first().user
    
    def get_member(self, user):
        """
        Get GroupMember instance for a user.
        
        Args:
            user: User instance
            
        Returns:
            GroupMember or None
        """
        try:
            return self.members.select_related('user').get(user=user)
        except GroupMember.DoesNotExist:
            return None
    
    def is_member(self, user) -> bool:
        """
        Check if user is a member of this group.
        
        Args:
            user: User instance
            
        Returns:
            bool: True if user is a member
        """
        return self.members.filter(user=user).exists()
    
    def get_role(self, user):
        """
        Get user's role in this group.
        
        Args:
            user: User instance
            
        Returns:
            str: Role value (OWNER/ADMIN/MEMBER/VIEWER) or None
        """
        member = self.get_member(user)
        return member.role if member else None
    
    def member_count(self) -> int:
        """Get total number of members."""
        return self.members.count()
    
    def active_member_count(self) -> int:
        """Get number of non-viewer members (can create expenses)."""
        return self.members.exclude(role=GroupMember.Role.VIEWER).count()
    
    def get_members_by_role(self, role: str):
        """
        Get all members with a specific role.
        
        Args:
            role: Role to filter by (use GroupMember.Role enum)
            
        Returns:
            QuerySet of GroupMember instances
        """
        return self.members.filter(role=role).select_related('user')


class GroupMember(models.Model):
    """
    Group membership with role-based access control.
    
    Roles (descending privileges):
    - OWNER: Full control, can transfer ownership, delete group
    - ADMIN: Manage members, expenses, settings (except delete group)
    - MEMBER: Create/edit own expenses, view everything
    - VIEWER: Read-only access
    
    Constraints:
    - Unique (group, user) pair
    - Exactly one OWNER per group (enforced in services)
    """
    
    class Role(models.TextChoices):
        OWNER = 'OWNER', 'Owner'
        ADMIN = 'ADMIN', 'Admin'
        MEMBER = 'MEMBER', 'Member'
        VIEWER = 'VIEWER', 'Viewer'
    
    # Primary key
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    
    # Relationships
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name='members'
    )
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='group_memberships'
    )
    
    # Role
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.MEMBER,
        help_text="User's role in the group"
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When user joined the group"
    )
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'groups_groupmember'
        unique_together = [('group', 'user')]
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['group', 'role']),
            models.Index(fields=['user']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()} in {self.group.name}"
    
    # ==================== Properties ====================
    
    @property
    def is_owner(self) -> bool:
        """Check if this member is the group owner."""
        return self.role == self.Role.OWNER
    
    @property
    def is_admin_or_higher(self) -> bool:
        """Check if this member is admin or owner."""
        return self.role in (self.Role.OWNER, self.Role.ADMIN)
    
    @property
    def can_create_expenses(self) -> bool:
        """Check if this member can create expenses."""
        return self.role != self.Role.VIEWER
    
    @property
    def can_manage_members(self) -> bool:
        """Check if this member can add/remove members."""
        return self.is_admin_or_higher
    
    @property
    def rank(self) -> int:
        """
        Get numeric rank of this member's role.
        
        Returns:
            int: 4=OWNER, 3=ADMIN, 2=MEMBER, 1=VIEWER, 0=unknown
        """
        ranks = {
            self.Role.OWNER: 4,
            self.Role.ADMIN: 3,
            self.Role.MEMBER: 2,
            self.Role.VIEWER: 1,
        }
        return ranks.get(self.role, 0)
    
    # ==================== Validation ====================
    
    def clean(self):
        """Validate before saving."""
        super().clean()
        
        # Validate role is a valid choice
        if self.role not in [r.value for r in self.Role]:
            raise ValidationError({'role': f"Invalid role: {self.role}"})
        
        # Prevent self-referential groups (edge case)
        if hasattr(self, 'group') and hasattr(self, 'user'):
            if self.group.id == self.user.id:
                raise ValidationError("Group ID cannot equal User ID")
    
    def save(self, *args, **kwargs):
        """Override save to run validation."""
        self.full_clean()
        super().save(*args, **kwargs)