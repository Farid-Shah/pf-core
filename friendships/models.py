import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q, F

class FriendRequest(models.Model):
    """Model to initiate connections between users."""
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        DECLINED = 'DECLINED', 'Declined'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_friend_requests'
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_friend_requests'
    )
    message = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=~Q(from_user=F('to_user')),
                name='no_self_request'
            ),
            models.UniqueConstraint(
                fields=['from_user', 'to_user'],
                condition=Q(status='PENDING'),
                name='unique_pending_pair'
            )
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"Request from {self.from_user} to {self.to_user} ({self.status})"

class Friendship(models.Model):
    """Model for established connections between users."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # To enforce uniqueness, user_low should always have a lower ID than user_high
    user_low = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='friendships_low'
    )
    user_high = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='friendships_high'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user_low', 'user_high'],
                name='unique_friendship_pair'
            ),
            models.CheckConstraint(
                check=Q(user_low_id__lt=F('user_high_id')),
                name='user_low_lt_user_high'
            )
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"Friendship between {self.user_low} and {self.user_high}"