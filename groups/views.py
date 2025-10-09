"""
Group API views.

Thin viewset that delegates all business logic to services.
Responsibilities:
1. Parse HTTP requests
2. Validate input format
3. Call service methods
4. Handle exceptions → HTTP status codes
5. Format HTTP responses
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Group, GroupMember
from .serializers import (
    GroupSerializer,
    GroupDetailSerializer,
    GroupMemberSerializer,
    GroupMemberCreateSerializer,
    GroupCreateSerializer,
    GroupUpdateSerializer,
    ChangeRoleSerializer,
    TransferOwnershipSerializer,
    InviteLinkSerializer,
)
from .services import (
    GroupService,
    GroupMembershipService,
    InviteLinkService,
    AlreadyMemberError,
    NotMemberError,
    OwnerRequiredError,
    InvalidRoleError,
    CannotRemoveOwnerError,
    OwnershipTransferError,
)
from .permissions import PermissionChecker, GroupPermission

User = get_user_model()


class IsGroupMember(permissions.BasePermission):
    """
    Permission class: User must be a member of the group.
    """
    
    def has_object_permission(self, request, view, obj):
        """Check if user is a member of the group."""
        if isinstance(obj, Group):
            return obj.is_member(request.user)
        elif isinstance(obj, GroupMember):
            return obj.group.is_member(request.user)
        return False


class GroupViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Groups and their members.

    Endpoints:
    - GET    /api/v1/groups/                          - List user's groups
    - POST   /api/v1/groups/                          - Create a group
    - GET    /api/v1/groups/{id}/                     - Retrieve group details
    - PUT    /api/v1/groups/{id}/                     - Update group
    - DELETE /api/v1/groups/{id}/                     - Delete group
    - POST   /api/v1/groups/{id}/add_member/          - Add a member
    - DELETE /api/v1/groups/{id}/remove_member/{user_id}/ - Remove a member
    - POST   /api/v1/groups/{id}/change_role/         - Change member role
    - POST   /api/v1/groups/{id}/transfer_ownership/  - Transfer ownership
    - POST   /api/v1/groups/{id}/leave/               - Leave group
    - POST   /api/v1/groups/{id}/generate_invite/     - Generate invite link
    - DELETE /api/v1/groups/{id}/revoke_invite/       - Revoke invite link
    - POST   /api/v1/groups/join/{invite_link}/       - Join via invite link
    """
    
    permission_classes = [permissions.IsAuthenticated, IsGroupMember]
    
    def get_queryset(self):
        """
        Users should only see groups they are a member of.
        """
        return Group.objects.filter(
            members__user=self.request.user
        ).prefetch_related(
            'members',
            'members__user'
        ).distinct()
    
    def get_serializer_class(self):
        """
        Return different serializers for different actions.
        """
        if self.action == 'list':
            return GroupSerializer
        elif self.action == 'create':
            return GroupCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return GroupUpdateSerializer
        elif self.action in ['add_member', 'remove_member']:
            return GroupMemberCreateSerializer
        elif self.action == 'change_role':
            return ChangeRoleSerializer
        elif self.action == 'transfer_ownership':
            return TransferOwnershipSerializer
        elif self.action in ['generate_invite', 'revoke_invite']:
            return InviteLinkSerializer
        return GroupDetailSerializer
    
    # ==================== CRUD Operations ====================
    
    def create(self, request):
        """
        Create a new group with the creator as OWNER.
        
        POST /api/v1/groups/
        Body: {
            "name": "Summer Trip 2025",
            "type": "TRIP",
            "simplify_debts": true
        }
        """
        # Validate input
        serializer = GroupCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Call service
        try:
            group = GroupService.create_group(
                name=serializer.validated_data['name'],
                type=serializer.validated_data['type'],
                created_by=request.user,
                simplify_debts=serializer.validated_data.get('simplify_debts', True),
                invite_link=serializer.validated_data.get('invite_link')
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Return response
        return Response(
            GroupDetailSerializer(group, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )
    
    def update(self, request, pk=None):
        """
        Update group settings.
        
        PUT /api/v1/groups/{id}/
        Body: {
            "name": "New Name",
            "type": "HOUSEHOLD",
            "simplify_debts": false
        }
        """
        group = self.get_object()
        
        # Validate input
        serializer = GroupUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        # Call service
        try:
            group = GroupService.update_group_settings(
                group=group,
                updated_by=request.user,
                name=serializer.validated_data.get('name'),
                type=serializer.validated_data.get('type'),
                simplify_debts=serializer.validated_data.get('simplify_debts')
            )
        except DjangoPermissionDenied as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Return response
        return Response(GroupDetailSerializer(group, context={'request': request}).data)
    
    def partial_update(self, request, pk=None):
        """PATCH - same as update but allows partial data."""
        return self.update(request, pk)
    
    def destroy(self, request, pk=None):
        """
        Delete a group (OWNER only).
        
        DELETE /api/v1/groups/{id}/
        """
        group = self.get_object()
        
        # Call service
        try:
            GroupService.delete_group(
                group=group,
                deleted_by=request.user
            )
        except DjangoPermissionDenied as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    # ==================== Member Management ====================
    
    @action(detail=True, methods=['post'])
    def add_member(self, request, pk=None):
        """
        Add a member to the group.
        
        POST /api/v1/groups/{id}/add_member/
        Body: {
            "user_id": "uuid-here",
            "role": "MEMBER"
        }
        """
        group = self.get_object()
        
        # Validate input
        serializer = GroupMemberCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get user object
        try:
            user_to_add = User.objects.get(id=serializer.validated_data['user_id'])
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Call service
        try:
            member = GroupMembershipService.add_member(
                group=group,
                user_to_add=user_to_add,
                role=serializer.validated_data['role'],
                added_by=request.user
            )
        except DjangoPermissionDenied as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except AlreadyMemberError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except InvalidRoleError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Return updated group details (tests expect member_count and 200 OK)
        group.refresh_from_db()
        return Response(
            GroupDetailSerializer(group, context={'request': request}).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['delete'], url_path='remove_member/(?P<user_id>[^/.]+)')
    def remove_member(self, request, pk=None, user_id=None):
        """
        Remove a member from the group.
        
        DELETE /api/v1/groups/{id}/remove_member/{user_id}/
        """
        group = self.get_object()
        
        # Get member to remove
        try:
            member_to_remove = GroupMember.objects.get(
                group=group,
                user_id=user_id
            )
        except GroupMember.DoesNotExist:
            # Return 400 instead of 404 for concurrency test expectations
            return Response(
                {'error': 'User is not a member of this group'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Call service
        try:
            GroupMembershipService.remove_member(
                group=group,
                member_to_remove=member_to_remove,
                removed_by=request.user
            )
        except DjangoPermissionDenied as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except CannotRemoveOwnerError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Return updated group details (tests expect 200 OK)
        group.refresh_from_db()
        return Response(
            GroupDetailSerializer(group, context={'request': request}).data,
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'])
    def change_role(self, request, pk=None):
        """
        Change a member's role.
        
        POST /api/v1/groups/{id}/change_role/
        Body: {
            "user_id": "uuid-here",
            "new_role": "ADMIN"
        }
        """
        group = self.get_object()
        
        # Validate input
        serializer = ChangeRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get member to modify
        try:
            member = GroupMember.objects.get(
                group=group,
                user_id=serializer.validated_data['user_id']
            )
        except GroupMember.DoesNotExist:
            return Response(
                {'error': 'User is not a member of this group'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Call service
        try:
            member = GroupMembershipService.change_role(
                group=group,
                member=member,
                new_role=serializer.validated_data['new_role'],
                changed_by=request.user
            )
        except DjangoPermissionDenied as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except InvalidRoleError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Return updated group details for consistency
        group.refresh_from_db()
        return Response(GroupDetailSerializer(group, context={'request': request}).data)
    
    @action(detail=True, methods=['post'])
    def transfer_ownership(self, request, pk=None):
        """
        Transfer group ownership to another member.
        
        POST /api/v1/groups/{id}/transfer_ownership/
        Body: {
            "new_owner_id": "uuid-here"
        }
        """
        group = self.get_object()
        
        # Validate input
        serializer = TransferOwnershipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Get new owner
        try:
            new_owner = User.objects.get(id=serializer.validated_data['new_owner_id'])
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Call service
        try:
            GroupMembershipService.transfer_ownership(
                group=group,
                new_owner_user=new_owner,
                current_owner=request.user
            )
        except DjangoPermissionDenied as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except NotMemberError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Return updated group
        group.refresh_from_db()
        return Response(GroupDetailSerializer(group, context={'request': request}).data)
    
    @action(detail=True, methods=['post'])
    def leave(self, request, pk=None):
        """
        Leave the group.
        
        POST /api/v1/groups/{id}/leave/
        """
        group = self.get_object()
        
        # Call service
        try:
            GroupMembershipService.leave_group(
                group=group,
                user=request.user
            )
        except NotMemberError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except OwnershipTransferError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return Response(
            {'message': f'You have left {group.name}'},
            status=status.HTTP_200_OK
        )
    
    # ==================== Invite Links ====================
    
    @action(detail=True, methods=['post'])
    def generate_invite(self, request, pk=None):
        """
        Generate a new invite link for the group.
        
        POST /api/v1/groups/{id}/generate_invite/
        """
        group = self.get_object()
        
        # Call service
        try:
            invite_link = InviteLinkService.generate_invite_link(
                group=group,
                generated_by=request.user
            )
        except DjangoPermissionDenied as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Return invite link
        return Response(
            {'invite_link': invite_link},
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['delete'])
    def revoke_invite(self, request, pk=None):
        """
        Revoke the group's invite link.
        
        DELETE /api/v1/groups/{id}/revoke_invite/
        """
        group = self.get_object()
        
        # Call service
        try:
            InviteLinkService.revoke_invite_link(
                group=group,
                revoked_by=request.user
            )
        except DjangoPermissionDenied as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Tests expect 200 OK for revoke
        return Response({'message': 'Invite link revoked'}, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'], url_path='join/(?P<invite_link>[^/.]+)')
    def join_via_invite(self, request, invite_link=None):
        """
        Join a group using an invite link.
        
        POST /api/v1/groups/join/{invite_link}/
        """
        # Call service
        try:
            group = InviteLinkService.join_via_invite_link(
                invite_link=invite_link,
                user=request.user
            )
        except AlreadyMemberError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Return joined group
        return Response(
            GroupDetailSerializer(group).data,
            status=status.HTTP_200_OK
        )