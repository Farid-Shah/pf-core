from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    
    # API routes
    path('api/v1/', include('splitpay_backend.api_router')),  # All apps except accounts
    path("api/v1/", include("accounts.urls")),  # Accounts separate (for auth endpoints)
    
    # DRF browsable API auth
    path('api-auth/', include('rest_framework.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)