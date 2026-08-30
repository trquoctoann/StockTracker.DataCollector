from __future__ import annotations

import sys
from pathlib import Path

TEXT_SUFFIXES = {
    ".alloy",
    ".cursorrules",
    ".example",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".ps1",
    ".rules",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
TEXT_NAMES = {"Dockerfile", "Jenkinsfile", "LICENSE"}
SKIP_DIRECTORIES = {
    ".audit-cache",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".pyright",
    ".research",
    ".ruff_cache",
    ".venv",
    "__pycache__",
}
SKIP_FILES = {".env"}


def is_project_text(path: Path) -> bool:
    return path.name in TEXT_NAMES or path.suffix.lower() in TEXT_SUFFIXES


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    violations: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.name in SKIP_FILES:
            continue
        if any(part in SKIP_DIRECTORIES for part in path.relative_to(root).parts):
            continue
        if not is_project_text(path):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            violations.append(f"{path.relative_to(root)}: file is not valid UTF-8")
            continue
        for line_number, line in enumerate(lines, start=1):
            if any(ord(character) > 127 for character in line):
                violations.append(f"{path.relative_to(root)}:{line_number}: non-ASCII project text")

    if violations:
        sys.stderr.write("English-only content check failed:\n")
        for violation in violations:
            sys.stderr.write(f"  {violation}\n")
        return 1

    sys.stdout.write("English-only content check passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
