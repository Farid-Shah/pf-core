from rest_framework import serializers
from .models import User

class UserSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for basic public user information.
    """
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'first_name',
            'last_name',
        ]
        read_only_fields = fields


class UserDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for the authenticated user's full profile details.
    Used for the /api/v1/user/me endpoint.
    """
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'date_joined',
        ]
        # 'username' can be updatable or read-only depending on your business logic.
        # For now, we'll make it read-only after creation.
        read_only_fields = ['id', 'username', 'date_joined']
