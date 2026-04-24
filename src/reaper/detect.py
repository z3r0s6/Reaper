from __future__ import annotations

import logging
import re
import select
import time
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reaper.session import Session

logger = logging.getLogger("reaper.detect")

_TIMEOUT        = 4.0
_SELECT_TIMEOUT = 0.1


def _recv_for(session: "Session", duration: float) -> str:
    buf      = b""
    deadline = time.monotonic() + duration
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            r, _, _ = select.select([session.conn], [], [], min(remaining, _SELECT_TIMEOUT))
            if r:
                chunk = session.conn.recv(4096)
                if not chunk:
                    session.alive = False
                    break
                buf += chunk
                if session._log_fh:
                    session._log_write(chunk, "in")
        except OSError:
            session.alive = False
            break
    return buf.decode("utf-8", errors="replace")


def detect_os(session: "Session") -> None:
    """Probe the remote shell to determine OS and shell type."""
    if not session.alive:
        return

    a = uuid.uuid4().hex[:8]
    b = uuid.uuid4().hex[:8]
    expected = a + b
    probe    = f" A={a} B={b}; echo $A$B\r\n"

    try:
        session.conn.sendall(probe.encode("utf-8"))
    except OSError:
        session.alive = False
        return

    response = _recv_for(session, _TIMEOUT)
    logger.debug(f"[detect] session #{session.id} raw: {response!r}")
    _apply(session, response, expected)


def _apply(session: "Session", response: str, expected: str) -> None:
    r = response.lower()

    if expected in response:
        session.os_type  = "linux"
        session.encoding = "utf-8"
        session.eol      = "\n"
        return

    ps_hints   = ["is not recognized as the name of a cmdlet", "windows powershell", "powershell"]
    ps_prompt  = bool(re.search(r"\bps\s+[a-z]:\\", r))
    if ps_prompt or any(h in r for h in ps_hints):
        session.os_type  = "windows_ps"
        session.encoding = "cp1252"
        session.eol      = "\r\n"
        return

    cmd_hints = ["is not recognized as an internal or external command", "microsoft windows", "c:\\", "c:/"]
    if any(h in r for h in cmd_hints):
        session.os_type  = "windows_cmd"
        session.encoding = "cp1252"
        session.eol      = "\r\n"
        return

    _fallback(session)


def _fallback(session: "Session") -> None:
    if not session.alive:
        return
    try:
        session.conn.sendall(b"uname\r\n")
    except OSError:
        return

    response = _recv_for(session, _TIMEOUT)
    r        = response.lower()
    logger.debug(f"[detect] session #{session.id} fallback: {response!r}")

    if any(x in r for x in ("linux", "darwin", "freebsd", "openbsd", "netbsd")):
        session.os_type  = "linux"
        session.encoding = "utf-8"
        session.eol      = "\n"
    elif any(x in r for x in ("windows", "microsoft", "c:\\")):
        session.os_type  = "windows_cmd"
        session.encoding = "cp1252"
        session.eol      = "\r\n"
