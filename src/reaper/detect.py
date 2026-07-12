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


def fetch_identity(session: "Session") -> None:
    """Best-effort grab of `user@host` so the operator can recognise the shell.

    Only used for the notification line - failure is non-fatal.

    The markers are assembled from shell variables so the command-echo coming
    back doesn't contain the final sentinel and confuse the parser.
    """
    if not session.alive or session.os_type is None:
        return

    a1, a2 = uuid.uuid4().hex[:6], uuid.uuid4().hex[:6]
    b1, b2 = uuid.uuid4().hex[:6], uuid.uuid4().hex[:6]
    start  = f"__R{a1}{a2}__"
    end    = f"__R{b1}{b2}__"

    if session.os_type == "linux":
        cmd = (
            f"_A={a1}{a2};_B={b1}{b2};"
            f"echo __R${{_A}}__;"
            f"(whoami; hostname) 2>/dev/null | tr '\\n' '@';"
            f"echo;echo __R${{_B}}__\n"
        )
    elif session.os_type == "windows_ps":
        cmd = (
            f"$_a='{a1}'+'{a2}';$_b='{b1}'+'{b2}';"
            f"Write-Host \"__R${{_a}}__\";"
            f"Write-Host (\"$env:USERNAME@$env:COMPUTERNAME\");"
            f"Write-Host \"__R${{_b}}__\"\r\n"
        )
    else:  # windows_cmd
        cmd = (
            f"set _A={a1}{a2}& set _B={b1}{b2}& "
            f"echo __R%_A%__& echo %USERNAME%@%COMPUTERNAME%& echo __R%_B%__\r\n"
        )

    try:
        session.conn.sendall(cmd.encode(session.encoding, errors="replace"))
    except OSError:
        session.alive = False
        return

    raw = _recv_for(session, 3.0)
    if start in raw and end in raw:
        # rsplit on start so an echoed command containing the marker text
        # doesn't shadow the real output block.
        chunk = raw.rsplit(start, 1)[1].split(end, 1)[0]
        for line in chunk.splitlines():
            line = line.strip().rstrip("@")
            if line and "@" in line and " " not in line and len(line) <= 80:
                session.identity = line
                return


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
