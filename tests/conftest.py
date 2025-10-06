import os
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from django.core.cache import cache
import django

django.setup()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "splitpay_backend.settings")

User = get_user_model()

@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="alice",
        email="alice@example.com",
        password="StrongPass123!"
    )

@pytest.fixture
def auth_client(api_client, user):
    # فرض کنیم توکن اتنتیکیشن از DRF TokenAuthentication استفاده می‌کنی
    # اگر JWT داری، مطابق همون تغییر بده
    from rest_framework.authtoken.models import Token
    token, _ = Token.objects.get_or_create(user=user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client
