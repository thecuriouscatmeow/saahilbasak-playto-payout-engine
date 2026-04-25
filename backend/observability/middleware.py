import uuid
import structlog
from django.utils.deprecation import MiddlewareMixin


class CorrelationIdMiddleware(MiddlewareMixin):
    def process_request(self, request):
        cid = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(correlation_id=cid)
        request.correlation_id = cid

    def process_response(self, request, response):
        cid = getattr(request, "correlation_id", "")
        if cid:
            response["X-Correlation-Id"] = cid
        return response

    def process_exception(self, request, exception):
        structlog.contextvars.clear_contextvars()
