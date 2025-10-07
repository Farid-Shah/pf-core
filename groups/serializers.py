"""
Group API serializers.

Organized by purpose:
1. Read serializers (display data)
2. Write serializers (create/update operations)
3. Action serializers (specific operations like change role, transfer ownership)
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model

from accounts.serializers import UserSerializer
from .models import Group, GroupMember

User = get_user_model()


# ==================== Read Serializers (Display) ====================

class GroupMemberSerializer(serializers.ModelSerializer):
    """
    Serializer for displaying group members.
    
    Shows user details and their role.
    Used in: group detail view, member lists
    """
    user = UserSerializer(read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    
    class Meta:
        model = GroupMember
        fields = [
            'id',
            'user',
            'role',
            'role_display',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class GroupSerializer(serializers.ModelSerializer):
    """
    Basic serializer for listing groups.
    
    Lightweight - only essential fields.
    Used in: list view, select dropdowns
    """
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    member_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Group
        fields = [
            'id',
            'name',
            'type',
            'type_display',
            'member_count',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']
    
    def to_representation(self, instance):
        """Add member count dynamically."""
        data = super().to_representation(instance)
        data['member_count'] = instance.member_count()
        return data


class GroupDetailSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for a single group.
    
    Includes members, settings, and all metadata.
    Used in: retrieve view, after create/update
    """
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    members = GroupMemberSerializer(many=True, read_only=True)
    owner = UserSerializer(read_only=True)
    member_count = serializers.IntegerField(read_only=True)
    active_member_count = serializers.IntegerField(read_only=True)
    
    # User's role in this group (contextual)
    user_role = serializers.SerializerMethodField()
    user_permissions = serializers.SerializerMethodField()
    
    class Meta:
        model = Group
        fields = [
            'id',
            'name',
            'type',
            'type_display',
            'simplify_debts',
            'invite_link',
            'members',
            'owner',
            'member_count',
            'active_member_count',
            'user_role',
            'user_permissions',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'invite_link',
            'members',
            'owner',
            'member_count',
            'active_member_count',
            'user_role',
            'user_permissions',
            'created_at',
            'updated_at',
        ]
    
    def get_user_role(self, obj):
        """Get current user's role in the group."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.get_role(request.user)
        return None
    
    def get_user_permissions(self, obj):
        """Get current user's permissions in the group."""
        from .permissions import PermissionChecker, GroupPermission
        
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return []
        
        checker = PermissionChecker(obj, request.user)
        
        # Return list of permissions user has
        permissions = []
        for perm in GroupPermission:
            if checker.can(perm):
                permissions.append(perm.value)
        
        return permissions
    
    def to_representation(self, instance):
        """Add dynamic counts."""
        data = super().to_representation(instance)
        data['member_count'] = instance.member_count()
        data['active_member_count'] = instance.active_member_count()
        return data


# ==================== Write Serializers (Create/Update) ====================

class GroupCreateSerializer(serializers.Serializer):
    """
    Serializer for creating a new group.
    
    POST /api/v1/groups/
    """
    name = serializers.CharField(
        max_length=255,
        help_text="Group name"
    )
    
    type = serializers.ChoiceField(
        choices=Group.GroupType.choices,
        default=Group.GroupType.OTHER,
        help_text="Group type: HOUSEHOLD, TRIP, PROJECT, or OTHER"
    )
    
    simplify_debts = serializers.BooleanField(
        default=True,
        help_text="Whether to simplify debts using graph algorithms"
    )
    
    invite_link = serializers.CharField(
        max_length=255,
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Optional custom invite link token"
    )
    
    def validate_name(self, value):
        """Validate name is not empty after stripping."""
        if not value.strip():
            raise serializers.ValidationError("Group name cannot be empty")
        return value.strip()


