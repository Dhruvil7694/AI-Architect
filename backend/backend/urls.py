from django.urls import path, include
from django.contrib import admin

urlpatterns = [
    # Django admin
    path("admin/", admin.site.urls),
    # User management and auth
    path("api/", include("users.urls")),
    # Development / planner APIs
    path("api/development/", include("api.urls.development")),
    # Backwards-compatible v1 prefix
    path("api/v1/development/", include("api.urls.development")),
    # Plot APIs
    path("api/v1/", include("api.urls.plots")),
    path("api/", include("api.urls.plots")),
    # AI-assisted planner
    path("api/planner/", include("api.urls.planner")),
    # Debug and validation endpoints
    path("api/debug/", include("api.urls.debug")),
]
