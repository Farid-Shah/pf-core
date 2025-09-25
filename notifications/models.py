import uuid
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

class Notification(models.Model):
    """User-facing notifications."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications'
    )
    content = models.TextField()
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Generic relation to the source of the notification (e.g., an Expense or Payment)
    source_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    source_id = models.UUIDField(null=True, blank=True)
    source = GenericForeignKey('source_content_type', 'source_id')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.user}"