import uuid
from django.conf import settings
from django.db import models

class Group(models.Model):
    """Expense containers for users."""
    class GroupType(models.TextChoices):
        HOUSEHOLD = 'HOUSEHOLD', 'Household'
        TRIP = 'TRIP', 'Trip'
        PROJECT = 'PROJECT', 'Project'
        OTHER = 'OTHER', 'Other'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=GroupType.choices, default=GroupType.OTHER)
    # The default_currency field has been removed.
    simplify_debts = models.BooleanField(default=False)
    invite_link = models.URLField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class GroupMember(models.Model):
    """Membership and roles within a group."""
    class Role(models.TextChoices):
        OWNER = 'OWNER', 'Owner'
        ADMIN = 'ADMIN', 'Admin'
        MEMBER = 'MEMBER', 'Member'
        VIEWER = 'VIEWER', 'Viewer'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='group_memberships')
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('group', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} in {self.group} as {self.get_role_display()}"