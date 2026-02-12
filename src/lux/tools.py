from __future__ import annotations

import re
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
    allow_unsafe: bool = False,
) -> CmdResult:
    safety = check_command_safety(command)
    if safety["level"] == "deny":
        return CmdResult(
            command=command,
            exit_code=126,
            stdout="",
            stderr=f"Refused to run denied command: {safety['reason']}",
        )
    if safety["level"] == "unsafe" and not allow_unsafe:
        return CmdResult(
            command=command,
            exit_code=126,
            stdout="",
            stderr=f"Refused to run unsafe command without --unsafe: {safety['reason']}",
        )
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


def check_command_safety(command: str) -> dict[str, str]:
    """
    Very small, conservative heuristic.
    - level=deny: never allow (too dangerous)
    - level=unsafe: allow only if user opted-in
    - level=ok: fine
    """
    c = command.strip().lower()
    if not c:
        return {"level": "deny", "reason": "empty command"}

    # Hard deny: destructive / exfil / remote code execution patterns.
    deny_patterns = [
        r"\brm\s+-rf\b",
        r"\bsudo\b",
        r"\bshutdown\b",
        r"\breboot\b",
        r"\bmkfs\b",
        r":\(\)\s*\{\s*:\s*\|\s*:\s*;\s*\}\s*;",  # fork bomb
        r"\bcurl\b.*\|\s*(sh|bash|zsh)\b",
        r"\bwget\b.*\|\s*(sh|bash|zsh)\b",
    ]
    for pat in deny_patterns:
        if re.search(pat, c):
            return {"level": "deny", "reason": f"matched pattern {pat!r}"}

    # Unsafe: can change repo state or write broadly; allow only with explicit opt-in.
    unsafe_patterns = [
        r"\bgit\s+push\b",
        r"\bgit\s+reset\b",
        r"\bgit\s+clean\b",
        r"\bgit\s+rebase\b",
        r"\bchmod\b",
        r"\bchown\b",
        r">\s*/",  # redirect to absolute path
        r"\btee\b\s+/",  # tee to absolute path
    ]
    for pat in unsafe_patterns:
        if re.search(pat, c):
            return {"level": "unsafe", "reason": f"matched pattern {pat!r}"}

    return {"level": "ok", "reason": "no risky patterns detected"}
