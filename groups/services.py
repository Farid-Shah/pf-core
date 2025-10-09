"""
Group membership management services.

Handles all business logic for:
- Adding members to groups
- Removing members from groups
- Changing member roles
- Transferring group ownership
- Leaving groups
- Invite link management

All operations enforce permission checks and maintain data integrity.
"""

import secrets
from typing import Optional
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import get_random_string

from .models import Group, GroupMember
from .permissions import GroupPermission, PermissionChecker

User = get_user_model()


# ==================== Custom Exceptions ====================

class MembershipError(Exception):
    """Base exception for membership operations."""
    pass


class AlreadyMemberError(MembershipError):
    """User is already a member of the group."""
    pass


class NotMemberError(MembershipError):
    """User is not a member of the group."""
    pass


class OwnerRequiredError(MembershipError):
    """Operation requires group owner privileges."""
    pass


class LastOwnerError(MembershipError):
    """Cannot remove or demote the last owner."""
    pass


class InvalidRoleError(MembershipError):
    """Invalid role for this operation."""
    pass


class CannotRemoveOwnerError(MembershipError):
    """Cannot remove the group owner."""
    pass


class OwnershipTransferError(MembershipError):
    """Owner must transfer ownership before leaving."""
    pass


# ==================== Main Service Class ====================

