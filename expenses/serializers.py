from rest_framework import serializers
from django.db import transaction
from decimal import Decimal

from accounts.serializers import UserSerializer
from .models import (
    Category,
    Expense,
    ExpensePayer,
    ExpenseParticipant,
    ExpenseComment,
    Attachment,
    RecurringExpenseTemplate,
)

# --- Category Serializer ---
class CategorySerializer(serializers.ModelSerializer):
    """
    Serializer for the Category model, supporting parent-child relationships.
    """
    class Meta:
        model = Category
        fields = ['id', 'name', 'parent']

# --- Comment and Attachment Serializers ---
class ExpenseCommentSerializer(serializers.ModelSerializer):
    """
    Serializer for expense comments. The user is automatically set to the request user.
    """
    user = UserSerializer(read_only=True)

    class Meta:
        model = ExpenseComment
        fields = ['id', 'user', 'content', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']

class AttachmentSerializer(serializers.ModelSerializer):
    """
    Serializer for expense attachments.
    """
    class Meta:
        model = Attachment
        fields = ['id', 'file', 'content_type', 'size_bytes', 'created_at']
        read_only_fields = ['id', 'content_type', 'size_bytes', 'created_at']


# --- Expense Split and Payer/Participant Serializers ---
class ExpensePayerSerializer(serializers.ModelSerializer):
    """Read-only serializer for displaying who paid for an expense."""
    user = UserSerializer(read_only=True)

    class Meta:
        model = ExpensePayer
        fields = ['user', 'paid_amount_minor']

class ExpenseParticipantSerializer(serializers.ModelSerializer):
    """Read-only serializer for displaying who owes for an expense."""
    user = UserSerializer(read_only=True)

    class Meta:
        model = ExpenseParticipant
        fields = ['user', 'owed_amount_minor']


class ExpenseSplitSerializer(serializers.Serializer):
    """
    Write-only serializer to validate the structure for splitting an expense.
    This is used inside the main Expense serializer.
    """
    user_id = serializers.UUIDField()
    paid_amount_minor = serializers.IntegerField(min_value=0, default=0)
    owed_amount_minor = serializers.IntegerField(min_value=0, default=0)


# --- Main Expense Serializers ---
class ExpenseSerializer(serializers.ModelSerializer):
    """
    Basic serializer for listing expenses.
    """
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = Expense
        fields = [
            'id',
            'description',
            'total_amount_minor',
            'date',
            'group',
            'created_by',
        ]

class ExpenseItemShareInSerializer(serializers.Serializer):
    """
    سهم هر آیتم برای یک کاربر:
    یا amount_minor بده (تقسیم دقیق)،
    یا weight بده (تقسیم نسبتی). هردو همزمان مجاز نیستند.
    """
    user_id = serializers.UUIDField()
    amount_minor = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    weight = serializers.DecimalField(required=False, allow_null=True, max_digits=12, decimal_places=3)

    def validate(self, data):
        if (data.get("amount_minor") is None) == (data.get("weight") is None):
            raise serializers.ValidationError("Provide exactly one of amount_minor or weight for each item share.")
        return data


class ExpenseItemInSerializer(serializers.Serializer):
    """
    یک ردیف آیتم فاکتور برای حالت ITEMIZED.
    total آیتم = quantity * unit_price_minor
    """
    title = serializers.CharField(max_length=200)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, required=False, default=Decimal("1.000"))
    unit_price_minor = serializers.IntegerField(min_value=0)
    shares = ExpenseItemShareInSerializer(many=True)

    def validate(self, data):
        shares = data.get("shares", [])
        if not shares:
            raise serializers.ValidationError("Each item must have at least one share.")
        return data


