"""
Permission matrix:
                    OWNER  ADMIN  MEMBER  VIEWER
View group            ✓      ✓      ✓       ✓
View expenses         ✓      ✓      ✓       ✓
View members          ✓      ✓      ✓       ✓
Create expense        ✓      ✓      ✓       ✗
Edit own expense      ✓      ✓      ✓       ✗
Edit any expense      ✓      ✓      ✗       ✗
Delete expense        ✓      ✓      ✗       ✗
Add member            ✓      ✓      ✗       ✗
Remove member         ✓      ✓      ✗       ✗
Change role           ✓      ✓*     ✗       ✗  (*cannot promote to OWNER/ADMIN)
Update settings       ✓      ✓      ✗       ✗
Delete group          ✓      ✗      ✗       ✗
Transfer ownership    ✓      ✗      ✗       ✗
"""

"""
Group permission system.

Defines:
- Permission types (what actions exist)
- Role-permission mapping (who can do what)
- Permission checker (runtime permission validation)

Role hierarchy (descending power):
OWNER > ADMIN > MEMBER > VIEWER
"""

from enum import Enum
from typing import Optional
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

User = get_user_model()


class GroupPermission(str, Enum):
    """
    All possible permissions within a group.
    
    These 13 permissions align with the test suite expectations.
    
    Organized by category:
    - Read permissions (view_*)
    - Expense permissions (expense_*)
    - Member management (member_*)
    - Group settings (group_*)
    """
    
    # ==================== Read Permissions ====================
    VIEW_GROUP = "view_group"
    VIEW_AUDIT_LOG = "view_audit_log"
    
    # ==================== Expense Permissions ====================
    CREATE_EXPENSE = "create_expense"
    EDIT_ANY_EXPENSE = "edit_any_expense"
    DELETE_ANY_EXPENSE = "delete_any_expense"
    
    # ==================== Member Management ====================
    INVITE_MEMBER = "invite_member"
    REMOVE_MEMBER = "remove_member"
    CHANGE_MEMBER_ROLE = "change_member_role"
    
    # ==================== Invite Link Management ====================
    GENERATE_INVITE_LINK = "generate_invite_link"
    REVOKE_INVITE_LINK = "revoke_invite_link"
    
    # ==================== Group Settings ====================
    UPDATE_GROUP_SETTINGS = "update_group_settings"
    DELETE_GROUP = "delete_group"
    TRANSFER_OWNERSHIP = "transfer_ownership"


def get_role_rank(role: str) -> int:
    """
    Get numeric rank of a role (higher = more powerful).
    
    Args:
        role: Role string (OWNER/ADMIN/MEMBER/VIEWER)
        
    Returns:
        int: 4=OWNER, 3=ADMIN, 2=MEMBER, 1=VIEWER, 0=unknown
    """
    from .models import GroupMember
    
    ranks = {
        GroupMember.Role.OWNER: 4,
        GroupMember.Role.ADMIN: 3,
        GroupMember.Role.MEMBER: 2,
        GroupMember.Role.VIEWER: 1,
    }
    return ranks.get(role, 0)


# ==================== Permission Matrix ====================
# Maps each role to the set of permissions they have

ROLE_PERMISSIONS = {
    'OWNER': {
        # All 13 permissions - full control
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
    },
    
    'ADMIN': {
        # 11 permissions - everything except delete group and transfer ownership
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
    },
    
    'MEMBER': {
        # 3 permissions - basic participation
        GroupPermission.VIEW_GROUP,
        GroupPermission.CREATE_EXPENSE,
        GroupPermission.VIEW_AUDIT_LOG,
    },
    
    'VIEWER': {
        # 2 permissions - read-only access
        GroupPermission.VIEW_GROUP,
        GroupPermission.VIEW_AUDIT_LOG,
    },
}


