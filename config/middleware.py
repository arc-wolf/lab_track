import logging
import time
import uuid

logger = logging.getLogger(__name__)


class RequestIDAndPerformanceMiddleware:
    """Production-grade middleware adding X-Request-ID headers and logging slow requests (>500ms)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.request_id = request_id

        start_time = time.time()
        response = self.get_response(request)
        duration_ms = (time.time() - start_time) * 1000

        response["X-Request-ID"] = request_id

        if duration_ms > 500:
            logger.warning(
                "SLOW REQUEST [%s]: %s %s took %.2fms (status %s)",
                request_id,
                request.method,
                request.path,
                duration_ms,
                response.status_code,
            )

        return response
