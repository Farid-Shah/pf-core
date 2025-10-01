from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

User = get_user_model()

def check_handle_availability(username: str) -> tuple[bool, str | None]:
    """
    Returns:
      (True, None)                 => available
      (False, <reason string>)     => invalid_format | too_short | too_long | reserved | taken
    """
    dummy = User(username=username)
    try:
        dummy.clean_username_policy(username, changing=False)
        return True, None
    except ValidationError as e:
        reason = e.messages[0] if e.messages else "invalid"
        return False, reason
