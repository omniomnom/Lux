from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import AgentConfig, run_agent
from .llm_ollama import ollama_available, ollama_list_models
from .util import repo_root_from_cwd
from . import voice as voice_mod


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


def cmd_voice(args: argparse.Namespace) -> int:
    if not voice_mod.voice_deps_available():
        print("Voice requires: pip install SpeechRecognition PyAudio pocketsphinx", file=sys.stderr)
        return 1
    root = Path(args.root).resolve() if args.root else repo_root_from_cwd()
    cfg = AgentConfig(
        model=args.model,
        max_iters=12,
        verify_cmd=args.verify,
        temperature=0.2,
        dry_run=False,
        allow_unsafe=False,
        max_consecutive_failures=4,
    )
    while True:
        print("Say your command (or Ctrl+C to exit)...", flush=True)
        goal = voice_mod.listen(timeout_seconds=args.listen_timeout)
        if not goal:
            print("No speech heard. Try again.", file=sys.stderr)
            continue
        if goal.strip().lower() in ("exit", "quit", "stop"):
            break
        print(f"Goal: {goal!r}")
        trace = run_agent(root=root, goal=goal, cfg=cfg)
        for entry in trace:
            if "error" in entry:
                print(json.dumps(entry, indent=2), file=sys.stderr)
        for entry in reversed(trace):
            if "result" in entry and isinstance(entry.get("result"), dict):
                summary = entry["result"].get("summary") or entry["result"].get("next")
                if summary:
                    print(summary)
                    if not getattr(args, "no_speak", False):
                        voice_mod.speak(summary)
                    break
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    goal = getattr(args, "goal", None)
    if getattr(args, "voice", False):
        if not voice_mod.voice_deps_available():
            print("Voice input requires: pip install SpeechRecognition PyAudio pocketsphinx", file=sys.stderr)
            return 1
        print("Listening for your command...", flush=True)
        heard = voice_mod.listen(timeout_seconds=getattr(args, "listen_timeout", 10.0))
        if not heard:
            print("No speech heard or recognition failed.", file=sys.stderr)
            return 1
        goal = heard
        print(f"Goal (from voice): {goal!r}")
    if not goal:
        print("Provide a goal as argument or use --voice to speak it.", file=sys.stderr)
        return 1
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
    trace = run_agent(root=root, goal=goal, cfg=cfg)
    print(json.dumps(trace, indent=2))
    # Optional: speak last summary if voice mode and TTS available
    if getattr(args, "voice", False) and trace:
        for entry in reversed(trace):
            if "result" in entry and isinstance(entry.get("result"), dict):
                summary = entry["result"].get("summary") or entry["result"].get("next")
                if summary:
                    voice_mod.speak(summary)
                    break
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
    r.add_argument("goal", nargs="?", default=None, help="What you want the agent to do (or use --voice to speak it).")
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
    r.add_argument("--voice", action="store_true", help="Use microphone for goal (speech-to-text), then speak result (TTS).")
    r.add_argument("--listen-timeout", type=float, default=10.0, help="Seconds to listen for --voice (default 10).")
    r.set_defaults(func=cmd_run)

    v = sub.add_parser("voice", help="Interactive voice loop: listen -> run agent -> speak result.")
    v.add_argument("--root", default=None, help="Repo root (default: cwd).")
    v.add_argument("--model", default="llama3.1:8b", help="Ollama model.")
    v.add_argument("--verify", default=None, help="Verification command after edits.")
    v.add_argument("--listen-timeout", type=float, default=10.0, help="Seconds to listen per turn.")
    v.add_argument("--no-speak", action="store_true", help="Do not speak the agent response (print only).")
    v.set_defaults(func=cmd_voice)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
