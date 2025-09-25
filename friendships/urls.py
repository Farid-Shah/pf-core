from rest_framework.routers import DefaultRouter
from .views import FriendRequestViewSet, FriendshipViewSet

router = DefaultRouter()
router.register(r'friend-requests', FriendRequestViewSet, basename='friend-request')
router.register(r'friends', FriendshipViewSet, basename='friendship')

urlpatterns = router.urls