from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Group, GroupMember
from .serializers import (
    GroupSerializer,
    GroupDetailSerializer,
    GroupMemberCreateSerializer,
    GroupMemberSerializer,
)

User = get_user_model()

class GroupViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Groups and their members.

    Endpoints:
    - GET /api/v1/groups/ - List groups the user is a member of.
    - POST /api/v1/groups/ - Create a new group.
    - GET /api/v1/groups/{id}/ - Retrieve a group's details.
    - PUT /api/v1/groups/{id}/ - Update a group.
    - POST /api/v1/groups/{id}/members/ - Add a member to a group.
    - DELETE /api/v1/groups/{id}/members/{user_id}/ - Remove a member from a group.
    """
    permission_classes = [permissions.IsAuthenticated] # We will add custom permissions later

    def get_queryset(self):
        """
        Users should only see groups they are a member of.
        """
        return self.request.user.group_memberships.select_related('group').all().values_list('group', flat=True)

    def get_serializer_class(self):
        """
        Return different serializers for list and detail views.
        """
        if self.action == 'list':
            return GroupSerializer
        if self.action in ['add_member', 'remove_member']:
            return GroupMemberCreateSerializer
        return GroupDetailSerializer

    def perform_create(self, serializer):
        """
        When creating a group, automatically add the creator as the 'OWNER'.
        This logic should ideally be in a service function.
        """
        with transaction.atomic():
            group = serializer.save()
            GroupMember.objects.create(
                group=group,
                user=self.request.user,
                role=GroupMember.Role.OWNER
            )

    @action(detail=True, methods=['post'], url_path='members')
    def add_member(self, request, pk=None):
        """
        Add a member to a specific group.
        """
        group = self.get_object()
        # TODO: Add permission check: Only OWNER or ADMIN can add members.

        serializer = GroupMemberCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user_id = serializer.validated_data['user_id']
        role = serializer.validated_data['role']

        if GroupMember.objects.filter(group=group, user_id=user_id).exists():
            return Response({'error': 'User is already a member of this group.'}, status=status.HTTP_400_BAD_REQUEST)

        member = GroupMember.objects.create(group=group, user_id=user_id, role=role)
        return Response(GroupMemberSerializer(member).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path='members/(?P<user_id>[^/.]+)')
    def remove_member(self, request, pk=None, user_id=None):
        """
        Remove a member from a specific group.
        """
        group = self.get_object()
        # TODO: Add permission check: Only OWNER or ADMIN can remove members.
        # TODO: Add logic to prevent removing the last OWNER.

        try:
            member = GroupMember.objects.get(group=group, user_id=user_id)
        except GroupMember.DoesNotExist:
            return Response({'error': 'User is not a member of this group.'}, status=status.HTTP_404_NOT_FOUND)

        if member.role == GroupMember.Role.OWNER and GroupMember.objects.filter(group=group, role=GroupMember.Role.OWNER).count() == 1:
            return Response({'error': 'Cannot remove the last owner of the group.'}, status=status.HTTP_400_BAD_REQUEST)

        member.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)