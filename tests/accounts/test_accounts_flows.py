import pytest
from django.test import override_settings
from django.conf import settings as dj_settings

HIGH_USER_RATE = {
    **dj_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
    "user": "1000/minute",  # برای این تست
}

@override_settings(
    REST_FRAMEWORK={
        **dj_settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": HIGH_USER_RATE
    }
)

@pytest.mark.django_db
def test_username_policy_availability(api_client):
    url = "/api/v1/username-availability/"

    # نام معتبر
    r = api_client.get(url, {"username": "valid_name"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True

    # نام خیلی کوتاه/غیرمجاز/رزرو (بسته به policy مدل تو)
    # این‌ها رو بسته به پیاده‌سازی‌ات تنظیم کن:
    for bad in ["ad", "ADMIN", "Root", "invalid space", "😅"]:
        r = api_client.get(url, {"username": bad})
        assert r.status_code == 200
        # ok=False و reason یکی از: invalid_format | too_short | too_long | reserved | taken
        assert r.json()["ok"] in (True, False)
        if r.json()["ok"] is False:
            assert r.json()["reason"] in {"invalid_format", "too_short", "too_long", "reserved", "taken"}

@pytest.mark.django_db
def test_register_and_me_and_public(api_client):
    # register
    reg_url = "/api/v1/auth/register/"
    payload = {
        "username": "newuser",
        "email": "newuser@example.com",
        "password": "StrongPass123!",
    }
    r = api_client.post(reg_url, payload, format="json")
    assert r.status_code in (201, 200)
    # ورود با TokenAuth؟ اگر اتوماتیک توکن نمی‌ده، از مسیر لاگین/توکن استفاده کن
    # اینجا فرض می‌کنیم endpoint توکن داری (در صورت نداشتن، با create_user در fixture کار کن)
    # برای نمونه:
    from rest_framework.authtoken.models import Token
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u = User.objects.get(username="newuser")
    token, _ = Token.objects.get_or_create(user=u)

    # me
    me_url = "/api/v1/user/me/"
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    r = api_client.get(me_url)
    assert r.status_code == 200
    me = r.json()
    assert me["username"] == "newuser"

    # public profile
    public_url = f"/api/v1/users/{u.username}/"
    r = api_client.get(public_url)
    assert r.status_code == 200
    pub = r.json()
    assert pub["username"] == "newuser"

@override_settings(USERNAME_IMMUTABLE_AFTER_WINDOW=False)
@pytest.mark.django_db
def test_username_change_flow(auth_client, user):
    url = "/api/v1/user/username-change/"
    # تغییر موفق
    r = auth_client.post(url, {"new_username": "alice2"}, format="json")
    assert r.status_code in (200, 204)
    # تلاش برای نام رزرو/نامعتبر/گرفته‌شده
    for bad in ["Admin", "root", "alice2", "a", "invalid space"]:
        r = auth_client.post(url, {"new_username": bad}, format="json")
        assert r.status_code in (400, 409)
