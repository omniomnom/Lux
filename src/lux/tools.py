from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from .util import CmdResult, ensure_under_root


def read_text(root: Path, rel_path: str, max_bytes: int = 200_000) -> str:
    path = ensure_under_root(root, root / rel_path)
    data = path.read_bytes()
    if len(data) > max_bytes:
        data = data[:max_bytes]
    return data.decode("utf-8", errors="replace")


def write_text(root: Path, rel_path: str, content: str) -> None:
    path = ensure_under_root(root, root / rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_cmd(
    root: Path,
    command: str,
    *,
    timeout_s: int = 300,
    env: Optional[dict[str, str]] = None,
) -> CmdResult:
    proc = subprocess.run(
        command,
        cwd=str(root),
        shell=True,
        text=True,
        capture_output=True,
        timeout=timeout_s,
        env=env,
    )
    return CmdResult(
        command=command,
        exit_code=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
    )
