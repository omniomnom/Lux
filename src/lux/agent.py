from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional

from .llm_ollama import OllamaConfig, OllamaError, ollama_available, ollama_chat, parse_json_block
from .tools import read_text, run_cmd, write_text
from .util import CmdResult


ActionType = Literal["read_file", "write_file", "run", "finish"]


@dataclass
class AgentConfig:
    model: str = "llama3.1:8b"
    max_iters: int = 12
    verify_cmd: Optional[str] = None
    temperature: float = 0.2
    dry_run: bool = False
    allow_unsafe: bool = False
    max_consecutive_failures: int = 4


SYSTEM = """You are Lux, a local-first coding agent.

You MUST respond with a single JSON object, no prose.

You can issue one action at a time. Pick the smallest next action.

Available actions:
- read_file: { "type":"read_file", "path":"relative/path.txt" }
- write_file: { "type":"write_file", "path":"relative/path.txt", "content":"...full file content..." }
- run: { "type":"run", "command":"shell command" }
- finish: { "type":"finish", "summary":"what you did", "next":"what user should do next" }

Rules:
- Keep paths relative to repo root.
- Prefer editing the minimal number of files.
- After making edits, if verify_cmd is provided, run it to confirm.
- If a run/verify fails, inspect stderr/stdout and self-correct.
"""


def _context_snapshot(root: Path, last_result: Optional[CmdResult]) -> dict[str, Any]:
    snap: dict[str, Any] = {
        "repo_root": str(root),
        "last_result": None,
    }
    if last_result is not None:
        snap["last_result"] = {
            "command": last_result.command,
            "exit_code": last_result.exit_code,
            "stdout_tail": (last_result.stdout or "")[-4000:],
            "stderr_tail": (last_result.stderr or "")[-4000:],
        }
    return snap


def _prompt(goal: str, *, verify_cmd: Optional[str], context: dict[str, Any]) -> str:
    return json.dumps(
        {
            "goal": goal,
            "verify_cmd": verify_cmd,
            "context": context,
            "note": "Remember: output ONLY a JSON object for the next action.",
        },
        indent=2,
    )


def run_agent(root: Path, goal: str, cfg: AgentConfig) -> list[dict[str, Any]]:
    """
    Returns a trace of actions/results.
    """
    trace: list[dict[str, Any]] = []
    last: Optional[CmdResult] = None
    consecutive_failures = 0
    seen_actions: set[str] = set()

    if not ollama_available():
        if cfg.dry_run:
            return [
                {
                    "step": 0,
                    "action": {"type": "finish"},
                    "result": {
                        "summary": "Dry-run: Ollama is not installed, so the agent cannot generate actions yet.",
                        "next": "Install Ollama (`brew install ollama`), start it (`ollama serve`), then pull a model (e.g. `ollama pull llama3.1:8b`). After that, rerun without --dry-run.",
                    },
                }
            ]
        return [
            {
                "step": 0,
                "error": "Ollama is not installed or not on PATH. Run `lux doctor` for setup instructions.",
            }
        ]

    llm_cfg = OllamaConfig(model=cfg.model, temperature=cfg.temperature)

    for step in range(cfg.max_iters):
        context = _context_snapshot(root, last)
        prompt = _prompt(goal, verify_cmd=cfg.verify_cmd, context=context)

        if last is not None and last.exit_code != 0:
            consecutive_failures += 1
        else:
            consecutive_failures = 0

        if consecutive_failures >= cfg.max_consecutive_failures:
            trace.append(
                {
                    "step": step,
                    "action": {"type": "finish"},
                    "result": {
                        "summary": "Stopped after repeated failures (self-fix budget exceeded).",
                        "next": "Inspect the last failure (stdout/stderr tails in trace). If you want, paste that error here and we can tighten the verifier or guardrails.",
                    },
                }
            )
            break

        try:
            raw = ollama_chat(prompt=prompt, config=llm_cfg, system=SYSTEM)
        except OllamaError as e:
            trace.append({"step": step, "error": f"OllamaError: {e}"})
            break

        try:
            action = parse_json_block(raw)
        except Exception as e:
            trace.append({"step": step, "error": f"Bad model output: {e}", "raw": raw})
            break

        if not isinstance(action, dict) or "type" not in action:
            trace.append({"step": step, "error": "Action must be an object with a 'type' field", "raw": raw})
            break

        action_key = json.dumps(action, sort_keys=True)
        if action_key in seen_actions:
            trace.append(
                {
                    "step": step,
                    "action": {"type": "finish"},
                    "result": {
                        "summary": "Stopped: detected repeating the same action (loop guard).",
                        "next": "Try adding a verifier command (--verify ...) and/or rephrase the goal to be more specific about what success looks like.",
                    },
                }
            )
            break
        seen_actions.add(action_key)

        a_type: ActionType = action["type"]  # type: ignore[assignment]
        record: dict[str, Any] = {"step": step, "action": action}

        if a_type == "read_file":
            path = str(action.get("path", ""))
            if not path:
                record["error"] = "Missing path"
            else:
                content = read_text(root, path)
                record["result"] = {"path": path, "content": content}
            trace.append(record)
            last = None
            continue

        if a_type == "write_file":
            path = str(action.get("path", ""))
            content = action.get("content", None)
            if not path or content is None:
                record["error"] = "Missing path/content"
                trace.append(record)
                last = None
                continue

            if cfg.dry_run:
                record["result"] = {"dry_run": True, "path": path, "bytes": len(str(content).encode("utf-8"))}
                trace.append(record)
            else:
                write_text(root, path, str(content))
                record["result"] = {"path": path, "bytes": len(str(content).encode("utf-8"))}
                trace.append(record)

            # After an edit, immediately verify if configured.
            if cfg.verify_cmd:
                if cfg.dry_run:
                    last = CmdResult(command=cfg.verify_cmd, exit_code=0, stdout="(dry-run)", stderr="")
                    trace.append({"step": step, "verify": {"dry_run": True, "command": cfg.verify_cmd}})
                else:
                    last = run_cmd(root, cfg.verify_cmd, allow_unsafe=cfg.allow_unsafe)
                    trace.append({"step": step, "verify": vars(last)})
            else:
                last = None
            continue

        if a_type == "run":
            command = str(action.get("command", ""))
            if not command:
                record["error"] = "Missing command"
                trace.append(record)
                last = None
                continue

            if cfg.dry_run:
                last = CmdResult(command=command, exit_code=0, stdout="(dry-run)", stderr="")
                record["result"] = vars(last)
            else:
                last = run_cmd(root, command, allow_unsafe=cfg.allow_unsafe)
                record["result"] = vars(last)

            trace.append(record)
            continue

        if a_type == "finish":
            record["result"] = {
                "summary": str(action.get("summary", "")).strip(),
                "next": str(action.get("next", "")).strip(),
            }
            trace.append(record)
            break

        record["error"] = f"Unknown action type: {a_type}"
        trace.append(record)
        last = None

    return trace
