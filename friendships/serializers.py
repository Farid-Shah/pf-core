from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.serializers import UserSerializer
from common.serializers import DynamicFieldsModelSerializer
from .models import FriendRequest, Friendship

User = get_user_model()


class FriendRequestSerializer(DynamicFieldsModelSerializer):
    """
    Serializer for creating and viewing friend requests.
    """
    from_user = UserSerializer(read_only=True)
    to_user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        write_only=True
    )
    to_user_details = UserSerializer(source='to_user', read_only=True)

    class Meta:
        model = FriendRequest
        fields = [
            'id',
            'from_user',
            'to_user',
            'to_user_details',
            'message',
            'status',
            'created_at',
        ]
        read_only_fields = ['id', 'from_user', 'status', 'created_at']

    def validate(self, attrs):
        """
        Check that a request is not being made to oneself.
        """
        request_user = self.context['request'].user
        if request_user == attrs['to_user']:
            raise serializers.ValidationError("You cannot send a friend request to yourself.")
        return attrs

    def create(self, validated_data):
        """
        Set the `from_user` to the currently authenticated user.
        """
        validated_data['from_user'] = self.context['request'].user
        return super().create(validated_data)


class FriendshipSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for established friendships.

    It includes a custom `friend` field that shows the *other* user
    in the friendship, which is useful for a "my friends" list.
    """
    friend = serializers.SerializerMethodField()

    class Meta:
        model = Friendship
        fields = [
            'id',
            'friend',
            'created_at',
        ]

    def get_friend(self, obj):
        """
        Return the user who is not the current authenticated user.
        """
        current_user = self.context['request'].user
        if obj.user_low == current_user:
            return UserSerializer(obj.user_high, context=self.context).data
        else:
            return UserSerializer(obj.user_low, context=self.context).data