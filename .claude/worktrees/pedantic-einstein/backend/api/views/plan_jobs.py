from __future__ import annotations

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from services.plan_job_service import (
    create_plan_job,
    get_plan_job_status,
    get_plan_job_result,
)
from api.serializers.plan_jobs import (
    PlanJobCreateSerializer,
    PlanJobStatusSerializer,
    PlanJobResultSerializer,
)


class PlanJobCreateAPIView(APIView):
    """
    Start an asynchronous plan-generation job for a plot.
    """

    def post(self, request: Request, *args, **kwargs) -> Response:
        serializer = PlanJobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        job = create_plan_job(plot_id=data["plotId"], inputs=data["inputs"])

        return Response({"jobId": str(job.id)}, status=status.HTTP_201_CREATED)


class PlanJobStatusAPIView(APIView):
    """
    Return status/progress for a plan job.
    """

    def get(self, request: Request, job_id: str, *args, **kwargs) -> Response:
        status_payload = get_plan_job_status(job_id)
        serializer = PlanJobStatusSerializer(status_payload)
        return Response(serializer.data)


class PlanJobResultAPIView(APIView):
    """
    Return final plan result (metrics + geometry) for a completed job.
    """

    def get(self, request: Request, job_id: str, *args, **kwargs) -> Response:
        try:
            result_payload = get_plan_job_result(job_id)
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = PlanJobResultSerializer(result_payload)
        return Response(serializer.data)


