from app.middleware.metrics import HttpMetrics


def test_metrics_render_low_cardinality_labels() -> None:
    metrics = HttpMetrics("collector")
    metrics.observe("GET", 200, 0.25)

    output = metrics.render()

    assert 'service="collector",method="GET",status="200"' in output
    assert "stocktracker_http_request_duration_seconds_count" in output
    assert "/run/" not in output


def test_metrics_render_pipeline_outcomes() -> None:
    metrics = HttpMetrics("collector")
    metrics.observe_pipeline("vnstock_market_data", "completed", 12.5, 1_788_051_600.0)
    metrics.observe_pipeline("vnstock_market_data", "failed", 2.0, 1_788_051_700.0)

    output = metrics.render()

    assert 'stocktracker_pipeline_runs_total{pipeline="vnstock_market_data",status="completed"} 1' in output
    assert 'stocktracker_pipeline_runs_total{pipeline="vnstock_market_data",status="failed"} 1' in output
    assert 'stocktracker_pipeline_last_success_timestamp_seconds{pipeline="vnstock_market_data"} 1788051600.0' in output
