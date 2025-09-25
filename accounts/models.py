import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    """Auth principal for the application."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)

    # The default_currency field has been removed.
    # username, first_name, last_name, and timestamps are inherited from AbstractUser.

    def __str__(self):
        return self.username