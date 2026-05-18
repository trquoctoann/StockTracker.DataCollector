from __future__ import annotations


class DataCollectorError(Exception):
    pass


class PipelineError(DataCollectorError):
    pass


class ConfigurationError(DataCollectorError):
    pass


class SinkError(DataCollectorError):
    pass


class SourceError(DataCollectorError):
    pass
