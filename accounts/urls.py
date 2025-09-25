from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import UserViewSet, CurrentUserView

# Create a router and register our viewsets with it.
router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')

# The API URLs are determined automatically by the router.
# The `urlpatterns` will be a combination of the router's URLs and any custom paths.
urlpatterns = [
    path('user/me/', CurrentUserView.as_view(), name='current-user'),
] + router.urls