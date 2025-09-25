import uuid
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

class ActivityLog(models.Model):
    """Audit trail and notifications source."""
    class Verb(models.TextChoices):
        CREATED = 'CREATED', 'Created'
        UPDATED = 'UPDATED', 'Updated'
        DELETED = 'DELETED', 'Deleted'
        COMMENTED = 'COMMENTED', 'Commented'
        # Add other verbs as needed

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='activities'
    )
    verb = models.CharField(max_length=20, choices=Verb.choices)
    
    # Generic relation to the entity that was acted upon
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    entity_id = models.UUIDField()
    entity = GenericForeignKey('content_type', 'entity_id')
    
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['content_type', 'entity_id', 'created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.actor} {self.verb.lower()} {self.content_type.model} {self.entity_id}"