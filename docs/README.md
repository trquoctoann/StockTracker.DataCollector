# DataCollector documentation

| Document | Purpose | Update when |
|---|---|---|
| [architecture.md](architecture.md) | Pipeline components, control plane, delivery paths, and reliability rules | Pipeline stages, ownership, storage, scheduling, or delivery semantics change |
| [operations.md](operations.md) | Settings, migrations, health, execution, resume, replay, and recovery | Commands, probes, settings, dependencies, or failure procedures change |
| [vnstock-compatibility.md](vnstock-compatibility.md) | Pinned SDK calls, provider mappings, data units, source limitations, and smoke coverage | vnstock version, source, method, schema mapping, or known limitation changes |

Documentation is part of the implementation. Every behavior, configuration, dependency, or operational change must update the relevant document in the same commit. All project content is written in English.
