"""Small cross-process locks so two Cursor agents cannot run a milestone twice."""

from __future__ import annotations

import json
import os
import socket
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .paths import refuse


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


@contextmanager
def milestone_lock(run_dir: Path, name: str):
    """Acquire an atomic per-run lock, recovering locks left by dead local processes."""
    lock_dir = run_dir / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    path = lock_dir / f"{name}.lock"
    token = {"pid": os.getpid(), "host": socket.gethostname(),
             "started_at": datetime.now().isoformat(timespec="seconds")}

    for attempt in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(token, handle)
            break
        except FileExistsError:
            try:
                owner = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                owner = {}
            try:
                owner_pid = int(owner["pid"])
            except (KeyError, TypeError, ValueError):
                owner_pid = 0
            local_dead = owner.get("host") == socket.gethostname() and owner_pid > 0 and not _pid_alive(owner_pid)
            if attempt == 0 and local_dead:
                path.unlink(missing_ok=True)
                continue
            refuse(f"milestone '{name}' is already running (lock owner: {owner or 'unknown'})")
    try:
        yield
    finally:
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            current = None
        if current == token:
            path.unlink(missing_ok=True)
