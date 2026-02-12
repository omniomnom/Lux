"""
Command guardrails: block known attack patterns for agent-executed shell commands.

- DENY: never run (exit 126).
- UNSAFE: run only when caller passes allow_unsafe=True (e.g. lux run --unsafe).
- OK: allow.

Covers: CWE-78 (OS command injection), CWE-88 (argument injection),
fork bombs, reverse shells, privilege escalation, data destruction,
OWASP OS Command Injection, CAPEC patterns.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

# Max command length (DoS / buffer)
MAX_COMMAND_LENGTH = 32 * 1024
# Forbidden bytes (injection / obfuscation)
FORBIDDEN_BYTES = (0x00,)  # NUL


@dataclass(frozen=True)
class SafetyResult:
    level: str  # "ok" | "unsafe" | "deny"
    reason: str


def _norm(s: str) -> str:
    return s.strip().lower()


def _deny(reason: str) -> SafetyResult:
    return SafetyResult(level="deny", reason=reason)


def _unsafe(reason: str) -> SafetyResult:
    return SafetyResult(level="unsafe", reason=reason)


def _ok() -> SafetyResult:
    return SafetyResult(level="ok", reason="ok")


# ---- DENY: never allow -----------------------------------------------

DENY_PATTERNS: Sequence[tuple[str, str]] = (
    # Destructive
    (r"\brm\s+(-[rf]+|-fr)\b", "rm -rf"),
    (r"\brm\s+.*\s+/\s*$", "rm targeting root"),
    (r"\brm\s+.*\s+/etc/", "rm under /etc"),
    (r"\bsudo\b", "sudo"),
    (r"\bsu\s+", "su"),
    (r"\bdoas\b", "doas"),
    (r"\brun0\b", "run0"),
    (r"\bshutdown\b", "shutdown"),
    (r"\breboot\b", "reboot"),
    (r"\bhalt\b", "halt"),
    (r"\bpoweroff\b", "poweroff"),
    (r"\bmkfs\b", "mkfs"),
    (r"\bwipefs\b", "wipefs"),
    (r"\bdd\s+.*(if=|\sof=).*/dev/", "dd to/from block device"),
    # Fork bombs (multiple variants)
    (r"\b:\(\)\s*\{\s*:\s*\|", "fork bomb"),
    (r"^\s*:\s*\(\s*\)\s*\{", "fork bomb (alt)"),
    (r"\$\s*\(\s*:\s*\)", "fork bomb $(:)"),
    (r":\s*\{\s*:\s*\|", "fork bomb :{|:"),
)

# Pipe to shell (RCE)
DENY_PIPE_SHELL = re.compile(
    r"\b(curl|wget|fetch)\b.*\|[\s]*(sh|bash|zsh|dash|ksh|csh|tcsh|python|python3|ruby|perl)\b",
    re.I,
)
DENY_PIPE_SHELL_ALT = re.compile(
    r"\b(wget|curl)\s+.*\s+-[oO]\s*-\s*\|[\s]*(sh|bash|zsh)",
    re.I,
)
# base64 decode piped to shell (here-string, pipe, etc.)
DENY_BASE64_SHELL = re.compile(r"\bbase64\s+-d\s+.*\|[\s]*(sh|bash)\b", re.I)

# Reverse shell / remote code
DENY_REVERSE_SHELL = re.compile(
    r"\b(nc|netcat|ncat|socat)\b.*(-e\s|--exec\s|>\s*&|/dev/tcp)",
    re.I,
)
DENY_BASH_DEV_TCP = re.compile(r"/dev/(tcp|udp)/")

# Redirects to system / auth
DENY_REDIRECT_SYSTEM = re.compile(
    r">\s*(/etc/|/boot/|/dev/sd|/dev/nvme|/dev/disk|/usr/|/bin/|/sbin/|/var/system|/proc/|/sys/)"
)
DENY_REDIRECT_SSH = re.compile(r">>\s*(~\/\.ssh/|/root/\.ssh/|/etc/ssh/)")
# setuid/setgid bits (privilege escalation): chmod +s or mode 4xxx/2xxx
DENY_CHMOD_SUID = re.compile(r"\bchmod\s+(\+\s*[sg]|[0-7]*[42][0-7]{3})\s+", re.I)

# Env hijack
DENY_LD_PRELOAD = re.compile(r"\bLD_PRELOAD\s*=", re.I)
DENY_BASH_ENV = re.compile(r"\bBASH_ENV\s*=", re.I)

# Dangerous chmod/chown on root
DENY_CHMOD_ROOT = re.compile(r"\bchmod\s+[0-7]+\s+/?\s*$")
DENY_CHOWN_ROOT = re.compile(r"\bchown\s+(-R\s+)?(root|0)\s+/?\s*$")

# Shellshock-style
DENY_SHELLSHOCK = re.compile(r"\(\s*\)\s*\{\s*[^}]*\s*;\s*\}\s*;")

# Obfuscated exec
DENY_PYTHON_EXEC = re.compile(
    r"python\d*\s+-c\s+['\"].*__(import|subprocess|os\.system|eval)__",
    re.I,
)
DENY_EVAL_EXEC = re.compile(r"\b(eval|exec)\s+[\"']?\$\{")


def _check_deny(c: str) -> SafetyResult | None:
    for pat, reason in DENY_PATTERNS:
        if re.search(pat, c):
            return _deny(reason)
    if DENY_PIPE_SHELL.search(c):
        return _deny("pipe to shell (curl|wget|...|sh)")
    if DENY_PIPE_SHELL_ALT.search(c):
        return _deny("pipe to shell (wget -O -|sh)")
    if DENY_BASE64_SHELL.search(c):
        return _deny("base64 decode pipe to shell")
    if DENY_REVERSE_SHELL.search(c):
        return _deny("reverse shell (nc -e / dev/tcp)")
    if DENY_BASH_DEV_TCP.search(c):
        return _deny("/dev/tcp or /dev/udp")
    if DENY_REDIRECT_SYSTEM.search(c):
        return _deny("redirect to system path")
    if DENY_REDIRECT_SSH.search(c):
        return _deny("redirect to ssh auth path")
    if DENY_LD_PRELOAD.search(c):
        return _deny("LD_PRELOAD")
    if DENY_BASH_ENV.search(c):
        return _deny("BASH_ENV")
    if DENY_CHMOD_ROOT.search(c):
        return _deny("chmod on root")
    if DENY_CHOWN_ROOT.search(c):
        return _deny("chown root")
    if DENY_CHMOD_SUID.search(c):
        return _deny("chmod setuid/setgid")
    if DENY_SHELLSHOCK.search(c):
        return _deny("shellshock-style")
    if DENY_PYTHON_EXEC.search(c):
        return _deny("python -c exec/subprocess")
    if DENY_EVAL_EXEC.search(c):
        return _deny("eval/exec with variable expansion")
    return None


# ---- UNSAFE: allow only with --unsafe ---------------------------------

UNSAFE_PATTERNS: Sequence[tuple[str, str]] = (
    (r"\bgit\s+push\b", "git push"),
    (r"\bgit\s+push\s+--force\b", "git push --force"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard"),
    (r"\bgit\s+clean\s+-f", "git clean -f"),
    (r"\bgit\s+rebase\b", "git rebase"),
    (r"\bchmod\b", "chmod"),
    (r"\bchown\b", "chown"),
    (r"\btee\s+/", "tee to absolute path"),
    (r">\s+/", "redirect to absolute path"),
    (r"\bdocker\s+run\b", "docker run"),
    (r"\bdocker\s+exec\b", "docker exec"),
    (r"\bkubectl\s+exec\b", "kubectl exec"),
    (r"\bssh\s+[^#]+['\"]?\w+['\"]?\s*$", "ssh remote command"),
)


def check_command_safety(command: str) -> SafetyResult:
    """
    Check a shell command against deny and unsafe patterns.
    Returns SafetyResult(level="ok"|"unsafe"|"deny", reason="...").
    """
    if not command or not command.strip():
        return _deny("empty command")

    raw = command
    if len(raw.encode("utf-8")) > MAX_COMMAND_LENGTH:
        return _deny("command exceeds max length")

    for b in FORBIDDEN_BYTES:
        if b in raw.encode("latin-1"):
            return _deny("forbidden byte in command")

    c = _norm(command)

    result = _check_deny(c)
    if result is not None:
        return result

    for pat, reason in UNSAFE_PATTERNS:
        if re.search(pat, c):
            return _unsafe(reason)

    return _ok()
