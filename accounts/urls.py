from django.urls import path
from .views import (
    UsernameAvailabilityView,
    RegisterView,
    MeView,
    PublicUserView,
    UsernameChangeView,
)

urlpatterns = [
    path("username-availability/", UsernameAvailabilityView.as_view(), name="username-availability"),
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("user/me/", MeView.as_view(), name="user-me"),
    path("user/username-change/", UsernameChangeView.as_view(), name="user-username-change"),
    path("users/<str:username>/", PublicUserView.as_view(), name="user-public"),
]