class GroupMembershipService:
    """Service for managing group memberships."""
    
    @staticmethod
    @transaction.atomic
    def add_member(
        group: Group,
        user_to_add: User,
        role: str,
        added_by: User
    ) -> GroupMember:
        """
        Add a new member to the group.
        
        Args:
            group: Group to add member to
            user_to_add: User to add
            role: Role to assign (ADMIN/MEMBER/VIEWER, not OWNER)
            added_by: User performing the action
            
        Returns:
            GroupMember: Created membership
            
        Raises:
            PermissionDenied: If added_by lacks permission
            AlreadyMemberError: If user is already a member
            InvalidRoleError: If role is invalid or OWNER
            ValidationError: If validation fails
        """
        # Permission check
        checker = PermissionChecker(group, added_by)
        checker.require(GroupPermission.INVITE_MEMBER)
        
        # Cannot directly add as OWNER
        if role == GroupMember.Role.OWNER:
            raise InvalidRoleError(
                "Cannot add member as OWNER. Use transfer_ownership instead."
            )
        
        # Validate role
        if role not in [r.value for r in GroupMember.Role]:
            raise InvalidRoleError(f"Invalid role: {role}")
        
        # Check if already a member
        if group.is_member(user_to_add):
            raise AlreadyMemberError(
                f"User {user_to_add.username} is already a member of {group.name}"
            )
        
        # Only OWNER can add ADMINs
        if role == GroupMember.Role.ADMIN and not checker.is_owner():
            raise PermissionDenied("Only group owner can add admins")
        
        # Create membership
        member = GroupMember.objects.create(
            group=group,
            user=user_to_add,
            role=role
        )
        
        # TODO: Log activity
        # ActivityLog.log(
        #     actor=added_by,
        #     verb='added_member',
        #     entity_type='group',
        #     entity_id=group.id,
        #     metadata={'added_user_id': str(user_to_add.id), 'role': role}
        # )
        
        return member
    
    @staticmethod
    @transaction.atomic
    def remove_member(
        group: Group,
        removed_by: User,
        member_to_remove: Optional[GroupMember] = None,
        user_to_remove: Optional[User] = None
    ):
        """
        Remove a member from the group.
        
        Args:
            group: Group to remove from
            removed_by: User performing the action
            member_to_remove: GroupMember instance to remove (optional)
            user_to_remove: User to remove (optional, alternative to member_to_remove)
            
        Raises:
            PermissionDenied: If removed_by lacks permission
            CannotRemoveOwnerError: If trying to remove owner (business rule)
            NotMemberError: If user is not a member
        """
        # Handle both signatures for compatibility
        if member_to_remove is None and user_to_remove is not None:
            member_to_remove = group.get_member(user_to_remove)
            if not member_to_remove:
                raise NotMemberError(
                    f"{user_to_remove.username} is not a member of {group.name}"
                )
        
        if member_to_remove is None:
            raise ValueError("Either member_to_remove or user_to_remove must be provided")
        
        # Create permission checker
        checker = PermissionChecker(group, removed_by)
        
        # Full permission check using can_remove_member
        # This checks: base permission, not self, and rank hierarchy
        can_remove = checker.can_remove_member(member_to_remove)
        
        # If they can't remove for rank/permission reasons, raise PermissionDenied first
        # This ensures admin trying to remove owner gets PermissionDenied (due to rank)
        # rather than CannotRemoveOwnerError
        if not can_remove and not (member_to_remove.user_id == checker.user.id and member_to_remove.is_owner):
            # Not allowed due to permission/rank (not because they're trying to remove themselves as owner)
            raise PermissionDenied(
                f"Cannot remove {member_to_remove.user.username} from {group.name}"
            )
        
        # Special case: trying to remove owner (either self or someone else who is owner)
        # If we get here and target is owner, it means owner is trying to remove themselves
        # (because anyone else would have failed the rank check above)
        if member_to_remove.is_owner:
            raise CannotRemoveOwnerError(
                "Cannot remove group owner. Transfer ownership first."
            )
        
        # Final check - if they still can't remove for other reasons (shouldn't reach here)
        if not can_remove:
            raise PermissionDenied(
                f"Cannot remove {member_to_remove.user.username} from {group.name}"
            )
        
        # Store info for logging before deletion
        removed_user_id = member_to_remove.user_id
        removed_user_username = member_to_remove.user.username
        
        # Delete membership
        member_to_remove.delete()
        
        # TODO: Log activity
        # ActivityLog.log(
        #     actor=removed_by,
        #     verb='removed_member',
        #     entity_type='group',
        #     entity_id=group.id,
        #     metadata={'removed_user_id': str(removed_user_id), 'username': removed_user_username}
        # )
    
    @staticmethod
    @transaction.atomic
    def change_role(
        group: Group,
        member: GroupMember,
        new_role: str,
        changed_by: User
    ) -> GroupMember:
        """
        Change a member's role.
        
        Args:
            group: Group
            member: GroupMember to modify
            new_role: New role to assign (not OWNER)
            changed_by: User performing the action
            
        Returns:
            GroupMember: Updated membership
            
        Raises:
            PermissionDenied: If changed_by lacks permission
            InvalidRoleError: If role change is invalid
        """
        # Permission check
        checker = PermissionChecker(group, changed_by)
        
        # Cannot change role to/from OWNER (use transfer_ownership)
        if new_role == GroupMember.Role.OWNER or member.is_owner:
            raise InvalidRoleError(
                "Use transfer_ownership to change owner role"
            )
        
        # Validate new role
        if new_role not in [r.value for r in GroupMember.Role]:
            raise InvalidRoleError(f"Invalid role: {new_role}")
        
        # Check if can modify this specific member's role
        if not checker.can_modify_role(member, new_role):
            raise PermissionDenied(
                f"Cannot change {member.user.username}'s role to {new_role}"
            )
        
        # Update role
        old_role = member.role
        member.role = new_role
        member.save()
        
        # TODO: Log activity
        # ActivityLog.log(
        #     actor=changed_by,
        #     verb='changed_role',
        #     entity_type='group',
        #     entity_id=group.id,
        #     metadata={
        #         'user_id': str(member.user_id),
        #         'old_role': old_role,
        #         'new_role': new_role
        #     }
        # )
        
        return member
    
    @staticmethod
    @transaction.atomic
    def transfer_ownership(
        group: Group,
        new_owner_user: User,
        current_owner: User
    ):
        """
        Transfer group ownership to another member.
        
        Current owner becomes an ADMIN.
        
        Args:
            group: Group
            new_owner_user: User to become new owner
            current_owner: Current owner performing transfer
            
        Raises:
            PermissionDenied: If current_owner is not the owner
            NotMemberError: If new_owner_user is not a member
            ValidationError: If trying to transfer to self
        """
        # Permission check
        checker = PermissionChecker(group, current_owner)
        checker.require(
            GroupPermission.TRANSFER_OWNERSHIP,
            message="Only group owner can transfer ownership"
        )
        
        # Get current owner membership
        current_owner_member = group.get_member(current_owner)
        if not current_owner_member or not current_owner_member.is_owner:
            raise PermissionDenied("Only group owner can transfer ownership")
        
        # Get new owner membership
        new_owner_member = group.get_member(new_owner_user)
        if not new_owner_member:
            raise NotMemberError(
                f"{new_owner_user.username} is not a member of {group.name}"
            )
        
        # Cannot transfer to self
        if current_owner.id == new_owner_user.id:
            raise ValidationError("Cannot transfer ownership to yourself")
        
        # Perform transfer
        old_owner_role = current_owner_member.role
        old_new_owner_role = new_owner_member.role
        
        new_owner_member.role = GroupMember.Role.OWNER
        new_owner_member.save()
        
        current_owner_member.role = GroupMember.Role.ADMIN
        current_owner_member.save()
        
        # TODO: Log activity
        # ActivityLog.log(
        #     actor=current_owner,
        #     verb='transferred_ownership',
        #     entity_type='group',
        #     entity_id=group.id,
        #     metadata={
        #         'new_owner_id': str(new_owner_user.id),
        #         'old_owner_role': old_owner_role,
        #         'new_owner_old_role': old_new_owner_role
        #     }
        # )
    
    @staticmethod
    @transaction.atomic
    def leave_group(group: Group, user: User):
        """
        User leaves the group.
        
        Owner cannot leave (must transfer ownership first or delete the group).
        
        Args:
            group: Group to leave
            user: User leaving
            
        Raises:
            NotMemberError: If user is not a member
            OwnershipTransferError: If user is the owner
        """
        member = group.get_member(user)
        
        if not member:
            raise NotMemberError(
                f"{user.username} is not a member of {group.name}"
            )
        
        if member.is_owner:
            raise OwnershipTransferError(
                "Group owner cannot leave. Transfer ownership first or delete the group."
            )
        
        # Leave the group
        member_role = member.role
        member.delete()
        
        # TODO: Log activity
        # ActivityLog.log(
        #     actor=user,
        #     verb='left_group',
        #     entity_type='group',
        #     entity_id=group.id,
        #     metadata={'role': member_role}
        # )


