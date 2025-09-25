import uuid
from django.conf import settings
from django.db import models

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
    description = models.CharField(max_length=255)
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

    # FX-related fields have been removed.

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
    created_at = models.DateTimeField(auto_now_add=True)

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

    def __str__(self):
        return f"Recurring: {self.description}"