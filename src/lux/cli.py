from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import AgentConfig, run_agent
from .llm_ollama import ollama_available, ollama_list_models
from .util import repo_root_from_cwd


def cmd_doctor(_: argparse.Namespace) -> int:
    ok = ollama_available()
    print(f"ollama: {'OK' if ok else 'NOT FOUND'}")
    if ok:
        res = ollama_list_models()
        if res.exit_code == 0:
            print("models:")
            print(res.stdout.rstrip())
        else:
            print("ollama list failed:")
            print(res.stderr.rstrip(), file=sys.stderr)
    else:
        print("Install Ollama, then pull a model. Example:")
        print("  brew install ollama")
        print("  ollama serve")
        print("  ollama pull llama3.1:8b")
    return 0 if ok else 1


def cmd_run(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else repo_root_from_cwd()
    cfg = AgentConfig(
        model=args.model,
        max_iters=args.max_iters,
        verify_cmd=args.verify,
        temperature=args.temperature,
        dry_run=args.dry_run,
        allow_unsafe=args.unsafe,
        max_consecutive_failures=args.max_failures,
    )
    trace = run_agent(root=root, goal=args.goal, cfg=cfg)
    print(json.dumps(trace, indent=2))
    # If there is any error entry, return non-zero.
    for entry in trace:
        if "error" in entry:
            return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lux", description="Lux: local-first agent loop (Ollama-backed).")
    sub = p.add_subparsers(required=True)

    d = sub.add_parser("doctor", help="Check local LLM (Ollama) availability.")
    d.set_defaults(func=cmd_doctor)

    r = sub.add_parser("run", help="Run the agent on a goal.")
    r.add_argument("goal", help="What you want the agent to do.")
    r.add_argument("--root", default=None, help="Repo root (defaults to cwd).")
    r.add_argument("--model", default="llama3.1:8b", help="Ollama model name.")
    r.add_argument("--max-iters", type=int, default=12, help="Max agent steps.")
    r.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature.")
    r.add_argument(
        "--verify",
        default=None,
        help="Verification command to run after edits (e.g. 'python -m unittest -q' or 'pytest -q').",
    )
    r.add_argument(
        "--unsafe",
        action="store_true",
        help="Allow risky commands (e.g. git push/reset/clean, chmod). Still denies rm -rf/sudo/curl|sh.",
    )
    r.add_argument(
        "--max-failures",
        type=int,
        default=4,
        help="Stop after this many consecutive command/verify failures.",
    )
    r.add_argument("--dry-run", action="store_true", help="Do not write files or run commands.")
    r.set_defaults(func=cmd_run)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