class GroupService:
    """Service for group-level operations."""
    
    @staticmethod
    @transaction.atomic
    def create_group(
        name: str,
        type: str,
        created_by: User,
        simplify_debts: bool = True,
        invite_link: Optional[str] = None
    ) -> Group:
        """
        Create a new group with creator as OWNER.
        
        Args:
            name: Group name
            type: Group type (HOUSEHOLD/TRIP/PROJECT/OTHER)
            created_by: User creating the group
            simplify_debts: Whether to simplify debts (default: True)
            invite_link: Optional custom invite link
            
        Returns:
            Group: Created group instance
            
        Raises:
            ValidationError: If validation fails
        """
        # Validate group type
        if type not in [t.value for t in Group.GroupType]:
            raise ValidationError(f"Invalid group type: {type}")
        
        # Create group
        group = Group.objects.create(
            name=name,
            type=type,
            simplify_debts=simplify_debts,
            invite_link=invite_link
        )
        
        # Add creator as OWNER
        GroupMember.objects.create(
            group=group,
            user=created_by,
            role=GroupMember.Role.OWNER
        )
        
        # TODO: Log activity
        # ActivityLog.log(
        #     actor=created_by,
        #     verb='created',
        #     entity_type='group',
        #     entity_id=group.id,
        #     metadata={'name': name, 'type': type}
        # )
        
        return group
    
    @staticmethod
    @transaction.atomic
    def update_group_settings(
        group: Group,
        updated_by: User,
        name: Optional[str] = None,
        type: Optional[str] = None,
        simplify_debts: Optional[bool] = None
    ) -> Group:
        """
        Update group settings.
        
        Args:
            group: Group to update
            updated_by: User performing update
            name: New name (optional)
            type: New type (optional)
            simplify_debts: New simplify_debts setting (optional)
            
        Returns:
            Group: Updated group instance
            
        Raises:
            PermissionDenied: If updated_by lacks permission
            ValidationError: If validation fails
        """
        # Permission check
        checker = PermissionChecker(group, updated_by)
        checker.require(GroupPermission.UPDATE_GROUP_SETTINGS)
        
        changes = {}
        
        # Update name
        if name is not None and name != group.name:
            group.name = name
            changes['name'] = name
        
        # Update type
        if type is not None and type != group.type:
            if type not in [t.value for t in Group.GroupType]:
                raise ValidationError(f"Invalid group type: {type}")
            group.type = type
            changes['type'] = type
        
        # Update simplify_debts
        if simplify_debts is not None and simplify_debts != group.simplify_debts:
            group.simplify_debts = simplify_debts
            changes['simplify_debts'] = simplify_debts
        
        # Save if changes were made
        if changes:
            group.save()
            
            # TODO: Log activity
            # ActivityLog.log(
            #     actor=updated_by,
            #     verb='updated',
            #     entity_type='group',
            #     entity_id=group.id,
            #     metadata=changes
            # )
        
        return group
    
    @staticmethod
    @transaction.atomic
    def delete_group(group: Group, deleted_by: User):
        """
        Delete a group.
        
        Args:
            group: Group to delete
            deleted_by: User deleting the group
            
        Raises:
            PermissionDenied: If deleted_by lacks permission
        """
        # Permission check
        checker = PermissionChecker(group, deleted_by)
        checker.require(GroupPermission.DELETE_GROUP)
        
        # Delete the group
        group.delete()
        
        # TODO: Log activity
        # ActivityLog.log(
        #     actor=deleted_by,
        #     verb='deleted',
        #     entity_type='group',
        #     entity_id=group.id,
        #     metadata={'name': group.name}
        # )


