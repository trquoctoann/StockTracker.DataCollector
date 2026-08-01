from app.middleware.metrics import HttpMetrics


def test_metrics_render_low_cardinality_labels() -> None:
    metrics = HttpMetrics("collector")
    metrics.observe("GET", 200, 0.25)

    output = metrics.render()

    assert 'service="collector",method="GET",status="200"' in output
    assert "stocktracker_http_request_duration_seconds_count" in output
    assert "/run/" not in output
