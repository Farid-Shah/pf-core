import pytest
from django.test import override_settings
from django.urls import reverse

# نرخ‌ها رو برای سرعت تست پایین می‌آریم
TEST_THROTTLES = {
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "accounts.throttling.UsernameAvailabilityThrottle",
        "accounts.throttling.RegisterThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/minute",
        "user": "1000/day",
        "username_availability": "3/minute",
        "register": "2/minute",
    },
}

@pytest.mark.django_db
@override_settings(REST_FRAMEWORK=TEST_THROTTLES)
def test_username_availability_throttle(api_client, settings):
    url = "/api/v1/username-availability/"
    # 3 درخواست اول: 200
    for i in range(10):
        assert api_client.get(url, {"username": f"t{i}"}).status_code == 200
    assert api_client.get(url, {"username": "t_over"}).status_code == 429

@pytest.mark.django_db
@override_settings(REST_FRAMEWORK=TEST_THROTTLES)
def test_register_throttle(api_client):
    url = "/api/v1/auth/register/"
    payload = lambda i: {
        "username": f"user{i}",
        "email": f"user{i}@ex.com",
        "password": "StrongPass123!",
    }
    for i in range(5):
        assert api_client.post(url, payload(i), format="json").status_code in (200, 201)
    assert api_client.post(url, payload(999), format="json").status_code == 429