class PermissionChecker:
    """
    Runtime permission checker for group operations.
    
    Usage:
        checker = PermissionChecker(group, user)
        
        # Check permission
        if checker.can(GroupPermission.DELETE_EXPENSE):
            expense.delete()
        
        # Require permission (raises PermissionDenied)
        checker.require(GroupPermission.CREATE_EXPENSE)
        
        # Check role-specific rules
        if checker.can_modify_role(target_member, new_role):
            target_member.role = new_role
    """
    
    def __init__(self, group, user: User):
        """
        Initialize permission checker.
        
        Args:
            group: Group instance
            user: User instance to check permissions for
        """
        self.group = group
        self.user = user
        self._membership = None
    
    @property
    def membership(self):
        """
        Lazy-load group membership.
        
        Returns:
            GroupMember instance, or False if not a member
        """
        if self._membership is None:
            from .models import GroupMember
            try:
                self._membership = GroupMember.objects.select_related('user').get(
                    group=self.group,
                    user=self.user
                )
            except GroupMember.DoesNotExist:
                self._membership = False  # Not a member
        return self._membership
    
    @property
    def role(self) -> Optional[str]:
        """
        Get user's role in the group.
        
        Returns:
            str: Role value (OWNER/ADMIN/MEMBER/VIEWER) or None
        """
        if self.membership and self.membership is not False:
            return self.membership.role
        return None
    
    def is_member(self) -> bool:
        """Check if user is a member of the group."""
        return self.membership is not False
    
    def is_owner(self) -> bool:
        """Check if user is the group owner."""
        from .models import GroupMember
        return self.role == GroupMember.Role.OWNER
    
    def is_admin_or_higher(self) -> bool:
        """Check if user is admin or owner."""
        from .models import GroupMember
        return self.role in (GroupMember.Role.OWNER, GroupMember.Role.ADMIN)
    
    def can(self, permission: GroupPermission) -> bool:
        """
        Check if user has a specific permission in the group.
        
        Args:
            permission: Permission to check (GroupPermission enum)
            
        Returns:
            bool: True if user has permission, False otherwise
        """
        if not self.is_member():
            return False
        
        role = self.role
        allowed_permissions = ROLE_PERMISSIONS.get(role, set())
        return permission in allowed_permissions
    
    def can_modify_role(self, target_member, new_role: str) -> bool:
        """
        Check if user can change another member's role.
        
        Rules:
        - Must have CHANGE_MEMBER_ROLE permission
        - Cannot change own role
        - Cannot promote/demote someone with higher or equal rank
        - Cannot promote to equal or higher rank than self
        - ADMIN cannot promote to OWNER
        
        Args:
            target_member: GroupMember instance to modify
            new_role: Desired new role (use GroupMember.Role)
            
        Returns:
            bool: True if allowed
        """
        from .models import GroupMember
        
        # Must have base permission
        if not self.can(GroupPermission.CHANGE_MEMBER_ROLE):
            return False
        
        # Cannot change own role
        if target_member.user_id == self.user.id:
            return False
        
        current_role = self.role
        target_current_role = target_member.role
        
        # Cannot modify someone with higher or equal rank
        if get_role_rank(target_current_role) >= get_role_rank(current_role):
            return False
        
        # Cannot promote to equal or higher rank than self
        if get_role_rank(new_role) >= get_role_rank(current_role):
            return False
        
        return True
    
    def can_remove_member(self, target_member) -> bool:
        """
        Check if user can remove another member.
        
        Rules:
        - Must have REMOVE_MEMBER permission
        - Cannot remove self (use leave_group instead)
        - Cannot remove someone with higher or equal rank
        
        Args:
            target_member: GroupMember instance to remove
            
        Returns:
            bool: True if allowed
        """
        # Must have base permission
        if not self.can(GroupPermission.REMOVE_MEMBER):
            return False
        
        # Cannot remove self
        if target_member.user_id == self.user.id:
            return False
        
        # Cannot remove someone with higher or equal rank
        if get_role_rank(target_member.role) >= get_role_rank(self.role):
            return False
        
        return True
    
    def require(self, permission: GroupPermission, message: Optional[str] = None):
        """
        Require a permission or raise PermissionDenied.
        
        Args:
            permission: Required permission
            message: Optional custom error message
            
        Raises:
            PermissionDenied: If user lacks permission
        """
        if not self.can(permission):
            if message:
                raise PermissionDenied(message)
            elif permission == GroupPermission.DELETE_GROUP:
                raise PermissionDenied(
                    f"You do not have permission to delete this group. "
                    f"Only the group owner can delete this group."
                )
            else:
                raise PermissionDenied(
                    f"User '{self.user.username}' lacks permission "
                    f"'{permission.value}' in group '{self.group.name}'"
                )


def check_group_permission(group, user: User, permission: GroupPermission) -> bool:
    """
    Shorthand permission check.
    
    Args:
        group: Group instance
        user: User instance
        permission: Permission to check
        
    Returns:
        bool: True if user has permission
        
    Example:
        if check_group_permission(group, user, GroupPermission.DELETE_EXPENSE):
            expense.delete()
    """
    checker = PermissionChecker(group, user)
    return checker.can(permission)


def require_group_permission(group, user: User, permission: GroupPermission):
    """
    Shorthand permission requirement (raises exception if denied).
    
    Args:
        group: Group instance
        user: User instance
        permission: Required permission
        
    Raises:
        PermissionDenied: If user lacks permission
        
    Example:
        require_group_permission(group, user, GroupPermission.CREATE_EXPENSE)
        # If we reach here, user has permission
    """
    checker = PermissionChecker(group, user)
    checker.require(permission)