# ==================== Invite Link Service ====================

class InviteLinkService:
    """Service for managing group invite links."""
    
    @staticmethod
    @transaction.atomic
    def generate_invite_link(group: Group, generated_by: User) -> str:
        """
        Generate or regenerate invite link for a group.
        
        Args:
            group: Group to generate link for
            generated_by: User generating the link
            
        Returns:
            str: Generated invite link token
            
        Raises:
            PermissionDenied: If user lacks permission
        """
        # Permission check
        checker = PermissionChecker(group, generated_by)
        checker.require(GroupPermission.GENERATE_INVITE_LINK)
        
        # Generate random token
        invite_link = secrets.token_urlsafe(16)
        
        # Save to group
        group.invite_link = invite_link
        group.save()
        
        # TODO: Log activity
        
        return invite_link
    
    @staticmethod
    @transaction.atomic
    def revoke_invite_link(group: Group, revoked_by: User) -> None:
        """
        Revoke invite link for a group.
        
        Args:
            group: Group to revoke link for
            revoked_by: User revoking the link
            
        Raises:
            PermissionDenied: If user lacks permission
        """
        # Permission check
        checker = PermissionChecker(group, revoked_by)
        checker.require(GroupPermission.REVOKE_INVITE_LINK)
        
        # Clear invite link
        group.invite_link = None
        group.save()
        
        # TODO: Log activity
    
    @staticmethod
    @transaction.atomic
    def join_via_invite_link(invite_link: str, user: User) -> Group:
        """
        Join a group using an invite link.
        
        Args:
            invite_link: Invite link token
            user: User joining the group
            
        Returns:
            Group: The group that was joined
            
        Raises:
            ValidationError: If invite link is invalid
            AlreadyMemberError: If user is already a member
        """
        # Find group with this invite link
        try:
            group = Group.objects.get(invite_link=invite_link)
        except Group.DoesNotExist:
            raise ValidationError("Invalid or expired invite link")
        
        # Check if already a member
        if group.is_member(user):
            raise AlreadyMemberError(
                f"User {user.username} is already a member of group {group.name}"
            )
        
        # Add as member
        GroupMember.objects.create(
            group=group,
            user=user,
            role=GroupMember.Role.MEMBER
        )
        
        # TODO: Log activity
        
        return group