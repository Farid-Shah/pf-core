from rest_framework import permissions
from rest_framework.permissions import BasePermission, SAFE_METHODS

REL_PARTICIPANTS = "participants"  # روی مدل شما وجود دارد

def _payer_qs(obj):
    # روی مدل شما 'payers' یک related manager است (طبق ریسپانسی که دیدیم)
    return getattr(obj, "payers", None)

def _payer_ids(obj):
    q = _payer_qs(obj)
    if q is None:
        return set()
    return set(q.filter(paid_amount_minor__gt=0).values_list("user_id", flat=True))

def _participant_ids(obj):
    q = getattr(obj, REL_PARTICIPANTS, None)
    if q is None:
        return set()
    return set(q.filter(owed_amount_minor__gt=0).values_list("user_id", flat=True))


class OnlyPayerCanDelete(permissions.BasePermission):
    """
    اجازه‌ی DELETE فقط برای کسی که پرداخت کرده (payer) یا در صورت وجود فیلد تکی paid_by_id.
    """
    def has_object_permission(self, request, view, obj):
        if request.method != "DELETE":
            return True

        # اگر فیلد تکی paid_by_id دارید
        if hasattr(obj, "paid_by_id") and obj.paid_by_id is not None:
            return obj.paid_by_id == request.user.id

        # مدل چندپرداخت‌کننده
        return request.user.id in _payer_ids(obj)


class IsExpensePayer(BasePermission):
    """مجوزی که چک می‌کند کاربر payer این Expense است یا نه."""
    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.id in _payer_ids(obj)


class IsExpenseActionAllowed(BasePermission):
    """
    GET: آزاد طبق سیاست‌های view (اینجا True می‌دهیم)
    PATCH/PUT/DELETE: فقط payerها (و اختیاری: creator)
    """
    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if request.method in SAFE_METHODS:
            return True

        payers = _payer_ids(obj)
        is_creator = (getattr(obj, "created_by_id", None) == user.id)
        is_payer = user.id in payers

        if request.method in ("PATCH", "PUT", "DELETE"):
            return is_payer

        return False
