from django.contrib.auth import get_user_model
from rest_framework import viewsets, generics, permissions
from .serializers import UserSerializer, UserDetailSerializer

User = get_user_model()

class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """
    A read-only viewset for listing and retrieving public user information.
    
    Endpoints:
    - GET /api/v1/users/
    - GET /api/v1/users/{id}/
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]


class CurrentUserView(generics.RetrieveUpdateAPIView):
    """
    An endpoint for the currently authenticated user to view and update their profile.

    Endpoints:
    - GET /api/v1/user/me/
    - PUT /api/v1/user/me/
    - PATCH /api/v1/user/me/
    """
    serializer_class = UserDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        """
        Return the currently authenticated user.
        """
        return self.request.user

    def get_queryset(self):
        """
        Needed for the browsable API, but get_object is the primary method used.
        """
        return User.objects.filter(id=self.request.user.id)