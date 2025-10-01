# accounts/views.py
from django.contrib.auth import get_user_model
from rest_framework import permissions, status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle

from .serializers import (
    RegisterSerializer,
    MeSerializer,
    PublicUserSerializer,
    UsernameChangeSerializer,
)
from .throttling import UsernameAvailabilityThrottle, RegisterThrottle
from .services import check_handle_availability

User = get_user_model()


class UsernameAvailabilityView(APIView):
    """
    GET /api/v1/username-availability/?username=<str>
    پاسخ استاندارد:
    {"ok": true|false, "reason": null|"invalid_format"|"too_short"|"too_long"|"reserved"|"taken"}
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [UsernameAvailabilityThrottle]

    def get(self, request, *args, **kwargs):
        username = (request.query_params.get("username") or "").strip()
        ok, reason = check_handle_availability(username)
        return Response(
            {"ok": bool(ok), "reason": (None if ok else reason)},
            status=status.HTTP_200_OK,
        )


class RegisterView(generics.CreateAPIView):
    """
    POST /api/v1/auth/register/
    ثبت‌نام عمومی کاربران جدید (Throttle اختصاصی فقط روی همین ویو).
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [RegisterThrottle]
    serializer_class = RegisterSerializer


class MeView(generics.RetrieveUpdateAPIView):
    """
    GET/PUT/PATCH /api/v1/user/me/
    پروفایل کاربر جاری.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MeSerializer

    def get_object(self):
        return self.request.user


class PublicUserView(generics.RetrieveAPIView):
    """
    GET /api/v1/users/<username>/
    نمایه‌ی عمومی کاربر (read-only).
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = PublicUserSerializer

    def get_object(self):
        # جست‌وجوی case-insensitive برای یک‌پارچگی با normalizer
        username = self.kwargs.get("username")
        return User.objects.get(username__iexact=username)


class UsernameChangeView(generics.GenericAPIView):
    """
    POST /api/v1/user/username-change/
    تغییر نام کاربری. در صورت نیاز می‌توان scope اختصاصی تعریف کرد.
    - اگر می‌خواهی سقف نرخ مستقل داشته باشی، در settings:
        REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["username_change"] = "20/minute"
      و در این ویو:
        throttle_classes = [ScopedRateThrottle]
        throttle_scope = "username_change"
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UsernameChangeSerializer
    # اگر scope جدا تنظیم کرده‌ای، این دو خط را از کامنت خارج کن:
    # throttle_classes = [ScopedRateThrottle]
    # throttle_scope = "username_change"

    def post(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)  # ValidationError → 400 به‌صورت تمیز
        ser.save()  # منطق change_username داخل serializer/Model هندل می‌شود
        return Response(status=status.HTTP_204_NO_CONTENT)
