# accounts/throttling.py
from rest_framework.throttling import SimpleRateThrottle

class UsernameAvailabilityThrottle(SimpleRateThrottle):
    scope = "username_availability"
    def get_cache_key(self, request, view):
        ident = self.get_ident(request)  # معمولا IP
        return f"throttle:avail:{ident}"

class RegisterThrottle(SimpleRateThrottle):
    scope = "register"
    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return f"throttle:register:{ident}"
