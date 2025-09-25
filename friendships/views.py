from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import FriendRequest, Friendship
from .serializers import FriendRequestSerializer, FriendshipSerializer


class FriendRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Friend Requests.

    Endpoints:
    - GET /api/v1/friend-requests/ - List received and sent requests.
    - POST /api/v1/friend-requests/ - Create a new friend request.
    - GET /api/v1/friend-requests/{id}/ - Retrieve a specific request.
    - DELETE /api/v1/friend-requests/{id}/ - Cancel a sent request.
    - POST /api/v1/friend-requests/{id}/accept/ - Accept a received request.
    - POST /api/v1/friend-requests/{id}/decline/ - Decline a received request.
    """
    serializer_class = FriendRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        This view should return a list of all friend requests
        for the currently authenticated user (both sent and received).
        """
        user = self.request.user
        return FriendRequest.objects.filter(Q(from_user=user) | Q(to_user=user))

    def perform_create(self, serializer):
        """
        The serializer already sets the `from_user` from the context.
        """
        serializer.save()

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        """
        Accept a friend request. This creates a Friendship.
        """
        friend_request = self.get_object()
        if friend_request.to_user != request.user:
            return Response(
                {'error': 'You are not authorized to accept this request.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if friend_request.status != FriendRequest.Status.PENDING:
            return Response(
                {'error': 'This request is no longer pending.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # This is where a service function would be ideal.
        # For now, we handle the logic here.
        friend_request.status = FriendRequest.Status.ACCEPTED
        friend_request.save()

        # Create the Friendship, ensuring user_low < user_high
        user1, user2 = sorted([friend_request.from_user, friend_request.to_user], key=lambda u: u.id.int)
        Friendship.objects.create(user_low=user1, user_high=user2)
        
        return Response(FriendRequestSerializer(friend_request).data)

    @action(detail=True, methods=['post'])
    def decline(self, request, pk=None):
        """
        Decline a friend request.
        """
        friend_request = self.get_object()
        if friend_request.to_user != request.user:
            return Response(
                {'error': 'You are not authorized to decline this request.'},
                status=status.HTTP_403_FORBIDDEN
            )

        friend_request.status = FriendRequest.Status.DECLINED
        friend_request.save()
        return Response(FriendRequestSerializer(friend_request).data)


class FriendshipViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for listing and removing friends.

    Endpoints:
    - GET /api/v1/friends/ - List all friends.
    - DELETE /api/v1/friends/{id}/ - Remove a friend.
    """
    serializer_class = FriendshipSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """

        This view should return a list of all friendships
        for the currently authenticated user.
        """
        user = self.request.user
        return Friendship.objects.filter(Q(user_low=user) | Q(user_high=user))

    def perform_destroy(self, instance):
        """
        Allow a user to "unfriend" someone. This deletes the Friendship record.
        The default implementation already checks object permissions, which is sufficient here.
        """
        instance.delete()