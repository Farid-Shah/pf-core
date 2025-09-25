import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q

class Payment(models.Model):
    """Settle-up transfers impacting balances."""
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        FAILED = 'FAILED', 'Failed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_payments'
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_payments'
    )
    amount_minor = models.BigIntegerField()
    # The `currency` field has been removed.
    group = models.ForeignKey(
        'groups.Group', on_delete=models.SET_NULL, null=True, blank=True, related_name='payments'
    )
    method = models.CharField(max_length=50, blank=True)
    external_reference = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['group', 'created_at']),
            models.Index(fields=['from_user', 'to_user', 'status']),
        ]
        constraints = [
            models.CheckConstraint(
                check=~Q(from_user=models.F('to_user')),
                name='payment_from_to_not_equal'
            ),
            models.CheckConstraint(
                check=Q(amount_minor__gt=0),
                name='payment_amount_positive'
            )
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment from {self.from_user} to {self.to_user} ({self.status})"