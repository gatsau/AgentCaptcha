"""Sliding-window rate limiter middleware for FastAPI."""
import time
from collections import defaultdict, deque

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-IP sliding-window rate limiter.
    Allows RATE_LIMIT_REQUESTS requests per RATE_LIMIT_WINDOW_S seconds.
    WebSocket upgrade requests count toward the limit.
    """

    def __init__(self, app):
        super().__init__(app)
        # ip → deque of request timestamps
        self._windows: dict[str, deque] = defaultdict(deque)

    def _get_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next) -> Response:
        ip = self._get_ip(request)
        now = time.monotonic()
        window = settings.rate_limit_window_s
        limit = settings.rate_limit_requests

        dq = self._windows[ip]

        # Evict timestamps outside the window
        while dq and now - dq[0] > window:
            dq.popleft()

        if len(dq) >= limit:
            return Response(
                content='{"detail":"rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(window)},
            )

        dq.append(now)
        return await call_next(request)
