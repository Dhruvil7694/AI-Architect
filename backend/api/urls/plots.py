from __future__ import annotations

from django.urls import path

from api.views.plots import PlotListAPIView, PlotDetailAPIView, TpBundleAPIView
from api.views.block_labels import BlockLabelListAPIView
from api.views.roads import RoadListAPIView


urlpatterns = [
    path("plots/", PlotListAPIView.as_view(), name="plot-list"),
    path("plots/<str:id>/", PlotDetailAPIView.as_view(), name="plot-detail"),
    path("block-labels/", BlockLabelListAPIView.as_view(), name="block-label-list"),
    path("roads/", RoadListAPIView.as_view(), name="road-list"),
    path("map/tp-bundle/", TpBundleAPIView.as_view(), name="tp-bundle"),
]
