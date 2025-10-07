from rest_framework import serializers
from .models import User
from .services import check_handle_availability
from django.core.exceptions import ValidationError as DjangoValidationError
from .utils import normalize_username


class UserSerializer(serializers.ModelSerializer):
    """
    Internal use only (e.g., friendships). Includes the UUID `id` for app-internal relations.
    Do NOT use this for public profile responses.
    """
    class Meta:
        model = User
        fields = ("id", "username", "first_name", "last_name", "avatar")


class UsernameAvailabilitySerializer(serializers.Serializer):
    username = serializers.CharField()
    available = serializers.BooleanField(read_only=True)
    reason = serializers.CharField(read_only=True, allow_null=True)

    def to_representation(self, instance):
        username = self.context.get("username", "").strip()
        ok, reason = check_handle_availability(username)
        return {"username": username, "available": ok, "reason": None if ok else reason}


class PublicUserSerializer(serializers.ModelSerializer):
    """
    Public-facing profile. Do NOT include UUID or email here.
    """
    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "avatar")


class MeSerializer(serializers.ModelSerializer):
    """
    Authenticated user's own profile. Username is immutable here.
    ENHANCED: Now includes username_change_allowed_until
    """
    username_change_allowed_until = serializers.DateTimeField(read_only=True)
    
    class Meta:
        model = User
        fields = (
            "username", 
            "first_name", 
            "last_name", 
            "bio", 
            "avatar", 
            "email",
            "username_change_allowed_until"  # NEW: expose change window
        )
        read_only_fields = ("username", "username_change_allowed_until")


class RegisterSerializer(serializers.ModelSerializer):
    """
    Registration serializer. Applies model-level username policy on save().
    """
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "password")

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UsernameChangeSerializer(serializers.Serializer):
    new_username = serializers.CharField()

    def validate(self, attrs):
        user = self.context["request"].user
        new_u = normalize_username(attrs["new_username"].strip())
        cur_u = normalize_username(user.username)
        if new_u == cur_u:
            raise serializers.ValidationError({"new_username": "same_username"})
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        new_username = self.validated_data["new_username"].strip()
        try:
            user.change_username(new_username)
        except DjangoValidationError as e:
            reason = e.messages[0] if e.messages else "invalid"
            raise serializers.ValidationError({"new_username": reason})
        return user