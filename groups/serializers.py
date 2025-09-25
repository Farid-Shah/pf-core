from rest_framework import serializers

from accounts.serializers import UserSerializer
from .models import Group, GroupMember

class GroupMemberSerializer(serializers.ModelSerializer):
    """
    Serializer for group members, showing user details and their role.
    """
    user = UserSerializer(read_only=True)

    class Meta:
        model = GroupMember
        fields = [
            'id',
            'user',
            'role',
            'created_at'
        ]


class GroupSerializer(serializers.ModelSerializer):
    """
    Basic serializer for listing groups.
    """
    class Meta:
        model = Group
        fields = [
            'id',
            'name',
            'type',
            'created_at',
        ]


class GroupDetailSerializer(GroupSerializer):
    """
    Detailed serializer for a single group, including its members.
    This serializer is used for create, retrieve, and update operations.
    """
    members = GroupMemberSerializer(many=True, read_only=True)
    # The 'created_by' field will be set in the service layer, not by the serializer.

    class Meta(GroupSerializer.Meta):
        # Inherit fields from GroupSerializer and add more
        fields = GroupSerializer.Meta.fields + [
            'simplify_debts',
            'invite_link',
            'updated_at',
            'members',
        ]
        read_only_fields = ['invite_link']


class GroupMemberCreateSerializer(serializers.Serializer):
    """
    Serializer used specifically for adding a new member to a group.
    It validates the user ID and the role.
    """
    user_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=GroupMember.Role.choices, default=GroupMember.Role.MEMBER)

    def validate_user_id(self, value):
        """
        Check that the user_id exists.
        """
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError("User with this ID does not exist.")
        return value
