from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class HttpMetrics:
    def __init__(self, service: str) -> None:
        self._service = service.replace('"', '\\"')
        self._requests: dict[tuple[str, int], int] = defaultdict(int)
        self._duration_sum: dict[tuple[str, int], float] = defaultdict(float)
        self._lock = Lock()

    def observe(self, method: str, status: int, duration: float) -> None:
        key = (method, status)
        with self._lock:
            self._requests[key] += 1
            self._duration_sum[key] += duration

    def render(self) -> str:
        lines = [
            "# HELP stocktracker_http_requests_total Total HTTP requests.",
            "# TYPE stocktracker_http_requests_total counter",
        ]
        with self._lock:
            items = sorted(self._requests.items())
            durations = dict(self._duration_sum)
        for (method, status), count in items:
            labels = f'service="{self._service}",method="{method}",status="{status}"'
            lines.append(f"stocktracker_http_requests_total{{{labels}}} {count}")
            lines.append(f"stocktracker_http_request_duration_seconds_sum{{{labels}}} {durations[(method, status)]}")
            lines.append(f"stocktracker_http_request_duration_seconds_count{{{labels}}} {count}")
        return "\n".join(lines) + "\n"


class HttpMetricsMiddleware:
    def __init__(self, app: ASGIApp, metrics: HttpMetrics) -> None:
        self.app = app
        self._metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") == "/metrics":
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        response_status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            self._metrics.observe(scope.get("method", "UNKNOWN"), response_status, time.monotonic() - started)
