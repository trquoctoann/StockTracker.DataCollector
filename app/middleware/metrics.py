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
        self._pipeline_runs: dict[tuple[str, str], int] = defaultdict(int)
        self._pipeline_duration_sum: dict[tuple[str, str], float] = defaultdict(float)
        self._pipeline_last_success: dict[str, float] = {}
        self._lock = Lock()

    def observe(self, method: str, status: int, duration: float) -> None:
        key = (method, status)
        with self._lock:
            self._requests[key] += 1
            self._duration_sum[key] += duration

    def observe_pipeline(self, pipeline: str, status: str, duration: float, finished_at: float) -> None:
        key = (pipeline, status)
        with self._lock:
            self._pipeline_runs[key] += 1
            self._pipeline_duration_sum[key] += duration
            if status == "completed":
                self._pipeline_last_success[pipeline] = finished_at

    def render(self) -> str:
        lines = [
            "# HELP stocktracker_http_requests_total Total HTTP requests.",
            "# TYPE stocktracker_http_requests_total counter",
        ]
        with self._lock:
            items = sorted(self._requests.items())
            durations = dict(self._duration_sum)
            pipeline_runs = sorted(self._pipeline_runs.items())
            pipeline_durations = dict(self._pipeline_duration_sum)
            pipeline_last_success = dict(self._pipeline_last_success)
        for (method, status), count in items:
            labels = f'service="{self._service}",method="{method}",status="{status}"'
            lines.append(f"stocktracker_http_requests_total{{{labels}}} {count}")
            lines.append(f"stocktracker_http_request_duration_seconds_sum{{{labels}}} {durations[(method, status)]}")
            lines.append(f"stocktracker_http_request_duration_seconds_count{{{labels}}} {count}")
        lines.extend(
            [
                "# HELP stocktracker_pipeline_runs_total Total pipeline runs by terminal status.",
                "# TYPE stocktracker_pipeline_runs_total counter",
            ]
        )
        for (pipeline, status), count in pipeline_runs:
            labels = f'pipeline="{pipeline}",status="{status}"'
            lines.append(f"stocktracker_pipeline_runs_total{{{labels}}} {count}")
            lines.append(
                f"stocktracker_pipeline_duration_seconds_sum{{{labels}}} {pipeline_durations[(pipeline, status)]}"
            )
            lines.append(f"stocktracker_pipeline_duration_seconds_count{{{labels}}} {count}")
        lines.append("# HELP stocktracker_pipeline_last_success_timestamp_seconds Last successful pipeline completion.")
        lines.append("# TYPE stocktracker_pipeline_last_success_timestamp_seconds gauge")
        for pipeline, timestamp in sorted(pipeline_last_success.items()):
            lines.append(f'stocktracker_pipeline_last_success_timestamp_seconds{{pipeline="{pipeline}"}} {timestamp}')
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