class ExpenseDetailSerializer(ExpenseSerializer):
    """
    Detailed serializer for creating, retrieving, and updating an expense.
    Supports two modes:
      - TOTAL: legacy Splitwise-style (use 'splits' with paid/owed)
      - ITEMIZED: provide 'items'; we'll compute participants (owed) from items.
                  For payers, still use 'splits' (paid side only).
    """
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True, required=False, allow_null=True
    )
    payers = ExpensePayerSerializer(many=True, read_only=True)
    participants = ExpenseParticipantSerializer(many=True, read_only=True)
    comments = ExpenseCommentSerializer(many=True, read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)
    description = serializers.CharField(required=False, allow_blank=True)

    # NEW: modes & inputs
    calc_mode = serializers.ChoiceField(choices=[("TOTAL","TOTAL"), ("ITEMIZED","ITEMIZED")], required=False, default="TOTAL")
    breakdown_method = serializers.ChoiceField(
        choices=[("equally","equally"), ("unequally","unequally"), ("shares","shares")],
        required=False, allow_null=True
    )
    items = ExpenseItemInSerializer(many=True, required=False)
    receipt = serializers.FileField(write_only=True, required=False, allow_null=True)
    receipt_url = serializers.SerializerMethodField(read_only=True)

    # splits now optional (in ITEMIZED we only need paid side)
    splits = serializers.ListField(child=ExpenseSplitSerializer(), write_only=True, required=False)

    class Meta(ExpenseSerializer.Meta):
        fields = ExpenseSerializer.Meta.fields + [
            'details',
            'category',
            'category_id',
            'updated_by',
            'payers',
            'participants',
            'comments',
            'attachments',
            'calc_mode',
            'breakdown_method',
            'items',
            'receipt',
            'receipt_url',
            'splits',  # For write operations
        ]
        read_only_fields = ['created_by', 'updated_by']

    def get_receipt_url(self, obj):
        rec = obj.attachments.filter().first()  # اگر is_receipt داری: .filter(is_receipt=True).first()
        return rec.file.url if rec and rec.file else None

    def _sum_items_total(self, items):
        total = 0
        for it in items:
            qty = Decimal(str(it.get("quantity", "1")))
            total += int(qty * int(it["unit_price_minor"]))
        return total

    def _compute_itemized_owed_map(self, items):
        """
        خروجی: dict[user_id -> owed_amount_minor] از روی items/shares
        """
        user_totals = {}
        for it in items:
            qty = Decimal(str(it.get("quantity", "1")))
            item_total = int(qty * int(it["unit_price_minor"]))
            shares = it["shares"]

            explicit = [s for s in shares if s.get("amount_minor") is not None]
            weights = [s for s in shares if s.get("weight") is not None]

            if explicit and weights:
                raise serializers.ValidationError("Each item must use either explicit amounts or weights, not both.")

            if explicit:
                alloc = {str(s["user_id"]): int(s["amount_minor"]) for s in explicit}
                if sum(alloc.values()) != item_total:
                    raise serializers.ValidationError("Explicit item shares must sum to item total.")
            else:
                # weight-based
                wpairs = [(str(s["user_id"]), Decimal(str(s.get("weight") or "0"))) for s in shares]
                total_w = sum(w for _, w in wpairs)
                if total_w == 0:
                    # تقسیم مساوی
                    each = item_total // len(wpairs)
                    alloc = {u: each for u, _ in wpairs}
                    leftover = item_total - each * len(wpairs)
                    for u, _ in wpairs[:leftover]:
                        alloc[u] += 1
                else:
                    # نسبت‌بندی با گردسازی
                    alloc = {}
                    acc = 0
                    for i, (u, w) in enumerate(wpairs):
                        if i == len(wpairs) - 1:
                            alloc[u] = item_total - acc
                        else:
                            amt = int((Decimal(item_total) * (w / total_w)).quantize(Decimal("1")))
                            alloc[u] = amt
                            acc += amt

            for u, a in alloc.items():
                user_totals[u] = user_totals.get(u, 0) + a
        return user_totals

    def validate(self, data):
        instance = getattr(self, "instance", None)
        partial = getattr(self, "partial", False)

        # حالت را از ورودی یا از شیء موجود بگیر
        mode = data.get('calc_mode') or (getattr(instance, 'calc_mode', None)) or 'TOTAL'
        data['calc_mode'] = mode  # نرمال‌سازی

        total_amount = data.get('total_amount_minor')
        splits = data.get('splits', None)
        items = data.get('items', None)

        if mode == 'TOTAL':
            # اگر PATCH است و splits نفرستادی، ولیدیشن splits لازم نیست
            if not partial or splits is not None:
                if not splits:
                    raise serializers.ValidationError({"splits": "splits are required in TOTAL mode."})
                paid_sum = sum(s.get('paid_amount_minor', 0) for s in splits)
                owed_sum = sum(s.get('owed_amount_minor', 0) for s in splits)
                # اگر total را همین PATCH تغییر می‌دهی یا روی create هستیم، چک کن
                effective_total = total_amount if total_amount is not None else getattr(instance, 'total_amount_minor',
                                                                                        None)
                if effective_total is None:
                    raise serializers.ValidationError({"total_amount_minor": "total_amount_minor is required."})
                if paid_sum != effective_total:
                    raise serializers.ValidationError(
                        f"The sum of paid amounts ({paid_sum}) must equal the expense total ({effective_total})."
                    )
                if owed_sum != effective_total:
                    raise serializers.ValidationError(
                        f"The sum of owed amounts ({owed_sum}) must equal the expense total ({effective_total})."
                    )
            return data

        # ITEMIZED
        # اگر PATCH است و items نفرستادی، ولیدیشن آیتم‌ها لازم نیست
        if not partial or items is not None:
            if not items:
                raise serializers.ValidationError({"items": "items are required in ITEMIZED mode."})

            # اگر items آمده، می‌تونی total را از آیتم‌ها پر کنی
            items_total = self._sum_items_total(items)
            if total_amount in (None, 0):
                data['total_amount_minor'] = items_total
                total_amount = items_total

            # اگر splits آمد، فقط paid_sum را با total چک کن
            if splits is not None:
                paid_sum = sum(s.get('paid_amount_minor', 0) for s in splits)
                if paid_sum != total_amount:
                    raise serializers.ValidationError(
                        f"The sum of paid amounts ({paid_sum}) must equal the expense total ({total_amount})."
                    )

        return data

    def create(self, validated_data):
        """
        TOTAL: همان رفتار فعلی—از splits هم payers می‌سازیم هم participants.
        ITEMIZED: participants را از items محاسبه و ثبت می‌کنیم؛
                  payers را از splits (paid side only) می‌سازیم.
        """
        splits_data = validated_data.pop('splits', None)
        items_data = validated_data.pop('items', None)
        receipt_file = validated_data.pop('receipt', None)
        validated_data['created_by'] = self.context['request'].user
        mode = validated_data.get('calc_mode', 'TOTAL')

        from .models import ExpensePayer, ExpenseParticipant, Attachment  # اجتناب از import loop

        with transaction.atomic():
            expense = Expense.objects.create(**validated_data)

            if mode == 'TOTAL':
                # === رفتار فعلی: ساخت payers و participants از روی splits ===
                for s in splits_data:
                    uid = s['user_id']
                    if s.get('paid_amount_minor', 0) > 0:
                        ExpensePayer.objects.create(
                            expense=expense, user_id=uid, paid_amount_minor=s['paid_amount_minor']
                        )
                    if s.get('owed_amount_minor', 0) > 0:
                        ExpenseParticipant.objects.create(
                            expense=expense, user_id=uid, owed_amount_minor=s['owed_amount_minor']
                        )

            else:
                # === ITEMIZED: participants از آیتم‌ها ===
                owed_map = self._compute_itemized_owed_map(items_data)
                # ساخت participants
                ExpenseParticipant.objects.bulk_create([
                    ExpenseParticipant(expense=expense, user_id=u, owed_amount_minor=amt)
                    for u, amt in owed_map.items()
                ])
                # ساخت payers فقط از paid_amount_minor
                for s in splits_data:
                    uid = s['user_id']
                    paid = s.get('paid_amount_minor', 0)
                    if paid > 0:
                        ExpensePayer.objects.create(
                            expense=expense, user_id=uid, paid_amount_minor=paid
                        )

            # رسید اختیاری
            if receipt_file:
                Attachment.objects.create(
                    expense=expense,
                    file=receipt_file,
                    content_type=getattr(receipt_file, "content_type", ""),
                    size_bytes=getattr(receipt_file, "size", 0),
                )

        return expense

    def update(self, instance, validated_data):
        from .models import ExpensePayer, ExpenseParticipant, Attachment

        splits_data = validated_data.pop('splits', None)
        items_data = validated_data.pop('items', None)
        receipt_file = validated_data.pop('receipt', None)

        validated_data['updated_by'] = self.context['request'].user
        mode = validated_data.get('calc_mode', getattr(instance, 'calc_mode', 'TOTAL'))

        with transaction.atomic():
            instance = super().update(instance, validated_data)

            # رسید جدید؟ (اختیاری)
            if receipt_file:
                Attachment.objects.create(
                    expense=instance,
                    file=receipt_file,
                    content_type=getattr(receipt_file, "content_type", ""),
                    size_bytes=getattr(receipt_file, "size", 0),
                )

            if mode == 'TOTAL':
                if splits_data is not None:
                    instance.payers.all().delete()
                    instance.participants.all().delete()
                    for s in splits_data:
                        uid = s['user_id']
                        if s.get('paid_amount_minor', 0) > 0:
                            ExpensePayer.objects.create(
                                expense=instance, user_id=uid, paid_amount_minor=s['paid_amount_minor']
                            )
                        if s.get('owed_amount_minor', 0) > 0:
                            ExpenseParticipant.objects.create(
                                expense=instance, user_id=uid, owed_amount_minor=s['owed_amount_minor']
                            )
            else:  # ITEMIZED
                if items_data is not None:
                    # فقط اگر آیتم‌ها آمدند، participants را بازسازی کن
                    instance.participants.all().delete()
                    owed_map = self._compute_itemized_owed_map(items_data)
                    ExpenseParticipant.objects.bulk_create([
                        ExpenseParticipant(expense=instance, user_id=u, owed_amount_minor=amt)
                        for u, amt in owed_map.items()
                    ])
                if splits_data is not None:
                    # فقط اگر splits آمد، payers را بازسازی کن
                    instance.payers.all().delete()
                    for s in splits_data:
                        uid = s['user_id']
                        paid = s.get('paid_amount_minor', 0)
                        if paid > 0:
                            ExpensePayer.objects.create(
                                expense=instance, user_id=uid, paid_amount_minor=paid
                            )

        return instance

# --- Recurring Expense Serializer ---
class RecurringExpenseTemplateSerializer(serializers.ModelSerializer):
    """
    Serializer for recurring expense templates.
    """
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = RecurringExpenseTemplate
        fields = [
            'id',
            'group',
            'description',
            'amount_minor',
            'schedule',
            'next_run_at',
            'is_active',
            'created_by',
        ]
        read_only_fields = ['created_by']