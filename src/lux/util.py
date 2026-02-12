from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CmdResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str


def repo_root_from_cwd() -> Path:
    return Path(os.getcwd()).resolve()


def ensure_under_root(root: Path, path: Path) -> Path:
    root = root.resolve()
    path = path.resolve()
    try:
        path.relative_to(root)
    except ValueError as e:
        raise ValueError(f"Refusing to access path outside repo root: {path}") from e
    return path
