import pytest
from django.utils.timezone import now
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model

BASE = "/api/v1/expenses/"

@pytest.fixture
def cli(db):
    def _c(u):
        t, _ = Token.objects.get_or_create(user=u)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Token {t.key}")
        return c
    return _c

@pytest.fixture
def users(db):
    U = get_user_model()
    p1, _ = U.objects.get_or_create(username="testUserPayer", defaults={"email":"testUserPayer@x.com"})
    p2, _ = U.objects.get_or_create(username="TestUserHelp", defaults={"email":"TestUserHelp@x.com"})
    deb,_ = U.objects.get_or_create(username="testUserParticipant", defaults={"email":"testUserParticipant@x.com"})
    out,_ = U.objects.get_or_create(username="testUserOut", defaults={"email":"testUserOut@x.com"})
    return p1, p2, deb, out

def make_payload(p1, p2, deb, total=200000):
    return {
        "description": "Manual-TEST",
        "total_amount_minor": total,
        "date": now().date().isoformat(),
        "calc_mode": "TOTAL",
        "breakdown_method": "unequally",
        "splits": [
            {"user_id": str(p1.id), "paid_amount_minor": total//2, "owed_amount_minor": 0},
            {"user_id": str(p2.id), "paid_amount_minor": total//2, "owed_amount_minor": 0},
            {"user_id": str(deb.id),"paid_amount_minor": 0,        "owed_amount_minor": total},
        ],
    }

@pytest.mark.django_db
def test_delete_approval_flow(cli, users):
    p1, p2, deb, out = users
    cp1, cp2, cdeb, cout = cli(p1), cli(p2), cli(deb), cli(out)

    # create
    r = cp1.post(BASE, make_payload(p1, p2, deb), format="json")
    assert r.status_code in (200, 201)
    eid = r.data["id"]

    # direct delete -> 409
    assert cp1.delete(f"{BASE}{eid}/").status_code == 409

    # outsider can't approve
    assert cout.post(f"{BASE}{eid}/approve/", {"action":"delete"}, format="json").status_code in (403, 404)

    # request-delete -> 202
    assert cp1.post(f"{BASE}{eid}/request-delete/", {}, format="json").status_code == 202

    # debtor can't approve
    assert cdeb.post(f"{BASE}{eid}/approve/", {"action":"delete"}, format="json").status_code in (403, 404)

    # approve by payer2 -> 200, then GET -> 404
    assert cp2.post(f"{BASE}{eid}/approve/", {"action":"delete"}, format="json").status_code == 200
    assert cp1.get(f"{BASE}{eid}/").status_code == 404

@pytest.mark.django_db
def test_edit_approval_flow(cli, users):
    p1, p2, deb, out = users
    cp1, cp2, cdeb, cout = cli(p1), cli(p2), cli(deb), cli(out)

    r = cp1.post(BASE, make_payload(p1, p2, deb), format="json")
    assert r.status_code in (200, 201)
    eid = r.data["id"]

    # debtor/outside can't patch directly
    assert cdeb.patch(f"{BASE}{eid}/", {"description":"x"}, format="json").status_code in (403, 404)
    assert cout.patch(f"{BASE}{eid}/", {"description":"x"}, format="json").status_code in (403, 404)

    # request-edit -> 202
    assert cp1.post(f"{BASE}{eid}/request-edit/", {"description":"NEW"}, format="json").status_code == 202

    # approve edit by payer2 -> 200 and description updated
    r2 = cp2.post(f"{BASE}{eid}/approve/", {"action":"edit"}, format="json")
    assert r2.status_code == 200
    g = cp1.get(f"{BASE}{eid}/")
    assert g.status_code == 200
    assert g.data.get("description") == "NEW"
