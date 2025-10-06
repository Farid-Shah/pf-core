import uuid
from django.conf import settings
from django.db import models, transaction
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class ExpenseActionRequest(models.Model):
    ACTION_DELETE = "delete"
    ACTION_EDIT   = "edit"
    ACTION_CHOICES = [(ACTION_DELETE, "Delete"), (ACTION_EDIT, "Edit")]

    expense       = models.ForeignKey("expenses.Expense", on_delete=models.CASCADE, related_name="action_requests")
    action        = models.CharField(max_length=16, choices=ACTION_CHOICES)
    payload       = models.JSONField(null=True, blank=True)  # برای edit: PATCH payload را نگه می‌داریم
    requested_by  = models.ForeignKey(User, on_delete=models.CASCADE, related_name="expense_action_requests")
    required_count= models.PositiveIntegerField()            # تعداد کل payerها در لحظهٔ ایجاد
    is_completed  = models.BooleanField(default=False)
    created_at    = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["expense", "action", "is_completed"]),
        ]

class ExpenseActionApproval(models.Model):
    request   = models.ForeignKey(ExpenseActionRequest, on_delete=models.CASCADE, related_name="approvals")
    user      = models.ForeignKey(User, on_delete=models.CASCADE, related_name="expense_action_approvals")
    created_at= models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("request", "user")]

class Category(models.Model):
    """Category tree for expenses."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True, related_name='subcategories'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('name', 'parent')
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name

class Expense(models.Model):
    """Source-of-truth for shared costs."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(
        'groups.Group', on_delete=models.CASCADE, related_name='expenses', null=True, blank=True
    )
    description = models.CharField(max_length=255, blank=True, default="")
    details = models.TextField(blank=True)
    total_amount_minor = models.BigIntegerField()
    # The `currency` field has been removed. All amounts are in the system's default currency.
    date = models.DateField()
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_expenses'
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_expenses'
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    CALC_TOTAL = "TOTAL"
    CALC_ITEMIZED = "ITEMIZED"
    CALC_MODE_CHOICES = [
        (CALC_TOTAL, "Total only"),
        (CALC_ITEMIZED, "Itemized"),
    ]
    calc_mode = models.CharField(
        max_length=10, choices=CALC_MODE_CHOICES, default=CALC_TOTAL
    )

    EQUALLY = "equally"
    UNEQUALLY = "unequally"
    SHARES = "shares"
    BREAKDOWN_CHOICES = [
        (EQUALLY, "Equally"),
        (UNEQUALLY, "Unequally"),
        (SHARES, "By shares"),
    ]
    breakdown_method = models.CharField(
        max_length=10, choices=BREAKDOWN_CHOICES, null=True, blank=True,
        help_text="Applies only when calc_mode=TOTAL"
    )

    class Meta:
        indexes = [models.Index(fields=['group', 'date']), models.Index(fields=['created_at'])]
        ordering = ['-date', '-created_at']

    def __str__(self):
        return self.description

# ExpensePayer, ExpenseParticipant, ExpenseComment, and Attachment models remain the same.
# They did not have direct currency fields.

class ExpensePayer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='payers')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payments_made')
    paid_amount_minor = models.BigIntegerField()

    class Meta:
        indexes = [models.Index(fields=['user', 'expense'])]
        unique_together = ('expense', 'user')

    def __str__(self):
        return f"{self.user} paid for {self.expense}"

class ExpenseParticipant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='expenses_participated')
    owed_amount_minor = models.BigIntegerField()

    class Meta:
        indexes = [models.Index(fields=['user', 'expense'])]
        unique_together = ('expense', 'user')

    def __str__(self):
        return f"{self.user} participates in {self.expense}"

class ExpenseComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='expense_comments')
    content = models.TextField()
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment by {self.user} on {self.expense}"

class Attachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='attachments/%Y/%m/%d/')
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveIntegerField()
    is_receipt = models.BooleanField(default=False)  # NEW
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['expense'],
                condition=models.Q(is_receipt=True),
                name='unique_receipt_per_expense'
            )
        ]

    def __str__(self):
        return f"Attachment for {self.expense}"


class RecurringExpenseTemplate(models.Model):
    """Template to generate periodic expenses."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(
        'groups.Group', on_delete=models.CASCADE, related_name='recurring_expenses', null=True, blank=True
    )
    description = models.CharField(max_length=255)
    amount_minor = models.BigIntegerField()
    # The `currency` field has been removed.
    schedule = models.CharField(max_length=100, help_text="e.g., cron expression or 'monthly'")
    next_run_at = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Recurring: {self.description}"


class ExpenseItem(models.Model):
    """Line item for ITEMIZED expenses."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='items')
    title = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("1.000"))
    unit_price_minor = models.BigIntegerField()  # minor units (e.g., rials)

    # اختیاری: category = models.ForeignKey(Category, ... , null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['expense'])]

    def __str__(self):
        return f"{self.title} × {self.quantity}"

    @property
    def total_minor(self) -> int:
        # quantity * unit_price_minor (با گرد کردن مطمئن)
        return int(Decimal(self.unit_price_minor) * self.quantity)

class ExpenseItemShare(models.Model):
    """Per-item share for a user: either by exact amount or by weight."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(ExpenseItem, on_delete=models.CASCADE, related_name='shares')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    amount_minor = models.BigIntegerField(null=True, blank=True)  # اگر مبلغ دقیق آیتم برای کاربر مشخص است
    weight = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)  # اگر بر حسب نسبت تقسیم می‌کنیم

    class Meta:
        indexes = [models.Index(fields=['item', 'user'])]
        constraints = [
            models.CheckConstraint(
                check=(
                    (models.Q(amount_minor__isnull=False) & models.Q(weight__isnull=True)) |
                    (models.Q(amount_minor__isnull=True) & models.Q(weight__isnull=False))
                ),
                name="itemshare_either_amount_or_weight"
            )
        ]

    def __str__(self):
        return f"{self.user} share of {self.item}"