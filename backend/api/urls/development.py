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
    PlanJobCritiqueAPIView,
)
from api.views.floor_core import FloorCoreLayoutAPIView
from api.views.floor_plan import FloorPlanAPIView
from api.views.unit_interior import UnitInteriorAPIView
from api.views.ai_floor_plan import AIFloorPlanAPIView
from api.views.floor_plan_preview_image import FloorPlanPreviewImageAPIView
from api.views.feasibility import FeasibilityAPIView, FeasibilityValidateAPIView
from api.views.plot_exploration import PlotExplorationAPIView


urlpatterns = [
    path(
        "explore/<str:plot_id>/",
        PlotExplorationAPIView.as_view(),
        name="plot-exploration",
    ),
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
    path(
        "plan-jobs/<uuid:job_id>/critique/",
        PlanJobCritiqueAPIView.as_view(),
        name="plan-job-critique",
    ),
    path(
        "floor-plan/",
        FloorPlanAPIView.as_view(),
        name="floor-plan-generate",
    ),
    path(
        "unit-interior/",
        UnitInteriorAPIView.as_view(),
        name="unit-interior-generate",
    ),
    path(
        "floor-core/",
        FloorCoreLayoutAPIView.as_view(),
        name="floor-core-generate",
    ),
    path(
        "ai-floor-plan/",
        AIFloorPlanAPIView.as_view(),
        name="ai-floor-plan",
    ),
    path(
        "floor-plan-preview-image/",
        FloorPlanPreviewImageAPIView.as_view(),
        name="floor-plan-preview-image",
    ),
    path(
        "feasibility/<str:plot_id>/",
        FeasibilityAPIView.as_view(),
        name="feasibility",
    ),
    path(
        "feasibility/<str:plot_id>/validate/",
        FeasibilityValidateAPIView.as_view(),
        name="feasibility-validate",
    ),
]

