from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .errors import ExternalServiceError, PlanningError
from .planner import plan_trip
from .serializers import PlanRequestSerializer


class PlanTripView(APIView):
    def post(self, request: Request) -> Response:
        serializer = PlanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            plan = plan_trip(**serializer.validated_data)
        except PlanningError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ExternalServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(plan)
