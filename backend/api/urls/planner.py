from __future__ import annotations

from django.urls import path

from api.views.ai_planner import AIPlannerScenariosAPIView


urlpatterns = [
    path(
        "ai_scenarios",
        AIPlannerScenariosAPIView.as_view(),
        name="ai-planner-scenarios",
    ),
]

