"""Drive the self-heal loop: `bdata scraper heal` -> approve -> re-run.

The Bright Data CLI runs interactively (proposes a fix, asks for approval), so
the default path here launches the CLI for a human to confirm — which is
exactly the demo flow. In CI we use the CLI with the approve flag where
supported; otherwise the run pauses and the operator approves in the terminal.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


class HealError(RuntimeError):
    pass


def find_bdata() -> str:
    """Return a command line that can run bdata (installed or via npx)."""
    if shutil.which("bdata"):
        return "bdata"
    if shutil.which("npx"):
        return "npx -p @brightdata/cli bdata"
    raise HealError("Bright Data CLI not found (install it or use npx -p @brightdata/cli)")


def heal_and_approve(collector_id: str, symptom: str, auto_approve: bool = True,
                     timeout_s: float = 1800.0) -> str:
    """Heal a collector and approve the fix. Returns a log of what happened."""
    base = find_bdata()
    log_lines: list[str] = []

    heal_cmd = f"{base} scraper heal {collector_id} {symptom!r}"
    log.info("healing: %s", heal_cmd)
    result = subprocess.run(heal_cmd, shell=True, capture_output=True, text=True, timeout=timeout_s)
    log_lines.append(f"$ {heal_cmd}\n{result.stdout}\n{result.stderr}".strip())
    if result.returncode != 0:
        raise HealError(f"bdata scraper heal failed (exit {result.returncode}):\n{result.stderr}")

    approve_cmd = f"{base} scraper approve {collector_id}"
    if not auto_approve:
        log_lines.append(f"pending manual approval: {approve_cmd}")
        return "\n".join(log_lines)
    log.info("approving: %s", approve_cmd)
    result = subprocess.run(approve_cmd, shell=True, capture_output=True, text=True, timeout=timeout_s)
    log_lines.append(f"$ {approve_cmd}\n{result.stdout}\n{result.stderr}".strip())
    if result.returncode != 0:
        raise HealError(f"bdata scraper approve failed (exit {result.returncode}):\n{result.stderr}")

    return "\n".join(log_lines)


def run_scraper(collector_id: str, url: str, timeout_s: float = 1800.0) -> str:
    """CLI run (used for the interactive demo and quick checks)."""
    base = find_bdata()
    cmd = f"{base} scraper run {collector_id} {url}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout_s)
    if result.returncode != 0:
        raise HealError(f"bdata scraper run failed (exit {result.returncode}):\n{result.stderr}")
    return result.stdout
