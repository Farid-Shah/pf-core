"""
Group API URL configuration.

The DefaultRouter automatically generates URLs for:
- Standard CRUD operations (list, create, retrieve, update, delete)
- Custom actions decorated with @action

Auto-generated endpoints:
- GET    /groups/                           - List user's groups
- POST   /groups/                           - Create a new group
- GET    /groups/{id}/                      - Retrieve group details
- PUT    /groups/{id}/                      - Update group settings
- PATCH  /groups/{id}/                      - Partial update
- DELETE /groups/{id}/                      - Delete group

- POST   /groups/{id}/add_member/           - Add a member
- DELETE /groups/{id}/remove_member/{user_id}/ - Remove a member
- POST   /groups/{id}/change_role/          - Change member role
- POST   /groups/{id}/transfer_ownership/   - Transfer ownership
- POST   /groups/{id}/leave/                - Leave group
- POST   /groups/{id}/generate_invite/      - Generate invite link
- DELETE /groups/{id}/revoke_invite/        - Revoke invite link
- POST   /groups/join/{invite_link}/        - Join via invite link
"""

from rest_framework.routers import DefaultRouter
from .views import GroupViewSet

router = DefaultRouter()
router.register(r'groups', GroupViewSet, basename='group')

urlpatterns = router.urls