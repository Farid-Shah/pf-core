from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, List, Tuple

from django.db import transaction
from django.contrib.auth import get_user_model

from .models import (
    Expense, ExpenseItem, ExpenseItemShare,
    ExpenseParticipant, ExpensePayer
)

User = get_user_model()


def _round_minor(x: Decimal) -> int:
    # گرد کردن به نزدیک‌ترین واحد minor، مثل ریال
    return int(x.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _distribute_by_weights(total_minor: int, shares: List[Tuple[int, Decimal]]) -> Dict[int, int]:
    """
    total_minor را بر اساس وزن‌ها بین کاربران پخش می‌کند.
    shares: [(user_id, weight_decimal), ...]
    خروجی: {user_id: amount_minor}
    """
    if not shares:
        return {}
    total_w = sum(w for _, w in shares)
    if total_w == Decimal("0"):
        # تقسیم مساوی
        each = total_minor // len(shares)
        out = {u: each for u, _ in shares}
        leftover = total_minor - each * len(shares)
        # باقی‌مانده را به اولین‌ها بده
        for u, _ in shares[:leftover]:
            out[u] += 1
        return out

    # نسبت‌بندی
    alloc = {}
    acc = 0
    for i, (u, w) in enumerate(shares):
        if i == len(shares) - 1:
            alloc[u] = total_minor - acc
        else:
            amt = _round_minor(Decimal(total_minor) * (w / total_w))
            alloc[u] = amt
            acc += amt
    return alloc


@transaction.atomic
def apply_total_mode_breakdown(
    expense: Expense,
    participants: Iterable[int],
    split_type: str,
    splits_payload: List[dict] | None
) -> None:
    """
    منطق توتال‌محور: equally | unequally | shares
    خروجی را در ExpenseParticipant ذخیره می‌کند.
    """
    # پاک‌سازی قبلی
    ExpenseParticipant.objects.filter(expense=expense).delete()

    participants = list(dict.fromkeys(participants))  # unique & keep order
    if split_type == "equally":
        assert participants, "participants must not be empty for equally"
        each = expense.total_amount_minor // len(participants)
        amounts = {u: each for u in participants}
        leftover = expense.total_amount_minor - each * len(participants)
        for u in participants[:leftover]:
            amounts[u] += 1

    elif split_type == "unequally":
        # splits_payload: [{"user": id, "amount_minor": 1234}, ...]
        assert splits_payload, "splits required for unequally"
        amounts = {s["user"]: int(s["amount_minor"]) for s in splits_payload}
        assert sum(amounts.values()) == expense.total_amount_minor, "sum(splits) must equal total amount"
        # اگر participants داده شده، check عضویت‌ها
        if participants:
            diff = set(amounts.keys()) ^ set(participants)
            assert not diff, "participants and splits users mismatch"

    elif split_type == "shares":
        # splits_payload: [{"user": id, "weight": "2.5"}, ...]
        assert splits_payload, "splits (weights) required for shares"
        weights = [(s["user"], Decimal(str(s["weight"]))) for s in splits_payload]
        amounts = _distribute_by_weights(expense.total_amount_minor, weights)
        if participants:
            diff = set(amounts.keys()) ^ set(participants)
            assert not diff, "participants and weights users mismatch"

    else:
        raise ValueError("Invalid split_type")

    ExpenseParticipant.objects.bulk_create([
        ExpenseParticipant(expense=expense, user_id=u, owed_amount_minor=amt)
        for u, amt in amounts.items()
    ])


@transaction.atomic
def apply_itemized_mode_breakdown(expense: Expense, items_payload: List[dict]) -> None:
    """
    آیتم‌محور: items = [{
      title, quantity, unit_price_minor,
      shares: [{user, amount_minor} | {user, weight}]
    }]
    خروجی را در ExpenseItem/ExpenseItemShare ساخته و نهایتاً ExpenseParticipant را پر می‌کند.
    """
    # پاک‌سازی قبلی
    ExpenseItem.objects.filter(expense=expense).delete()
    ExpenseParticipant.objects.filter(expense=expense).delete()

    user_totals: Dict[int, int] = {}

    for item_in in items_payload:
        it = ExpenseItem.objects.create(
            expense=expense,
            title=item_in["title"],
            quantity=Decimal(str(item_in.get("quantity", "1"))),
            unit_price_minor=int(item_in["unit_price_minor"])
        )
        item_total = _round_minor(Decimal(it.unit_price_minor) * it.quantity)

        shares_in = item_in["shares"]
        explicit = [s for s in shares_in if s.get("amount_minor") is not None]
        weights  = [s for s in shares_in if s.get("weight") is not None]

        if explicit and weights:
            raise ValueError("Each item shares must be either amount-based or weight-based, not both")

        if explicit:
            alloc = {int(s["user"]): int(s["amount_minor"]) for s in explicit}
            if sum(alloc.values()) != item_total:
                raise ValueError("Item explicit shares must sum to item total")
            ExpenseItemShare.objects.bulk_create([
                ExpenseItemShare(item=it, user_id=u, amount_minor=amt)
                for u, amt in alloc.items()
            ])
        else:
            pairs = [(int(s["user"]), Decimal(str(s.get("weight", "0")))) for s in shares_in]
            alloc = _distribute_by_weights(item_total, pairs)
            ExpenseItemShare.objects.bulk_create([
                ExpenseItemShare(item=it, user_id=u, weight=Decimal(str(w)) if any(w for _, w in pairs) else None,
                                 amount_minor=amt)
                for (u, w), amt in zip(pairs, [alloc[u] for u, _ in pairs])
            ])

        # جمع به ازای هر کاربر
        for u, amt in alloc.items():
            user_totals[u] = user_totals.get(u, 0) + amt

    # پرکردن ExpenseParticipant از user_totals
    ExpenseParticipant.objects.bulk_create([
        ExpenseParticipant(expense=expense, user_id=u, owed_amount_minor=amt)
        for u, amt in user_totals.items()
    ])
