from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from .tools import run_cmd
from .util import CmdResult


@dataclass(frozen=True)
class OllamaConfig:
    model: str = "llama3.1:8b"
    temperature: float = 0.2


class OllamaError(RuntimeError):
    pass


def _env_for_ollama() -> dict[str, str]:
    # Keep it simple; respect user's environment.
    env = dict(os.environ)
    return env


def ollama_available() -> bool:
    try:
        res = run_cmd(
            root=_fake_root(),
            command="ollama --version",
            timeout_s=10,
            env=_env_for_ollama(),
        )
        return res.exit_code == 0
    except Exception:
        return False


def _fake_root():
    # run_cmd requires a root; use current directory.
    import pathlib

    return pathlib.Path(os.getcwd()).resolve()


def ollama_list_models() -> CmdResult:
    return run_cmd(
        root=_fake_root(),
        command="ollama list",
        timeout_s=20,
        env=_env_for_ollama(),
    )


def ollama_chat(
    *,
    prompt: str,
    config: OllamaConfig,
    system: Optional[str] = None,
) -> str:
    """
    Calls `ollama run <model>` in a minimal, dependency-free way.

    Note: We avoid the HTTP API to keep setup dead-simple for local use.
    """
    full_prompt = prompt if system is None else f"{system.strip()}\n\n{prompt}"

    # Use stdin to avoid shell escaping issues.
    import subprocess

    try:
        proc = subprocess.run(
            ["ollama", "run", config.model],
            input=full_prompt,
            text=True,
            capture_output=True,
            env=_env_for_ollama(),
        )
    except FileNotFoundError as e:
        raise OllamaError("ollama not found on PATH") from e
    if proc.returncode != 0:
        raise OllamaError(proc.stderr.strip() or "ollama run failed")
    return (proc.stdout or "").strip()


def parse_json_block(text: str) -> Any:
    """
    Tries to extract the first JSON object/array from a model response.
    """
    text = text.strip()
    # Fast path
    try:
        return json.loads(text)
    except Exception:
        pass

    start = None
    for i, ch in enumerate(text):
        if ch in "[{":
            start = i
            break
    if start is None:
        raise ValueError("No JSON found in model output")

    # naive bracket matching
    stack: list[str] = []
    for j in range(start, len(text)):
        ch = text[j]
        if ch in "[{":
            stack.append(ch)
        elif ch in "]}":
            if not stack:
                continue
            stack.pop()
            if not stack:
                candidate = text[start : j + 1]
                return json.loads(candidate)

    raise ValueError("Incomplete JSON in model output")
