from __future__ import annotations

from django.urls import path

from api.views.plots import PlotListAPIView, PlotDetailAPIView


urlpatterns = [
    path("plots/", PlotListAPIView.as_view(), name="plot-list"),
    path("plots/<str:id>/", PlotDetailAPIView.as_view(), name="plot-detail"),
]

