# Contributing

Use Python 3.12, uv, conventional commits, and one cohesive change per commit.

Every source adapter or processor change requires tests for schema drift, null handling, empty snapshots, units, timestamps, stable IDs, and failure propagation where relevant. Every vnstock change must update `docs/vnstock-compatibility.md` in the same commit.

Configuration changes update `.env.example` and `docs/operations.md`. Architecture or delivery changes update `docs/architecture.md`. All source, comments, test data, configuration, commit messages, and documentation must be written in English. Provider values that must match non-English source data are represented with escaped Unicode literals and documented in English.
