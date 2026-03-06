from django.urls import path, include

urlpatterns = [
    path("api/auth/", include("api.urls.auth")),
    # Development / planner APIs
    path("api/development/", include("api.urls.development")),
    # Backwards-compatible v1 prefix
    path("api/v1/development/", include("api.urls.development")),
    # Plot APIs
    path("api/v1/", include("api.urls.plots")),
    path("api/", include("api.urls.plots")),
]