class GroupUpdateSerializer(serializers.Serializer):
    """
    Serializer for updating group settings.
    
    PUT/PATCH /api/v1/groups/{id}/
    """
    name = serializers.CharField(
        max_length=255,
        required=False,
        help_text="Group name"
    )
    
    type = serializers.ChoiceField(
        choices=Group.GroupType.choices,
        required=False,
        help_text="Group type"
    )
    
    simplify_debts = serializers.BooleanField(
        required=False,
        help_text="Whether to simplify debts"
    )
    
    def validate_name(self, value):
        """Validate name is not empty."""
        if not value.strip():
            raise serializers.ValidationError("Group name cannot be empty")
        return value.strip()


# ==================== Member Management Serializers ====================

class GroupMemberCreateSerializer(serializers.Serializer):
    """
    Serializer for adding a new member to a group.
    
    POST /api/v1/groups/{id}/add_member/
    """
    user_id = serializers.UUIDField(
        help_text="ID of user to add"
    )
    
    role = serializers.ChoiceField(
        choices=GroupMember.Role.choices,
        default=GroupMember.Role.MEMBER,
        help_text="Role to assign: ADMIN, MEMBER, or VIEWER (not OWNER)"
    )
    
    def validate_user_id(self, value):
        """Validate user exists."""
        try:
            User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this ID does not exist")
        return value
    
    def validate_role(self, value):
        """Prevent direct assignment of OWNER role."""
        if value == GroupMember.Role.OWNER:
            raise serializers.ValidationError(
                "Cannot add member as OWNER. Use transfer_ownership endpoint instead."
            )
        return value


class ChangeRoleSerializer(serializers.Serializer):
    """
    Serializer for changing a member's role.
    
    POST /api/v1/groups/{id}/change_role/
    """
    user_id = serializers.UUIDField(
        help_text="ID of member whose role to change"
    )
    
    new_role = serializers.ChoiceField(
        choices=GroupMember.Role.choices,
        help_text="New role to assign (not OWNER)"
    )
    
    def validate_user_id(self, value):
        """Validate user exists."""
        try:
            User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this ID does not exist")
        return value
    
    def validate_new_role(self, value):
        """Prevent changing to/from OWNER via this endpoint."""
        if value == GroupMember.Role.OWNER:
            raise serializers.ValidationError(
                "Cannot change role to OWNER. Use transfer_ownership endpoint instead."
            )
        return value


class TransferOwnershipSerializer(serializers.Serializer):
    """
    Serializer for transferring group ownership.
    
    POST /api/v1/groups/{id}/transfer_ownership/
    """
    new_owner_id = serializers.UUIDField(
        help_text="ID of member to become new owner"
    )
    
    def validate_new_owner_id(self, value):
        """Validate user exists."""
        try:
            User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this ID does not exist")
        return value


# ==================== Invite Link Serializers ====================

class InviteLinkSerializer(serializers.Serializer):
    """
    Serializer for invite link operations.
    
    POST /api/v1/groups/{id}/generate_invite/
    DELETE /api/v1/groups/{id}/revoke_invite/
    """
    invite_link = serializers.CharField(
        max_length=255,
        read_only=True,
        help_text="Generated invite link token"
    )


class JoinViaInviteSerializer(serializers.Serializer):
    """
    Serializer for joining a group via invite link.
    
    POST /api/v1/groups/join/{invite_link}/
    """
    # No input fields needed - invite_link comes from URL
    # This serializer is for documentation purposes
    pass


# ==================== Nested Serializers (for other apps) ====================

class GroupMinimalSerializer(serializers.ModelSerializer):
    """
    Minimal group info for embedding in other serializers.
    
    Used in: Expense serializers, Payment serializers, etc.
    """
    class Meta:
        model = Group
        fields = ['id', 'name', 'type']
        read_only_fields = fields


class GroupMemberMinimalSerializer(serializers.ModelSerializer):
    """
    Minimal member info for embedding.
    
    Used in: Activity logs, notifications, etc.
    """
    username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = GroupMember
        fields = ['id', 'username', 'role']
        read_only_fields = fields