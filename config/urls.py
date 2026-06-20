# config/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Django admin
    path("admin/", admin.site.urls),

    # DRF browsable API session login and logout.
    # Accessible at /api-auth/login/ and /api-auth/logout/
    # Required for the browsable API to authenticate via the browser.
    path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),

    # ── Application routes — uncommented as each milestone is completed ────────
    #
    # Week 1 — Document upload and status:
    # path("api/v1/", include("apps.documents.urls")),
    path("api/documents/", include("apps.documents.urls")),   # NEW
    #
    # Week 3 — Knowledge graph endpoints:
    # path("api/v1/", include("apps.graph.urls")),
    #
    # Week 4 — Search and question answering:
    # path("api/v1/", include("apps.api.urls")),
    path("api/", include("apps.api.urls")),                    # NEW
]

# Serve uploaded media files during development.
# In production, delegate to nginx or a CDN. Never use this in production.
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )