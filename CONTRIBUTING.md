# Contributing

Use Python 3.12, uv, conventional commits, and one cohesive change per commit.

Every source adapter or processor change requires tests for schema drift, null handling, empty snapshots, units, timestamps, stable IDs, and failure propagation where relevant. Every vnstock change must update `docs/vnstock-compatibility.md` in the same commit.

Configuration changes update `.env.example` and `docs/operations.md`. Architecture or delivery changes update `docs/architecture.md`. All source, comments, test data, configuration, commit messages, and documentation must be written in English. Provider values that must match non-English source data are represented with escaped Unicode literals and documented in English.

## Documentation ownership

| Document | Update when |
|---|---|
| `README.md` | Setup, entry points, verification commands, or document links change |
| `docs/architecture.md` | Pipeline stages, ownership, storage, scheduling, or delivery semantics change |
| `docs/operations.md` | Commands, probes, settings, dependencies, migrations, or recovery procedures change |
| `docs/vnstock-compatibility.md` | The vnstock version, source, method, schema mapping, units, or limitations change |

Documentation is part of the implementation. If a code change has no documentation impact, record that conclusion in the commit or pull request description.
