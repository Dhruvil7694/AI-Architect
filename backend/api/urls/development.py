from __future__ import annotations

from django.urls import path

from api.views.development import (
    OptimalDevelopmentFloorPlanAPIView,
    SiteMetricsAPIView,
)
from api.views.plan_jobs import (
    PlanJobCreateAPIView,
    PlanJobStatusAPIView,
    PlanJobResultAPIView,
)


urlpatterns = [
    path(
        "optimal-floor-plan/",
        OptimalDevelopmentFloorPlanAPIView.as_view(),
        name="optimal-development-floor-plan",
    ),
    path(
        "site-metrics/<str:plot_id>/",
        SiteMetricsAPIView.as_view(),
        name="site-metrics",
    ),
    path(
        "plan/",
        PlanJobCreateAPIView.as_view(),
        name="plan-job-create",
    ),
    path(
        "plan-jobs/<uuid:job_id>/status/",
        PlanJobStatusAPIView.as_view(),
        name="plan-job-status",
    ),
    path(
        "plan-jobs/<uuid:job_id>/result/",
        PlanJobResultAPIView.as_view(),
        name="plan-job-result",
    ),
]

